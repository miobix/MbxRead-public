from server import anki


def _create(client, **overrides):
    body = {"lemma": "입다", "translation": "to wear", "deck": "Korean"}
    body.update(overrides)
    return client.post("/api/terms", json=body).json()


def test_sync_down_returns_503_and_touches_nothing(client, monkeypatch):
    def raise_error():
        raise anki.AnkiError("Anki is not running (or AnkiConnect missing)")

    monkeypatch.setattr(anki, "ping", raise_error)
    calls = []
    monkeypatch.setattr(anki, "add_note", lambda *a, **k: calls.append((a, k)))

    term = _create(client)
    resp = client.post("/api/anki/sync")

    assert resp.status_code == 503
    assert resp.json() == {"error": "Anki is not running (or AnkiConnect missing)"}
    assert calls == []
    assert client.get("/api/terms").json()[0]["id"] == term["id"]
    assert client.get("/api/terms").json()[0]["anki_note_id"] is None


def test_sync_adds_new_learning_term(client, monkeypatch):
    monkeypatch.setattr(anki, "ping", lambda: None)
    deck_calls = []
    monkeypatch.setattr(anki, "create_deck", lambda deck: deck_calls.append(deck))
    add_calls = []

    def fake_add_note(deck, front, back):
        add_calls.append((deck, front, back))
        return 12345

    monkeypatch.setattr(anki, "add_note", fake_add_note)

    term = _create(client, sentence="오늘 옷을 입다.")
    resp = client.post("/api/anki/sync")

    assert resp.status_code == 200
    assert resp.json() == {"added": 1, "updated": 0, "failed": []}
    assert deck_calls == ["Korean"]
    assert add_calls == [("Korean", "입다", "to wear<br><br><i>오늘 옷을 입다.</i>")]

    saved = client.get("/api/terms").json()[0]
    assert saved["id"] == term["id"]
    assert saved["anki_note_id"] == 12345
    assert saved["anki_dirty"] is False


def test_sync_front_includes_extra_forms(client, monkeypatch):
    """Epic 20: the card's Korean face is `lemma / form1 / form2`."""
    monkeypatch.setattr(anki, "ping", lambda: None)
    monkeypatch.setattr(anki, "create_deck", lambda deck: None)
    add_calls = []

    def fake_add_note(deck, front, back):
        add_calls.append((deck, front, back))
        return 555

    monkeypatch.setattr(anki, "add_note", fake_add_note)

    _create(client, lemma="승인", translation="approval", forms=["승인서", "승인하다"])
    resp = client.post("/api/anki/sync")

    assert resp.json() == {"added": 1, "updated": 0, "failed": []}
    assert add_calls == [("Korean", "승인 / 승인서 / 승인하다", "approval")]


def test_sync_updates_dirty_term_without_duplicating(client, monkeypatch):
    monkeypatch.setattr(anki, "ping", lambda: None)
    monkeypatch.setattr(anki, "create_deck", lambda deck: None)
    monkeypatch.setattr(anki, "add_note", lambda deck, front, back: 999)

    term = _create(client)
    first = client.post("/api/anki/sync")
    assert first.json() == {"added": 1, "updated": 0, "failed": []}

    client.patch(f"/api/terms/{term['id']}", json={"translation": "to put on"})

    update_calls = []

    def fake_update(note_id, front, back):
        update_calls.append((note_id, front, back))

    monkeypatch.setattr(anki, "update_note_fields", fake_update)
    add_calls = []
    monkeypatch.setattr(anki, "add_note", lambda deck, front, back: add_calls.append(1))

    second = client.post("/api/anki/sync")
    assert second.status_code == 200
    assert second.json() == {"added": 0, "updated": 1, "failed": []}
    assert update_calls == [(999, "입다", "to put on")]
    assert add_calls == []

    saved = client.get("/api/terms").json()[0]
    assert saved["anki_dirty"] is False


def test_sync_isolates_per_note_failure(client, monkeypatch):
    monkeypatch.setattr(anki, "ping", lambda: None)
    monkeypatch.setattr(anki, "create_deck", lambda deck: None)

    def fake_add_note(deck, front, back):
        if front == "가다":
            raise anki.AnkiError("cannot create note because it is a duplicate")
        return 111

    monkeypatch.setattr(anki, "add_note", fake_add_note)

    good = _create(client, lemma="입다")
    bad = _create(client, lemma="가다")

    resp = client.post("/api/anki/sync")
    assert resp.status_code == 200
    body = resp.json()
    assert body["added"] == 1
    assert body["failed"] == [
        {"lemma": "가다", "error": "cannot create note because it is a duplicate"}
    ]

    terms_by_id = {t["id"]: t for t in client.get("/api/terms").json()}
    assert terms_by_id[good["id"]]["anki_note_id"] == 111
    assert terms_by_id[bad["id"]]["anki_note_id"] is None


def test_sync_ignores_known_and_ignored_terms(client, monkeypatch):
    monkeypatch.setattr(anki, "ping", lambda: None)
    monkeypatch.setattr(anki, "create_deck", lambda deck: None)
    add_calls = []
    monkeypatch.setattr(anki, "add_note", lambda *a: add_calls.append(a))

    _create(client, lemma="아는단어", status="known")
    _create(client, lemma="무시단어", status="ignored")

    resp = client.post("/api/anki/sync")
    assert resp.json() == {"added": 0, "updated": 0, "failed": []}
    assert add_calls == []


def test_invoke_wraps_transport_errors(monkeypatch):
    import httpx

    def raise_connect_error(*a, **k):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(httpx, "post", raise_connect_error)

    try:
        anki.ping()
        assert False, "expected AnkiError"
    except anki.AnkiError as e:
        assert "Anki is not running" in str(e)
