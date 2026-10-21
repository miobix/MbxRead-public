import io

from server.article import ArticleError
from import_tools.yt_subs import NoSubtitlesError
from server.routes import imports as imports_route


def test_youtube_import_creates_scored_ready_book(client, monkeypatch):
    monkeypatch.setattr(
        imports_route,
        "fetch_subs",
        lambda url: ("영상 제목", "안녕하세요 여러분.", "abc123", 754),
    )

    resp = client.post(
        "/api/import/youtube",
        json={"url": "https://youtu.be/abc123", "topic": "gaming", "tags": ["대도서관"]},
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["title"] == "영상 제목"
    assert body["source"] == "yt"
    assert body["source_url"] == "https://youtu.be/abc123"
    assert body["source_ref"] == "yt:abc123"
    assert body["topic"] == "gaming"
    assert body["tags"] == ["대도서관"]
    assert body["page_count"] >= 1
    # Epic 18: real yt-dlp duration round-trips; word_count is derived from the text.
    assert body["duration_seconds"] == 754
    assert body["word_count"] == 2


def test_youtube_import_dedupes_on_video_id(client, monkeypatch):
    monkeypatch.setattr(
        imports_route, "fetch_subs", lambda url: ("제목", "본문 내용입니다.", "dupe1", None)
    )

    first = client.post("/api/import/youtube", json={"url": "https://youtu.be/dupe1"})
    assert first.status_code == 201

    second = client.post("/api/import/youtube", json={"url": "https://youtu.be/dupe1?x=1"})
    assert second.status_code == 409
    assert client.get("/api/books").json().__len__() == 1


def test_youtube_import_no_subtitles_returns_502(client, monkeypatch):
    def raise_no_subs(url):
        raise NoSubtitlesError("No Korean subtitles found for this video.")

    monkeypatch.setattr(imports_route, "fetch_subs", raise_no_subs)

    resp = client.post("/api/import/youtube", json={"url": "https://youtu.be/nosubs"})
    assert resp.status_code == 502
    assert resp.json() == {"error": "No Korean subtitles found for this video."}
    assert client.get("/api/books").json() == []


def test_article_import_creates_book(client, monkeypatch):
    monkeypatch.setattr(
        imports_route,
        "fetch_article",
        lambda url: ("기사 제목", "기사 본문 내용입니다."),
    )

    resp = client.post(
        "/api/import/article",
        json={"url": "https://example.com/a", "topic": "news"},
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["title"] == "기사 제목"
    assert body["source"] == "article"
    assert body["source_ref"] == "article:https://example.com/a"
    assert body["word_count"] == 3
    assert body["duration_seconds"] is None


def test_article_import_dedupes_on_url(client, monkeypatch):
    monkeypatch.setattr(
        imports_route, "fetch_article", lambda url: ("제목", "본문입니다 내용.")
    )

    first = client.post("/api/import/article", json={"url": "https://example.com/dupe"})
    assert first.status_code == 201
    second = client.post("/api/import/article", json={"url": "https://example.com/dupe"})
    assert second.status_code == 409
    assert client.get("/api/books").json().__len__() == 1


def test_article_import_fetch_failure_returns_502(client, monkeypatch):
    def raise_error(url):
        raise ArticleError(f"Could not fetch {url}")

    monkeypatch.setattr(imports_route, "fetch_article", raise_error)

    resp = client.post("/api/import/article", json={"url": "https://example.com/dead"})
    assert resp.status_code == 502
    assert resp.json() == {"error": "Could not fetch https://example.com/dead"}


def test_pdf_import_creates_book(client, monkeypatch):
    monkeypatch.setattr(
        imports_route, "extract_pdf", lambda content, page_range: "피디에프 본문 내용."
    )

    resp = client.post(
        "/api/import/pdf",
        data={"title": "", "topic": "literature", "tags": "다빈치, 소설"},
        files={"file": ("story.pdf", b"%PDF-fake-bytes", "application/pdf")},
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["title"] == "story"
    assert body["source"] == "pdf"
    assert body["topic"] == "literature"
    assert body["tags"] == ["다빈치", "소설"]
    assert body["source_ref"].startswith("pdf:")


def test_pdf_import_dedupes_on_content_hash(client, monkeypatch):
    monkeypatch.setattr(
        imports_route, "extract_pdf", lambda content, page_range: "동일한 본문 내용."
    )
    pdf_bytes = b"%PDF-same-bytes"

    first = client.post(
        "/api/import/pdf", files={"file": ("a.pdf", pdf_bytes, "application/pdf")}
    )
    assert first.status_code == 201

    second = client.post(
        "/api/import/pdf", files={"file": ("b.pdf", pdf_bytes, "application/pdf")}
    )
    assert second.status_code == 409
    assert client.get("/api/books").json().__len__() == 1


def test_pdf_import_extract_failure_returns_502(client, monkeypatch):
    def raise_error(content, page_range):
        raise RuntimeError("cannot open broken document")

    monkeypatch.setattr(imports_route, "extract_pdf", raise_error)

    resp = client.post(
        "/api/import/pdf", files={"file": ("broken.pdf", b"not a pdf", "application/pdf")}
    )
    assert resp.status_code == 502
    assert resp.json() == {"error": "cannot open broken document"}


def test_pdf_import_bad_page_range_returns_422(client):
    resp = client.post(
        "/api/import/pdf",
        data={"pages": "1-x"},
        files={"file": ("a.pdf", b"%PDF", "application/pdf")},
    )
    assert resp.status_code == 422
    assert "1-20" in resp.json()["detail"]


def test_pdf_import_empty_text_returns_502(client, monkeypatch):
    monkeypatch.setattr(imports_route, "extract_pdf", lambda content, page_range: "  \n")

    resp = client.post(
        "/api/import/pdf", files={"file": ("scan.pdf", b"%PDF image only", "application/pdf")}
    )
    assert resp.status_code == 502
    assert resp.json() == {"error": "No extractable text in this PDF."}


def test_epub_import_creates_book(client, monkeypatch):
    monkeypatch.setattr(
        imports_route, "extract_epub", lambda content: "이펍 본문 내용입니다."
    )

    resp = client.post(
        "/api/import/epub",
        data={"title": "", "topic": "literature", "tags": "김영하, 소설"},
        files={"file": ("novel.epub", b"PK-fake-epub-bytes", "application/epub+zip")},
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["title"] == "novel"
    assert body["source"] == "epub"
    assert body["topic"] == "literature"
    assert body["tags"] == ["김영하", "소설"]
    assert body["source_ref"].startswith("epub:")
    assert body["page_count"] >= 1


def test_epub_import_dedupes_on_content_hash(client, monkeypatch):
    monkeypatch.setattr(
        imports_route, "extract_epub", lambda content: "동일한 이펍 본문 내용."
    )
    epub_bytes = b"PK-same-epub-bytes"

    first = client.post(
        "/api/import/epub", files={"file": ("a.epub", epub_bytes, "application/epub+zip")}
    )
    assert first.status_code == 201

    second = client.post(
        "/api/import/epub", files={"file": ("b.epub", epub_bytes, "application/epub+zip")}
    )
    assert second.status_code == 409
    assert client.get("/api/books").json().__len__() == 1


def test_epub_import_extract_failure_returns_502(client, monkeypatch):
    def raise_error(content):
        raise RuntimeError("bad zip header")

    monkeypatch.setattr(imports_route, "extract_epub", raise_error)

    resp = client.post(
        "/api/import/epub",
        files={"file": ("broken.epub", b"not an epub", "application/epub+zip")},
    )
    assert resp.status_code == 502
    assert resp.json() == {"error": "bad zip header"}


def test_epub_import_empty_text_returns_502(client, monkeypatch):
    monkeypatch.setattr(imports_route, "extract_epub", lambda content: "   \n  ")

    resp = client.post(
        "/api/import/epub",
        files={"file": ("empty.epub", b"PK-empty", "application/epub+zip")},
    )
    assert resp.status_code == 502
    assert resp.json() == {"error": "No extractable text in this EPUB."}
    assert client.get("/api/books").json() == []


def _make_epub_bytes(chapters: list[list[str]]) -> bytes:
    """Build a minimal real EPUB in memory. Each chapter is a list of paragraphs."""
    from ebooklib import epub

    book = epub.EpubBook()
    book.set_identifier("test-id")
    book.set_title("테스트 책")
    book.set_language("ko")
    spine = []
    for n, paragraphs in enumerate(chapters):
        doc = epub.EpubHtml(title=f"장 {n}", file_name=f"c{n}.xhtml", lang="ko")
        body = "".join(f"<p>{p}</p>" for p in paragraphs)
        doc.content = f"<html><head><title>x</title></head><body>{body}</body></html>"
        book.add_item(doc)
        spine.append(doc)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = spine
    buf = io.BytesIO()
    epub.write_epub(buf, book)
    return buf.getvalue()


def test_epub_extract_reads_spine_text_in_order():
    """The real extractor (not mocked) pulls Korean text from a built EPUB."""
    data = _make_epub_bytes(
        [["안녕하세요 여러분.", "오늘은 좋은 날입니다."], ["둘째 장의 내용입니다."]]
    )
    text = imports_route.extract_epub(data)
    assert "안녕하세요 여러분." in text
    assert "오늘은 좋은 날입니다." in text
    assert "둘째 장의 내용입니다." in text
    # spine order preserved: first chapter's text precedes the second's
    assert text.index("안녕하세요") < text.index("둘째 장")


def test_epub_import_end_to_end_with_real_extractor(client):
    """No mock: a built EPUB imports into a scored-ready book."""
    data = _make_epub_bytes([["한국어 소설의 첫 문장입니다.", "두 번째 문장이에요."]])

    resp = client.post(
        "/api/import/epub",
        data={"topic": "literature"},
        files={"file": ("mybook.epub", data, "application/epub+zip")},
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["title"] == "mybook"
    assert body["source"] == "epub"
    assert body["page_count"] >= 1


# --------------------------------------------------------------------------- #
# subtitle import (batch)
# --------------------------------------------------------------------------- #
# Unlike the other importers these tests run the *real* parser rather than
# mocking at the module boundary: subtitle parsing is pure local string work with
# no network or API key involved, so exercising it end-to-end costs nothing and
# is what actually proves the route.

_SRT_1 = (
    b"1\n00:00:01,000 --> 00:00:03,000\n\xec\xb2\xab \xeb\xb2\x88\xec\xa7\xb8.\n\n"
)
_SRT_2 = (
    b"1\n00:00:01,000 --> 00:00:04,000\n\xeb\x91\x90 \xeb\xb2\x88\xec\xa7\xb8.\n\n"
)


def _sub(name: str, data: bytes):
    return ("files", (name, data, "application/x-subrip"))


def test_subtitle_batch_imports_in_filename_order(client):
    resp = client.post(
        "/api/import/subtitles",
        data={"topic": "tv", "tags": "bojack, sitcom"},
        files=[_sub("Show S01E02.ko.srt", _SRT_2), _sub("Show S01E01.ko.srt", _SRT_1)],
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["skipped"] == [] and body["failed"] == []
    # Uploaded E02-first, but a season must land in episode order.
    assert [b["title"] for b in body["imported"]] == ["Show S01E01", "Show S01E02"]
    assert all(b["source"] == "subs" for b in body["imported"])
    assert body["imported"][0]["topic"] == "tv"
    assert body["imported"][0]["tags"] == ["bojack", "sitcom"]
    # Duration comes from the last cue, so the Library length stat works here too.
    assert body["imported"][0]["duration_seconds"] == 3
    assert body["imported"][1]["duration_seconds"] == 4


def test_subtitle_batch_skips_already_imported_files(client):
    first = client.post("/api/import/subtitles", files=[_sub("a.ko.srt", _SRT_1)])
    assert len(first.json()["imported"]) == 1

    # Re-dropping a season is the normal case: same bytes, different filename.
    second = client.post(
        "/api/import/subtitles",
        files=[_sub("renamed.ko.srt", _SRT_1), _sub("new.ko.srt", _SRT_2)],
    )
    body = second.json()
    assert [s["reason"] for s in body["skipped"]] == ["already imported"]
    assert [b["title"] for b in body["imported"]] == ["new"]
    assert len(client.get("/api/books").json()) == 2


def test_one_bad_file_does_not_sink_the_batch(client):
    resp = client.post(
        "/api/import/subtitles",
        files=[
            _sub("good.ko.srt", _SRT_1),
            # Named .srt, so it is recognised as SRT and fails for having no cues…
            _sub("empty.ko.srt", b"not a subtitle file"),
            # …while an unknown extension fails earlier, at format detection.
            _sub("notes.doc", b"not a subtitle file"),
        ],
    )

    body = resp.json()
    assert [b["title"] for b in body["imported"]] == ["good"]
    failures = {f["filename"]: f["error"] for f in body["failed"]}
    assert "No subtitle text found" in failures["empty.ko.srt"]
    assert "Unrecognised subtitle file" in failures["notes.doc"]


def test_title_overrides_only_for_a_single_file(client):
    single = client.post(
        "/api/import/subtitles",
        data={"title": "My Title"},
        files=[_sub("ignored.ko.srt", _SRT_1)],
    )
    assert single.json()["imported"][0]["title"] == "My Title"

    batch = client.post(
        "/api/import/subtitles",
        data={"title": "My Title"},
        files=[_sub("ep one.ko.srt", _SRT_2), _sub("ep two.ko.vtt", b"WEBVTT\n\n00:00:01.000 --> 00:00:02.000\n\xea\xb7\xb8\xeb\x9e\x98.\n")],
    )
    # A batch title would collide across every episode, so filenames win.
    assert sorted(b["title"] for b in batch.json()["imported"]) == ["ep one", "ep two"]
