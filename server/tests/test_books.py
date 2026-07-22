import sqlite3

from server.paging import split_pages

SHORT_STORY = "그는 옷을 입고 나갔다. 날씨가 정말 좋았다! 학교에 가야 했다."
LONG_STORY = "문장입니다. " * 300  # well over the 1500-char default page size


def test_create_book_splits_into_pages_matching_paging_util(client):
    resp = client.post("/api/books", json={"title": "Long", "text": LONG_STORY})
    assert resp.status_code == 201
    body = resp.json()
    expected_pages = split_pages(LONG_STORY)
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
        "입다": {"id": 1, "translation": "to wear", "status": "learning", "deck": "Korean"}
    }


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
        }


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
