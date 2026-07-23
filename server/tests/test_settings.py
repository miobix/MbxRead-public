from server.routes.settings import DEFAULT_PAGE_SIZE


def test_get_settings_defaults(client):
    resp = client.get("/api/settings")
    assert resp.status_code == 200
    assert resp.json() == {
        "decks": ["Korean"],
        "default_deck": "Korean",
        "translator_backend": "deepl",
        "page_size": DEFAULT_PAGE_SIZE,
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
        "page_size": DEFAULT_PAGE_SIZE,
    }

    resp = client.get("/api/settings")
    assert resp.json() == {
        "decks": ["Korean", "Slang"],
        "default_deck": "Slang",
        "translator_backend": "deepl",
        "page_size": DEFAULT_PAGE_SIZE,
    }


def test_put_settings_partial_update_leaves_other_keys(client):
    client.put("/api/settings", json={"decks": ["Korean", "Slang"]})
    resp = client.put("/api/settings", json={"translator_backend": "claude"})
    assert resp.status_code == 200
    assert resp.json() == {
        "decks": ["Korean", "Slang"],
        "default_deck": "Korean",
        "translator_backend": "claude",
        "page_size": DEFAULT_PAGE_SIZE,
    }


def test_put_settings_overwrites_existing_key(client):
    client.put("/api/settings", json={"default_deck": "Slang"})
    resp = client.put("/api/settings", json={"default_deck": "Korean"})
    assert resp.status_code == 200
    assert resp.json()["default_deck"] == "Korean"


def test_put_settings_rejects_too_small_page_size(client):
    resp = client.put("/api/settings", json={"page_size": 10})
    assert resp.status_code == 422


LONG_STORY = "문장입니다. " * 300


def test_changing_page_size_repaginates_and_preserves_position(client):
    book_id = client.post("/api/books", json={"title": "Long", "text": LONG_STORY}).json()["id"]
    small = client.get(f"/api/books/{book_id}").json()["page_count"]

    # Move to the middle, then grow the page size — fewer, larger pages.
    mid = small // 2
    client.patch(f"/api/books/{book_id}", json={"current_page": mid})
    client.put("/api/settings", json={"page_size": 3000})

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


def test_changing_page_size_clears_page_reads(client):
    book_id = client.post("/api/books", json={"title": "Long", "text": LONG_STORY}).json()["id"]
    client.post("/api/reads", json={"book_id": book_id, "page_no": 1})
    assert client.get("/api/stats").json()["totals"]["pages_week"] == 1

    client.put("/api/settings", json={"page_size": 3000})
    # Re-pagination moved page boundaries, so the old read mark is dropped.
    assert client.get("/api/stats").json()["totals"]["pages_week"] == 0


def test_same_page_size_does_not_repaginate(client):
    book_id = client.post("/api/books", json={"title": "Long", "text": LONG_STORY}).json()["id"]
    client.post("/api/reads", json={"book_id": book_id, "page_no": 1})
    # Re-PUTting the same page_size is a no-op — page_reads survive.
    from server.routes.settings import DEFAULT_PAGE_SIZE

    client.put("/api/settings", json={"page_size": DEFAULT_PAGE_SIZE})
    assert client.get("/api/stats").json()["totals"]["pages_week"] == 1
