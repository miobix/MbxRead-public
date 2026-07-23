import sqlite3

from server import anki


def _create(client, **overrides):
    body = {"lemma": "입다", "translation": "to wear", "deck": "Korean"}
    body.update(overrides)
    return client.post("/api/terms", json=body).json()


def _mock_model(monkeypatch):
    """Stub out ensure_model so a test never reaches real AnkiConnect for it."""
    monkeypatch.setattr(anki, "ensure_model", lambda: None)


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
    """New terms (Epic 21) land on the two-way model as Korean/English/Examples."""
    monkeypatch.setattr(anki, "ping", lambda: None)
    _mock_model(monkeypatch)
    deck_calls = []
    monkeypatch.setattr(anki, "create_deck", lambda deck: deck_calls.append(deck))
    add_calls = []

    def fake_add_note_model(deck, korean, english, examples):
        add_calls.append((deck, korean, english, examples))
        return 12345

    monkeypatch.setattr(anki, "add_note_model", fake_add_note_model)

    term = _create(client, sentence="오늘 옷을 입다.")
    resp = client.post("/api/anki/sync")

    assert resp.status_code == 200
    assert resp.json() == {"added": 1, "updated": 0, "failed": []}
    assert deck_calls == ["Korean"]
    # The captured reading sentence goes into Examples (card back), not the front.
    assert add_calls == [("Korean", "입다", "to wear", "오늘 옷을 입다.")]

    saved = client.get("/api/terms").json()[0]
    assert saved["id"] == term["id"]
    assert saved["anki_note_id"] == 12345
    assert saved["anki_dirty"] is False


def test_sync_korean_face_includes_extra_forms_and_examples(client, monkeypatch):
    """Epic 20/21: Korean = `lemma / form1 / form2`; Examples = clicked-in examples
    plus the reading sentence, one per line."""
    monkeypatch.setattr(anki, "ping", lambda: None)
    _mock_model(monkeypatch)
    monkeypatch.setattr(anki, "create_deck", lambda deck: None)
    add_calls = []

    def fake_add_note_model(deck, korean, english, examples):
        add_calls.append((deck, korean, english, examples))
        return 555

    monkeypatch.setattr(anki, "add_note_model", fake_add_note_model)

    _create(
        client,
        lemma="승인",
        translation="approval",
        forms=["승인서", "승인하다"],
        examples=["승인을 받다", "승인이 나다"],
        sentence="승인을 기다린다.",
    )
    resp = client.post("/api/anki/sync")

    assert resp.json() == {"added": 1, "updated": 0, "failed": []}
    assert add_calls == [
        (
            "Korean",
            "승인 / 승인서 / 승인하다",
            "approval",
            "승인을 받다<br>승인이 나다<br>승인을 기다린다.",
        )
    ]


def test_new_model_templates_keep_examples_off_both_fronts(monkeypatch):
    """Anti-spoiler guarantee: `Examples` appears on neither card's Front."""
    for tmpl in anki._CARD_TEMPLATES:
        assert "{{Examples}}" not in tmpl["Front"]
        assert "{{Examples}}" in tmpl["Back"]


def test_ensure_model_is_idempotent(monkeypatch):
    calls = []

    def fake_invoke(action, **params):
        calls.append((action, params))
        if action == "modelNames":
            return [anki.MODEL_NAME]  # already present
        return None

    monkeypatch.setattr(anki, "_invoke", fake_invoke)
    anki.ensure_model()

    assert [c[0] for c in calls] == ["modelNames"]  # no createModel call


def test_ensure_model_creates_when_absent(monkeypatch):
    calls = []

    def fake_invoke(action, **params):
        calls.append((action, params))
        if action == "modelNames":
            return ["Basic"]
        return None

    monkeypatch.setattr(anki, "_invoke", fake_invoke)
    anki.ensure_model()

    actions = [c[0] for c in calls]
    assert actions == ["modelNames", "createModel"]
    created = calls[1][1]
    assert created["modelName"] == anki.MODEL_NAME
    assert created["inOrderFields"] == ["Korean", "English", "Examples"]


def test_sync_updates_new_model_term(client, monkeypatch):
    monkeypatch.setattr(anki, "ping", lambda: None)
    _mock_model(monkeypatch)
    monkeypatch.setattr(anki, "create_deck", lambda deck: None)
    monkeypatch.setattr(anki, "add_note_model", lambda deck, k, e, x: 999)

    term = _create(client)
    first = client.post("/api/anki/sync")
    assert first.json() == {"added": 1, "updated": 0, "failed": []}

    client.patch(f"/api/terms/{term['id']}", json={"translation": "to put on"})

    update_model_calls = []
    monkeypatch.setattr(
        anki,
        "update_note_model",
        lambda note_id, k, e, x: update_model_calls.append((note_id, k, e, x)),
    )
    legacy_calls = []
    monkeypatch.setattr(
        anki, "update_note_fields", lambda *a: legacy_calls.append(a)
    )

    second = client.post("/api/anki/sync")
    assert second.json() == {"added": 0, "updated": 1, "failed": []}
    assert update_model_calls == [(999, "입다", "to put on", "")]
    assert legacy_calls == []  # a two-way note never touches the Basic path

    assert client.get("/api/terms").json()[0]["anki_dirty"] is False


def test_sync_preserves_legacy_basic_notes(client, db_path, monkeypatch):
    """A note synced before Epic 21 (anki_model NULL) keeps the Front/Back path so
    its SRS history is preserved — no add, no two-way update."""
    monkeypatch.setattr(anki, "ping", lambda: None)
    _mock_model(monkeypatch)
    monkeypatch.setattr(anki, "create_deck", lambda deck: None)

    # Simulate a legacy synced Basic note directly in the DB.
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO terms (lemma, translation, sentence, deck, anki_note_id, "
        "anki_model, anki_dirty) VALUES ('입다','to wear','오늘 입다.','Korean',777,NULL,1)"
    )
    conn.commit()
    conn.close()

    legacy_calls = []
    monkeypatch.setattr(
        anki, "update_note_fields", lambda *a: legacy_calls.append(a)
    )
    model_calls = []
    monkeypatch.setattr(anki, "update_note_model", lambda *a: model_calls.append(a))
    add_calls = []
    monkeypatch.setattr(anki, "add_note_model", lambda *a: add_calls.append(a))

    resp = client.post("/api/anki/sync")
    assert resp.json() == {"added": 0, "updated": 1, "failed": []}
    # Front = lemma (+forms), Back = translation + italic sentence — the Epic 20 shape.
    assert legacy_calls == [(777, "입다", "to wear<br><br><i>오늘 입다.</i>")]
    assert model_calls == []
    assert add_calls == []


def test_sync_isolates_per_note_failure(client, monkeypatch):
    monkeypatch.setattr(anki, "ping", lambda: None)
    _mock_model(monkeypatch)
    monkeypatch.setattr(anki, "create_deck", lambda deck: None)

    def fake_add_note_model(deck, korean, english, examples):
        if korean == "가다":
            raise anki.AnkiError("cannot create note because it is a duplicate")
        return 111

    monkeypatch.setattr(anki, "add_note_model", fake_add_note_model)

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
    _mock_model(monkeypatch)
    monkeypatch.setattr(anki, "create_deck", lambda deck: None)
    add_calls = []
    monkeypatch.setattr(anki, "add_note_model", lambda *a: add_calls.append(a))

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
