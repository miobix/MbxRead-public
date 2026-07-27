import sqlite3

from server.paging import split_pages_by_rows
from server.routes.settings import DEFAULT_CHARS_PER_ROW, DEFAULT_PAGE_ROWS

SHORT_STORY = "그는 옷을 입고 나갔다. 날씨가 정말 좋았다! 학교에 가야 했다."
LONG_STORY = "문장입니다. " * 300  # well over the default page size


def test_create_book_splits_into_pages_matching_paging_util(client):
    resp = client.post("/api/books", json={"title": "Long", "text": LONG_STORY})
    assert resp.status_code == 201
    body = resp.json()
    # Imports split at the configured page rows/chars-per-row, not split_pages_by_rows'
    # own default.
    expected_pages = split_pages_by_rows(LONG_STORY, DEFAULT_PAGE_ROWS, DEFAULT_CHARS_PER_ROW)
    assert body["page_count"] == len(expected_pages)
    assert body["page_count"] > 1
    assert body["current_page"] == 1
    assert body["title"] == "Long"
    assert body["source"] == "paste"


def test_page_boundaries_never_split_a_sentence(client):
    resp = client.post("/api/books", json={"title": "Long", "text": LONG_STORY})
    book_id = resp.json()["id"]
    page_count = resp.json()["page_count"]

    pages_content = []
    for n in range(1, page_count + 1):
        page = client.get(f"/api/books/{book_id}/pages/{n}").json()
        pages_content.append(page["content"])

    assert "".join(pages_content) == LONG_STORY
    for content in pages_content[:-1]:
        assert content.endswith(".") or content.endswith("\n")


def test_page_payload_shape(client):
    resp = client.post("/api/books", json={"title": "Short", "text": SHORT_STORY})
    book_id = resp.json()["id"]

    page = client.get(f"/api/books/{book_id}/pages/1").json()
    assert page["page_no"] == 1
    assert page["page_count"] == 1
    assert page["content"] == SHORT_STORY
    assert isinstance(page["tokens"], list)
    assert page["tokens"]  # tokenizer should find something in this sentence
    for tok in page["tokens"]:
        assert set(tok.keys()) == {"s", "e", "surface", "lemma", "pos"}
        assert page["content"][tok["s"] : tok["e"]] == tok["surface"]
    assert page["terms"] == {}

    lemmas = {tok["lemma"] for tok in page["tokens"]}
    assert "입다" in lemmas
    assert "학교" in lemmas


def test_page_includes_saved_terms_matching_page_lemmas(client, db_path):
    resp = client.post("/api/books", json={"title": "Short", "text": SHORT_STORY})
    book_id = resp.json()["id"]

    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO terms (lemma, translation, status, deck) VALUES (?, ?, ?, ?)",
        ("입다", "to wear", "learning", "Korean"),
    )
    conn.commit()
    conn.close()

    page = client.get(f"/api/books/{book_id}/pages/1").json()
    assert page["terms"] == {
        "입다": {
            "id": 1,
            "lemma": "입다",
            "translation": "to wear",
            "notes": "",
            "status": "learning",
            "deck": "Korean",
            "forms": [],
            "examples": [],
            "back_items": [],
        }
    }


def test_page_highlights_a_terms_extra_form(client):
    """Epic 20: a token whose lemma is one of a term's `forms` highlights as that
    term, even though the term's own lemma never appears on the page."""
    resp = client.post("/api/books", json={"title": "Short", "text": SHORT_STORY})
    book_id = resp.json()["id"]

    # lemma 승인 is not in SHORT_STORY; its form 학교 is a token lemma on the page.
    client.post(
        "/api/terms",
        json={
            "lemma": "승인",
            "translation": "approval",
            "forms": [{"text": "학교", "kind": "manual"}],
        },
    )

    page = client.get(f"/api/books/{book_id}/pages/1").json()
    assert "승인" not in page["terms"]
    assert page["terms"]["학교"]["translation"] == "approval"
    assert page["terms"]["학교"]["lemma"] == "승인"
    assert page["terms"]["학교"]["forms"] == [{"text": "학교", "kind": "manual"}]


def test_get_nonexistent_page_returns_404(client):
    resp = client.post("/api/books", json={"title": "Short", "text": SHORT_STORY})
    book_id = resp.json()["id"]
    assert client.get(f"/api/books/{book_id}/pages/99").status_code == 404


def test_current_page_patch_persists(client):
    resp = client.post("/api/books", json={"title": "Long", "text": LONG_STORY})
    book_id = resp.json()["id"]

    patch = client.patch(f"/api/books/{book_id}", json={"current_page": 3})
    assert patch.status_code == 200
    assert patch.json()["current_page"] == 3

    fetched = client.get(f"/api/books/{book_id}")
    assert fetched.json()["current_page"] == 3


def test_title_patch_persists(client):
    resp = client.post("/api/books", json={"title": "Old", "text": SHORT_STORY})
    book_id = resp.json()["id"]

    patch = client.patch(f"/api/books/{book_id}", json={"title": "New"})
    assert patch.json()["title"] == "New"


def test_cascade_delete_removes_pages(client, db_path):
    resp = client.post("/api/books", json={"title": "Short", "text": SHORT_STORY})
    book_id = resp.json()["id"]

    assert client.delete(f"/api/books/{book_id}").status_code == 204

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    remaining = conn.execute(
        "SELECT COUNT(*) FROM pages WHERE book_id = ?", (book_id,)
    ).fetchone()[0]
    conn.close()
    assert remaining == 0

    assert client.get(f"/api/books/{book_id}").status_code == 404


def test_list_books_shape(client):
    client.post("/api/books", json={"title": "A", "text": SHORT_STORY})
    client.post("/api/books", json={"title": "B", "text": SHORT_STORY, "source": "txt"})

    resp = client.get("/api/books")
    assert resp.status_code == 200
    books = resp.json()
    assert len(books) == 2
    for book in books:
        assert set(book.keys()) == {
            "id", "title", "source", "current_page", "current_offset",
            "page_count", "total_chars", "created",
            "coverage", "new_per_page", "scored_at",
            "topic", "tags", "source_url", "source_ref", "fetched", "archived", "read",
            "status", "general_coverage", "general_level",
            "word_count", "duration_seconds",
            "feed_id", "discard_reason", "last_opened",
        }
        assert book["status"] == "library"


def test_create_book_with_topic_and_tags(client):
    resp = client.post(
        "/api/books",
        json={
            "title": "Game news",
            "text": SHORT_STORY,
            "topic": "gaming",
            "tags": ["ps5", "review"],
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["topic"] == "gaming"
    assert body["tags"] == ["ps5", "review"]
    assert body["archived"] is False
    assert body["read"] is False


def test_list_books_filters_by_topic(client):
    client.post("/api/books", json={"title": "A", "text": SHORT_STORY, "topic": "gaming"})
    client.post("/api/books", json={"title": "B", "text": SHORT_STORY, "topic": "fitness"})

    resp = client.get("/api/books?topic=gaming")
    assert resp.status_code == 200
    titles = {b["title"] for b in resp.json()}
    assert titles == {"A"}


def test_list_books_filters_by_archived(client):
    resp = client.post("/api/books", json={"title": "A", "text": SHORT_STORY})
    book_id = resp.json()["id"]
    client.post("/api/books", json={"title": "B", "text": SHORT_STORY})
    client.patch(f"/api/books/{book_id}", json={"archived": True})

    active = client.get("/api/books?archived=false").json()
    assert {b["title"] for b in active} == {"B"}

    archived = client.get("/api/books?archived=true").json()
    assert {b["title"] for b in archived} == {"A"}


def test_patch_book_topic_tags_archived_read(client):
    resp = client.post("/api/books", json={"title": "A", "text": SHORT_STORY})
    book_id = resp.json()["id"]

    patched = client.patch(
        f"/api/books/{book_id}",
        json={"topic": "literature", "tags": ["short-fiction"], "archived": True, "read": True},
    )
    assert patched.status_code == 200
    body = patched.json()
    assert body["topic"] == "literature"
    assert body["tags"] == ["short-fiction"]
    assert body["archived"] is True
    assert body["read"] is True


def test_duplicate_source_ref_returns_409(client):
    resp = client.post(
        "/api/books",
        json={"title": "A", "text": SHORT_STORY, "source_ref": "yt:abc123"},
    )
    assert resp.status_code == 201

    dup = client.post(
        "/api/books",
        json={"title": "B", "text": SHORT_STORY, "source_ref": "yt:abc123"},
    )
    assert dup.status_code == 409


def test_multiple_books_without_source_ref_are_allowed(client):
    resp1 = client.post("/api/books", json={"title": "A", "text": SHORT_STORY})
    resp2 = client.post("/api/books", json={"title": "B", "text": SHORT_STORY})
    assert resp1.status_code == 201
    assert resp2.status_code == 201


def test_get_patch_delete_404_for_missing_book(client):
    assert client.get("/api/books/999").status_code == 404
    assert client.patch("/api/books/999", json={"title": "x"}).status_code == 404
    assert client.delete("/api/books/999").status_code == 404


# --- Epic 15: candidate queue (status), source filter ---


def test_default_list_excludes_candidates_and_discarded(client):
    client.post("/api/books", json={"title": "Library", "text": SHORT_STORY})
    client.post(
        "/api/books", json={"title": "Candidate", "text": SHORT_STORY, "status": "candidate"}
    )
    client.post(
        "/api/books", json={"title": "Discarded", "text": SHORT_STORY, "status": "discarded"}
    )

    titles = {b["title"] for b in client.get("/api/books").json()}
    assert titles == {"Library"}

    titles = {b["title"] for b in client.get("/api/books?status=candidate").json()}
    assert titles == {"Candidate"}

    titles = {b["title"] for b in client.get("/api/books?status=discarded").json()}
    assert titles == {"Discarded"}


def test_list_books_filters_by_source(client):
    client.post("/api/books", json={"title": "A", "text": SHORT_STORY, "source": "paste"})
    client.post("/api/books", json={"title": "B", "text": SHORT_STORY, "source": "txt"})

    titles = {b["title"] for b in client.get("/api/books?source=txt").json()}
    assert titles == {"B"}


def test_promote_and_discard_via_patch(client):
    book_id = client.post(
        "/api/books", json={"title": "A", "text": SHORT_STORY, "status": "candidate"}
    ).json()["id"]

    promoted = client.patch(f"/api/books/{book_id}", json={"status": "library"})
    assert promoted.json()["status"] == "library"
    assert {b["id"] for b in client.get("/api/books").json()} == {book_id}

    discarded = client.patch(f"/api/books/{book_id}", json={"status": "discarded"})
    assert discarded.json()["status"] == "discarded"
    # Epic 19: a manual discard (as opposed to Epic 17's auto-expiry) is tagged 'user'.
    assert discarded.json()["discard_reason"] == "user"
    assert client.get("/api/books").json() == []


def test_manual_discard_purges_text_for_article_and_yt_only(client):
    """User's storage concern (2026-07-24): discarding a queued article/yt candidate
    should reclaim its page text, but paste/pdf/epub/txt content is kept
    indefinitely even if discarded."""
    article_id = client.post(
        "/api/books",
        json={"title": "A", "text": SHORT_STORY, "source": "article", "status": "candidate"},
    ).json()["id"]
    paste_id = client.post(
        "/api/books",
        json={"title": "B", "text": SHORT_STORY, "source": "paste", "status": "candidate"},
    ).json()["id"]

    client.patch(f"/api/books/{article_id}", json={"status": "discarded"})
    client.patch(f"/api/books/{paste_id}", json={"status": "discarded"})

    discarded = {b["id"]: b for b in client.get("/api/books?status=discarded").json()}
    assert discarded[article_id]["page_count"] == 0
    assert discarded[paste_id]["page_count"] > 0


def test_discarded_book_still_blocks_reimport(client):
    resp = client.post(
        "/api/books", json={"title": "A", "text": SHORT_STORY, "source_ref": "article:x"}
    )
    book_id = resp.json()["id"]
    client.patch(f"/api/books/{book_id}", json={"status": "discarded"})

    dup = client.post(
        "/api/books", json={"title": "B", "text": SHORT_STORY, "source_ref": "article:x"}
    )
    assert dup.status_code == 409


def test_score_book_caches_general_difficulty(client):
    book_id = client.post("/api/books", json={"title": "S", "text": SHORT_STORY}).json()["id"]
    scored = client.post(f"/api/books/{book_id}/score").json()
    assert scored["general_coverage"] is not None
    assert scored["general_level"] in {"easy", "medium", "hard"}


# --- 2026-07-24: sort + pagination (Library/Queue volume), last_opened ---


def test_get_page_stamps_last_opened(client):
    book_id = client.post("/api/books", json={"title": "A", "text": SHORT_STORY}).json()["id"]
    assert client.get("/api/books").json()[0]["last_opened"] is None

    client.get(f"/api/books/{book_id}/pages/1")

    assert client.get("/api/books").json()[0]["last_opened"] is not None


def test_list_books_sort_opened_puts_most_recently_viewed_first(client):
    a = client.post("/api/books", json={"title": "A", "text": SHORT_STORY}).json()["id"]
    b = client.post("/api/books", json={"title": "B", "text": SHORT_STORY}).json()["id"]
    # open A first, then B — B should now sort first ("most recently opened")
    client.get(f"/api/books/{a}/pages/1")
    client.get(f"/api/books/{b}/pages/1")

    titles = [bk["title"] for bk in client.get("/api/books?sort=opened").json()]
    assert titles == ["B", "A"]


def test_list_books_sort_opened_never_opened_sinks_after_opened(client):
    a = client.post("/api/books", json={"title": "A", "text": SHORT_STORY}).json()["id"]
    client.post("/api/books", json={"title": "B", "text": SHORT_STORY})
    client.get(f"/api/books/{a}/pages/1")

    titles = [bk["title"] for bk in client.get("/api/books?sort=opened").json()]
    assert titles == ["A", "B"]


def test_list_books_sort_easiest_orders_by_new_per_page(client, db_path):
    easy_id = client.post("/api/books", json={"title": "Easy", "text": SHORT_STORY}).json()["id"]
    hard_id = client.post("/api/books", json={"title": "Hard", "text": SHORT_STORY}).json()["id"]
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE books SET new_per_page = 1.0 WHERE id = ?", (easy_id,))
    conn.execute("UPDATE books SET new_per_page = 9.0 WHERE id = ?", (hard_id,))
    conn.commit()
    conn.close()

    titles = [bk["title"] for bk in client.get("/api/books?sort=easiest").json()]
    assert titles == ["Easy", "Hard"]


def test_list_books_limit_and_offset_paginate(client):
    for i in range(5):
        client.post("/api/books", json={"title": f"Book {i}", "text": SHORT_STORY})

    page1 = client.get("/api/books?sort=recent&limit=2&offset=0").json()
    page2 = client.get("/api/books?sort=recent&limit=2&offset=2").json()
    assert [b["title"] for b in page1] == ["Book 4", "Book 3"]
    assert [b["title"] for b in page2] == ["Book 2", "Book 1"]


def test_list_books_omitting_limit_returns_everything(client):
    for i in range(3):
        client.post("/api/books", json={"title": f"Book {i}", "text": SHORT_STORY})
    assert len(client.get("/api/books").json()) == 3


# --- Epic 24: character-addressed text windows ------------------------------

def test_get_text_returns_whole_short_book_with_absolute_total(client):
    book_id = client.post(
        "/api/books", json={"title": "Short", "text": SHORT_STORY}
    ).json()["id"]

    body = client.get(f"/api/books/{book_id}/text").json()
    assert body["offset"] == 0
    assert body["content"] == SHORT_STORY
    assert body["total_chars"] == len(SHORT_STORY)
    assert body["tokens"]
    # token offsets are relative to `content`, so they slice it directly
    tok = body["tokens"][0]
    assert body["content"][tok["s"]:tok["e"]] == tok["surface"]


def test_get_text_windows_a_long_book_and_joins_losslessly(client):
    book_id = client.post(
        "/api/books", json={"title": "Long", "text": LONG_STORY}
    ).json()["id"]

    chunks, offset, guard = [], 0, 0
    while guard < 100:
        guard += 1
        body = client.get(
            f"/api/books/{book_id}/text", params={"offset": offset, "window": 200}
        ).json()
        assert body["offset"] == offset  # requested offsets are already boundaries
        chunks.append(body["content"])
        offset = body["offset"] + len(body["content"])
        if offset >= body["total_chars"]:
            break

    assert guard > 1  # actually windowed rather than one response
    assert "".join(chunks) == LONG_STORY


def test_get_text_snaps_a_mid_sentence_offset_backwards(client):
    book_id = client.post(
        "/api/books", json={"title": "Short", "text": SHORT_STORY}
    ).json()["id"]

    mid = SHORT_STORY.index("날씨") + 3  # deliberately inside the second sentence
    body = client.get(f"/api/books/{book_id}/text", params={"offset": mid}).json()
    assert body["offset"] < mid
    # snaps to just after the previous sentence's period — the window therefore opens
    # on the whitespace before the sentence, never partway into a clause
    assert body["content"].strip().startswith("날씨")
    assert SHORT_STORY[body["offset"]:] == body["content"]


def test_get_text_clamps_window_and_offset(client):
    book_id = client.post(
        "/api/books", json={"title": "Short", "text": SHORT_STORY}
    ).json()["id"]

    past_end = client.get(
        f"/api/books/{book_id}/text", params={"offset": 10_000}
    ).json()
    assert past_end["offset"] <= len(SHORT_STORY)
    assert past_end["content"] == ""

    huge = client.get(
        f"/api/books/{book_id}/text", params={"window": 10_000_000}
    ).json()
    assert huge["content"] == SHORT_STORY


def test_get_text_highlights_saved_terms(client):
    book_id = client.post(
        "/api/books", json={"title": "Short", "text": SHORT_STORY}
    ).json()["id"]
    page = client.get(f"/api/books/{book_id}/pages/1").json()
    lemma = page["tokens"][0]["lemma"]
    client.post("/api/terms", json={"lemma": lemma, "translation": "x"})

    body = client.get(f"/api/books/{book_id}/text").json()
    assert lemma in body["terms"]
    # identical highlighting to the page endpoint it was extracted from
    assert set(body["terms"]) == set(client.get(f"/api/books/{book_id}/pages/1").json()["terms"])


def test_get_text_404s_for_unknown_book(client):
    assert client.get("/api/books/999999/text").status_code == 404


def test_patch_current_offset_round_trips(client):
    book_id = client.post(
        "/api/books", json={"title": "Long", "text": LONG_STORY}
    ).json()["id"]

    assert client.patch(f"/api/books/{book_id}", json={"current_offset": 512}).status_code == 200
    assert client.get(f"/api/books/{book_id}").json()["current_offset"] == 512
    # negative offsets are rejected by the schema, not silently stored
    assert client.patch(f"/api/books/{book_id}", json={"current_offset": -1}).status_code == 422


def test_current_offset_backfills_from_current_page(client, db_path):
    """The one-time Epic 24 migration: an existing DB's page-number positions become
    character offsets. `client` is only here to build the schema."""
    from server import db as db_module

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    book_id = conn.execute(
        "INSERT INTO books (title, source, current_page) VALUES ('B', 'paste', 3)"
    ).lastrowid
    for n, content in enumerate(["첫째다. ", "둘째다. ", "셋째다. "], start=1):
        conn.execute(
            "INSERT INTO pages (book_id, page_no, content) VALUES (?, ?, ?)",
            (book_id, n, content),
        )
    conn.commit()

    db_module._backfill_current_offset(conn)
    conn.commit()
    offset = conn.execute(
        "SELECT current_offset FROM books WHERE id = ?", (book_id,)
    ).fetchone()["current_offset"]
    # page 3 starts after pages 1 and 2
    assert offset == len("첫째다. ") + len("둘째다. ")
    conn.close()
