STORY = "그는 옷을 입고 나갔다. 날씨가 정말 좋았다! 학교에 가야 했다."


def _book(client):
    return client.post("/api/books", json={"title": "T", "text": STORY}).json()["id"]


def test_first_read_counts(client):
    book_id = _book(client)
    resp = client.post("/api/reads", json={"book_id": book_id, "page_no": 1})
    assert resp.status_code == 201
    assert resp.json() == {"counted": True}


def test_revisit_does_not_double_count(client):
    book_id = _book(client)
    client.post("/api/reads", json={"book_id": book_id, "page_no": 1})
    # Same page again (e.g. re-checking a word) — silently ignored, not counted.
    resp = client.post("/api/reads", json={"book_id": book_id, "page_no": 1})
    assert resp.status_code == 201
    assert resp.json() == {"counted": False}
    assert client.get("/api/stats").json()["totals"]["pages_week"] == 1


def test_distinct_pages_each_count_once(client):
    book_id = _book(client)
    client.post("/api/reads", json={"book_id": book_id, "page_no": 1})
    client.post("/api/reads", json={"book_id": book_id, "page_no": 2})
    assert client.get("/api/stats").json()["totals"]["pages_week"] == 2


def test_read_unknown_book_404s(client):
    resp = client.post("/api/reads", json={"book_id": 9999, "page_no": 1})
    assert resp.status_code == 404


def test_page_reads_cascade_on_book_delete(client):
    book_id = _book(client)
    client.post("/api/reads", json={"book_id": book_id, "page_no": 1})
    client.delete(f"/api/books/{book_id}")
    assert client.get("/api/stats").json()["totals"]["pages_week"] == 0
