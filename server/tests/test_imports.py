from server.article import ArticleError
from import_tools.yt_subs import NoSubtitlesError
from server.routes import imports as imports_route


def test_youtube_import_creates_scored_ready_book(client, monkeypatch):
    monkeypatch.setattr(
        imports_route, "fetch_subs", lambda url: ("영상 제목", "안녕하세요 여러분.", "abc123")
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


def test_youtube_import_dedupes_on_video_id(client, monkeypatch):
    monkeypatch.setattr(
        imports_route, "fetch_subs", lambda url: ("제목", "본문 내용입니다.", "dupe1")
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
