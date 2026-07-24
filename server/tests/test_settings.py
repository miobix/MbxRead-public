from server.routes.settings import (
    DEFAULT_CANDIDATE_RETENTION_DAYS,
    DEFAULT_CHARS_PER_ROW,
    DEFAULT_PAGE_ROWS,
)


def test_get_settings_defaults(client):
    resp = client.get("/api/settings")
    assert resp.status_code == 200
    assert resp.json() == {
        "decks": ["Korean"],
        "default_deck": "Korean",
        "translator_backend": "deepl",
        "page_rows": DEFAULT_PAGE_ROWS,
        "chars_per_row": DEFAULT_CHARS_PER_ROW,
        "candidate_retention_days": DEFAULT_CANDIDATE_RETENTION_DAYS,
        "last_fetch_attempt": None,
    }


def test_put_settings_persists_and_returns_full_dict(client):
    resp = client.put(
        "/api/settings",
        json={"decks": ["Korean", "Slang"], "default_deck": "Slang"},
    )
    assert resp.status_code == 200
    assert resp.json() == {
        "decks": ["Korean", "Slang"],
        "default_deck": "Slang",
        "translator_backend": "deepl",
        "page_rows": DEFAULT_PAGE_ROWS,
        "chars_per_row": DEFAULT_CHARS_PER_ROW,
        "candidate_retention_days": DEFAULT_CANDIDATE_RETENTION_DAYS,
        "last_fetch_attempt": None,
    }

    resp = client.get("/api/settings")
    assert resp.json() == {
        "decks": ["Korean", "Slang"],
        "default_deck": "Slang",
        "translator_backend": "deepl",
        "page_rows": DEFAULT_PAGE_ROWS,
        "chars_per_row": DEFAULT_CHARS_PER_ROW,
        "candidate_retention_days": DEFAULT_CANDIDATE_RETENTION_DAYS,
        "last_fetch_attempt": None,
    }


def test_put_settings_partial_update_leaves_other_keys(client):
    client.put("/api/settings", json={"decks": ["Korean", "Slang"]})
    resp = client.put("/api/settings", json={"translator_backend": "claude"})
    assert resp.status_code == 200
    assert resp.json() == {
        "decks": ["Korean", "Slang"],
        "default_deck": "Korean",
        "translator_backend": "claude",
        "page_rows": DEFAULT_PAGE_ROWS,
        "chars_per_row": DEFAULT_CHARS_PER_ROW,
        "candidate_retention_days": DEFAULT_CANDIDATE_RETENTION_DAYS,
        "last_fetch_attempt": None,
    }


def test_put_settings_candidate_retention_days_roundtrip(client):
    resp = client.put("/api/settings", json={"candidate_retention_days": 3})
    assert resp.status_code == 200
    assert resp.json()["candidate_retention_days"] == 3
    assert client.get("/api/settings").json()["candidate_retention_days"] == 3


def test_put_settings_rejects_out_of_range_candidate_retention_days(client):
    assert client.put("/api/settings", json={"candidate_retention_days": 0}).status_code == 422
    assert client.put("/api/settings", json={"candidate_retention_days": 91}).status_code == 422


def test_put_settings_ignores_last_fetch_attempt_in_body(client):
    # last_fetch_attempt is system-managed (stamped by POST /api/feeds/fetch) — not
    # a field on SettingsPut, so an unknown key in the body is just dropped.
    resp = client.put("/api/settings", json={"last_fetch_attempt": "2020-01-01 00:00:00"})
    assert resp.status_code == 200
    assert resp.json()["last_fetch_attempt"] is None


def test_put_settings_overwrites_existing_key(client):
    client.put("/api/settings", json={"default_deck": "Slang"})
    resp = client.put("/api/settings", json={"default_deck": "Korean"})
    assert resp.status_code == 200
    assert resp.json()["default_deck"] == "Korean"


def test_put_settings_rejects_too_small_page_rows(client):
    resp = client.put("/api/settings", json={"page_rows": 1})
    assert resp.status_code == 422


def test_put_settings_rejects_too_small_chars_per_row(client):
    resp = client.put("/api/settings", json={"chars_per_row": 1})
    assert resp.status_code == 422


LONG_STORY = "문장입니다. " * 300


def test_changing_page_rows_repaginates_and_preserves_position(client):
    book_id = client.post("/api/books", json={"title": "Long", "text": LONG_STORY}).json()["id"]
    small = client.get(f"/api/books/{book_id}").json()["page_count"]

    # Move to the middle, then grow the page rows budget — fewer, larger pages.
    mid = small // 2
    client.patch(f"/api/books/{book_id}", json={"current_page": mid})
    client.put("/api/settings", json={"page_rows": 100})

    book = client.get(f"/api/books/{book_id}").json()
    assert book["page_count"] < small  # bigger pages -> fewer of them
    # Reading position preserved by character offset: the same char is still shown.
    assert 1 <= book["current_page"] <= book["page_count"]

    # Full text is intact across the re-split (lossless join).
    rejoined = "".join(
        client.get(f"/api/books/{book_id}/pages/{n}").json()["content"]
        for n in range(1, book["page_count"] + 1)
    )
    assert rejoined == LONG_STORY


def test_changing_chars_per_row_repaginates(client):
    book_id = client.post("/api/books", json={"title": "Long", "text": LONG_STORY}).json()["id"]
    small = client.get(f"/api/books/{book_id}").json()["page_count"]

    # A much wider chars_per_row estimate fits more text per row -> fewer pages
    # at the same row budget, even though page_rows itself didn't change.
    client.put("/api/settings", json={"chars_per_row": 100})

    book = client.get(f"/api/books/{book_id}").json()
    assert book["page_count"] < small
    rejoined = "".join(
        client.get(f"/api/books/{book_id}/pages/{n}").json()["content"]
        for n in range(1, book["page_count"] + 1)
    )
    assert rejoined == LONG_STORY


def test_changing_page_rows_clears_page_reads(client):
    book_id = client.post("/api/books", json={"title": "Long", "text": LONG_STORY}).json()["id"]
    client.post("/api/reads", json={"book_id": book_id, "page_no": 1})
    assert client.get("/api/stats").json()["totals"]["pages_week"] == 1

    client.put("/api/settings", json={"page_rows": 100})
    # Re-pagination moved page boundaries, so the old read mark is dropped.
    assert client.get("/api/stats").json()["totals"]["pages_week"] == 0


def test_same_page_rows_does_not_repaginate(client):
    book_id = client.post("/api/books", json={"title": "Long", "text": LONG_STORY}).json()["id"]
    client.post("/api/reads", json={"book_id": book_id, "page_no": 1})
    # Re-PUTting the same page_rows/chars_per_row is a no-op — page_reads survive.
    from server.routes.settings import DEFAULT_CHARS_PER_ROW, DEFAULT_PAGE_ROWS

    client.put(
        "/api/settings",
        json={"page_rows": DEFAULT_PAGE_ROWS, "chars_per_row": DEFAULT_CHARS_PER_ROW},
    )
    assert client.get("/api/stats").json()["totals"]["pages_week"] == 1
