STORY = "그는 옷을 입고 나갔다. 날씨가 정말 좋았다! 학교에 가야 했다."


def _book(client, title="T"):
    return client.post("/api/books", json={"title": title, "text": STORY}).json()["id"]


def test_first_read_counts(client):
    book_id = _book(client)
    resp = client.post("/api/reads", json={"book_id": book_id})
    assert resp.status_code == 201
    assert resp.json() == {"counted": True}


def test_same_book_again_today_does_not_double_count(client):
    book_id = _book(client)
    client.post("/api/reads", json={"book_id": book_id})
    # Every later page that day (and any revisit) is a silent no-op.
    resp = client.post("/api/reads", json={"book_id": book_id})
    assert resp.status_code == 201
    assert resp.json() == {"counted": False}
    assert client.get("/api/stats").json()["totals"]["days_read_week"] == 1


def test_two_books_the_same_day_is_still_one_day_read(client):
    """days_read_week counts *days*, not books — reading two books today is one day."""
    client.post("/api/reads", json={"book_id": _book(client, "A")})
    client.post("/api/reads", json={"book_id": _book(client, "B")})
    body = client.get("/api/stats").json()
    assert body["totals"]["days_read_week"] == 1
    # ...but the activity row for today records both books.
    assert body["activity"][0]["read"] == 2


def test_read_unknown_book_404s(client):
    resp = client.post("/api/reads", json={"book_id": 9999})
    assert resp.status_code == 404


def test_read_days_cascade_on_book_delete(client):
    book_id = _book(client)
    client.post("/api/reads", json={"book_id": book_id})
    client.delete(f"/api/books/{book_id}")
    assert client.get("/api/stats").json()["totals"]["days_read_week"] == 0
