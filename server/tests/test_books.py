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
            "id", "title", "source", "current_page", "page_count", "created",
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
