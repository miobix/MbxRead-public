from server import anki


def _create(client, **overrides):
    body = {"lemma": "입다", "translation": "to wear", "deck": "Korean"}
    body.update(overrides)
    return client.post("/api/terms", json=body).json()


def _mock_model(monkeypatch):
    """Stub out ensure_model/ensure_hanja_model so a test never reaches real
    AnkiConnect for either."""
    monkeypatch.setattr(anki, "ensure_model", lambda: None)
    monkeypatch.setattr(anki, "ensure_hanja_model", lambda: None)
    monkeypatch.setattr(anki, "move_note_to_deck", lambda note_id, deck: None)
    monkeypatch.setattr(anki, "min_intervals", lambda note_ids: {})


def test_sync_down_returns_503_and_touches_nothing(client, monkeypatch):
    def raise_error():
        raise anki.AnkiError("Anki is not running (or AnkiConnect missing)")

    monkeypatch.setattr(anki, "ping", raise_error)
    calls = []
    monkeypatch.setattr(anki, "add_note_model", lambda *a, **k: calls.append((a, k)))

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
    assert resp.json() == {"added": 1, "updated": 0, "failed": [], "promoted": 0}
    assert deck_calls == ["Korean"]
    # The captured reading sentence goes into Examples (card back), not the front.
    assert add_calls == [("Korean", "입다", "to wear", "오늘 옷을 입다.")]

    saved = client.get("/api/terms").json()[0]
    assert saved["id"] == term["id"]
    assert saved["anki_note_id"] == 12345
    assert saved["anki_dirty"] is False


def test_sync_korean_face_stacks_extra_forms_legacy_back(client, monkeypatch):
    """Epic 20: forms still render on the Korean face. Epic 22: with 2+ front
    entries the stack is numbered — but with no back_items at all (never touched
    by the structured card builder), English/Examples still render exactly as
    they did before this epic (flat translation, the old `examples` column)."""
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
        forms=[{"text": "승인서", "kind": "manual"}, {"text": "승인하다", "kind": "manual"}],
        examples=["승인을 받다", "승인이 나다"],
        sentence="승인을 기다린다.",
    )
    resp = client.post("/api/anki/sync")

    assert resp.json() == {"added": 1, "updated": 0, "failed": [], "promoted": 0}
    assert add_calls == [
        (
            "Korean",
            "1. 승인<br>2. 승인서<br>3. 승인하다",
            "approval",
            "승인을 받다<br>승인이 나다<br>승인을 기다린다.",
        )
    ]


def test_sync_single_dict_sense_has_no_label(client, monkeypatch):
    """Epic 22: one front entry (just the lemma) with exactly one back item is
    still the simple, unlabeled case — the common one-word-one-meaning card."""
    monkeypatch.setattr(anki, "ping", lambda: None)
    _mock_model(monkeypatch)
    monkeypatch.setattr(anki, "create_deck", lambda deck: None)
    add_calls = []
    monkeypatch.setattr(
        anki, "add_note_model", lambda deck, k, e, x: (add_calls.append((deck, k, e, x)), 1)[1]
    )

    _create(
        client,
        lemma="입다",
        sentence="옷을 입다.",
        back_items=[{"group": "", "kind": "dict", "text": "to wear", "korean_def": "옷을 몸에 걸치다"}],
    )
    client.post("/api/anki/sync")

    # Blank line between the captured sentence and the definition block.
    assert add_calls == [("Korean", "입다", "to wear", "옷을 입다.<br><br>옷을 몸에 걸치다")]


def test_sync_multi_sense_labels_back_and_examples(client, monkeypatch):
    """Epic 22: a single front entry with 2+ back items letters them a/b (no
    front number needed — there's only one front entry), and the same labels
    appear in Examples next to each sense's Korean definition."""
    monkeypatch.setattr(anki, "ping", lambda: None)
    _mock_model(monkeypatch)
    monkeypatch.setattr(anki, "create_deck", lambda deck: None)
    add_calls = []
    monkeypatch.setattr(
        anki, "add_note_model", lambda deck, k, e, x: (add_calls.append((deck, k, e, x)), 1)[1]
    )

    _create(
        client,
        lemma="타다",
        back_items=[
            {"group": "", "kind": "dict", "text": "to ride", "korean_def": "탈것에 몸을 얹다"},
            {"group": "", "kind": "dict", "text": "to burn", "korean_def": "불이 붙다"},
        ],
    )
    client.post("/api/anki/sync")

    assert add_calls == [
        (
            "Korean",
            "타다",
            "a. to ride<br>b. to burn",
            "a. 탈것에 몸을 얹다<br>b. 불이 붙다",
        )
    ]


def test_sync_multi_form_labels_correlate_front_and_back(client, monkeypatch):
    """Epic 22: with 2+ front entries, a front entry with a single back item gets
    a bare number, one with several gets number+letter — proving which word each
    Back/Examples line came from."""
    monkeypatch.setattr(anki, "ping", lambda: None)
    _mock_model(monkeypatch)
    monkeypatch.setattr(anki, "create_deck", lambda deck: None)
    add_calls = []
    monkeypatch.setattr(
        anki, "add_note_model", lambda deck, k, e, x: (add_calls.append((deck, k, e, x)), 1)[1]
    )

    _create(
        client,
        lemma="승인",
        forms=[{"text": "승인서", "kind": "dict"}],
        back_items=[
            {"group": "", "kind": "dict", "text": "approval", "korean_def": "허가함"},
            {"group": "", "kind": "translate", "text": "authorization"},
            {"group": "승인서", "kind": "dict", "text": "approval document"},
        ],
    )
    client.post("/api/anki/sync")

    assert add_calls == [
        (
            "Korean",
            "1. 승인<br>2. 승인서",
            "1a. approval<br>1b. authorization<br>2. approval document",
            "1a. 허가함",
        )
    ]


def test_sync_notes_free_text_appended_after_definitions(client, monkeypatch):
    monkeypatch.setattr(anki, "ping", lambda: None)
    _mock_model(monkeypatch)
    monkeypatch.setattr(anki, "create_deck", lambda deck: None)
    add_calls = []
    monkeypatch.setattr(
        anki, "add_note_model", lambda deck, k, e, x: (add_calls.append((deck, k, e, x)), 1)[1]
    )

    _create(
        client,
        lemma="입다",
        sentence="옷을 입다.",
        notes="freely typed context",
        back_items=[{"group": "", "kind": "dict", "text": "to wear", "korean_def": "옷을 몸에 걸치다"}],
    )
    client.post("/api/anki/sync")

    assert add_calls == [
        (
            "Korean",
            "입다",
            "to wear",
            "옷을 입다.<br><br>옷을 몸에 걸치다<br><br>freely typed context",
        )
    ]


def test_sync_adds_new_hanja_term(client, monkeypatch):
    """Epic 25: a term with a hanja spelling routes to the hanja model, not the
    two-way one, and stamps anki_model accordingly."""
    monkeypatch.setattr(anki, "ping", lambda: None)
    _mock_model(monkeypatch)
    monkeypatch.setattr(anki, "create_deck", lambda deck: None)

    model_add_calls = []
    monkeypatch.setattr(anki, "add_note_model", lambda *a: model_add_calls.append(a))
    hanja_add_calls = []

    def fake_add_note_hanja(deck, korean, hanja, english, korean_def):
        hanja_add_calls.append((deck, korean, hanja, english, korean_def))
        return 4242

    monkeypatch.setattr(anki, "add_note_hanja", fake_add_note_hanja)

    term = _create(
        client,
        lemma="제일",
        deck="한자어",
        hanja=["第一"],
        back_items=[{"group": "第一", "kind": "dict", "text": "the most", "korean_def": "가장"}],
        notes="homograph of 祭日",
    )
    resp = client.post("/api/anki/sync")

    assert resp.json() == {"added": 1, "updated": 0, "failed": [], "promoted": 0}
    assert hanja_add_calls == [
        ("한자어", "제일", "第一", "the most", "가장<br><br>homograph of 祭日")
    ]
    assert model_add_calls == []

    saved = client.get("/api/terms").json()[0]
    assert saved["id"] == term["id"]
    assert saved["anki_note_id"] == 4242
    assert saved["anki_dirty"] is False


def test_sync_updates_dirty_hanja_term(client, monkeypatch):
    monkeypatch.setattr(anki, "ping", lambda: None)
    _mock_model(monkeypatch)
    monkeypatch.setattr(anki, "create_deck", lambda deck: None)
    monkeypatch.setattr(anki, "add_note_hanja", lambda *a: 9001)

    term = _create(client, lemma="제일", translation="the most", deck="한자어", hanja=["第一"])
    first = client.post("/api/anki/sync")
    assert first.json() == {"added": 1, "updated": 0, "failed": [], "promoted": 0}

    client.patch(f"/api/terms/{term['id']}", json={"hanja": ["祭日"]})

    hanja_update_calls = []
    monkeypatch.setattr(
        anki,
        "update_note_hanja",
        lambda note_id, k, h, e, kd: hanja_update_calls.append((note_id, k, h, e, kd)),
    )
    model_update_calls = []
    monkeypatch.setattr(anki, "update_note_model", lambda *a: model_update_calls.append(a))

    second = client.post("/api/anki/sync")
    assert second.json() == {"added": 0, "updated": 1, "failed": [], "promoted": 0}
    assert hanja_update_calls == [(9001, "제일", "祭日", "the most", "")]
    assert model_update_calls == []

    assert client.get("/api/terms").json()[0]["anki_dirty"] is False


def test_sync_renders_multi_sense_hanja_term(client, monkeypatch):
    """Epic 26: one lemma, several hanja. The Hanja field is a numbered stack and
    the English labels use the same numbers, so each meaning names its spelling."""
    monkeypatch.setattr(anki, "ping", lambda: None)
    _mock_model(monkeypatch)
    monkeypatch.setattr(anki, "create_deck", lambda deck: None)
    hanja_add_calls = []
    monkeypatch.setattr(
        anki,
        "add_note_hanja",
        lambda *a: (hanja_add_calls.append(a), 7)[1],
    )

    _create(
        client,
        lemma="시장",
        deck="한자어",
        hanja=["市場", "市長"],
        back_items=[
            {"group": "市場", "kind": "dict", "text": "market", "korean_def": "물건을 사고파는 곳"},
            {"group": "市長", "kind": "dict", "text": "mayor", "korean_def": "시의 우두머리"},
        ],
    )
    client.post("/api/anki/sync")

    assert hanja_add_calls == [
        (
            "한자어",
            "시장",
            "1. 市場<br>2. 市長",
            "1. market<br>2. mayor",
            "1. 물건을 사고파는 곳<br>2. 시의 우두머리",
        )
    ]


def test_sync_folds_senseless_back_items_into_the_first_sense(client, monkeypatch):
    """A chip whose group names no sense (a pre-Epic-26 lemma group that escaped the
    backfill) still reaches the card rather than vanishing from it."""
    monkeypatch.setattr(anki, "ping", lambda: None)
    _mock_model(monkeypatch)
    monkeypatch.setattr(anki, "create_deck", lambda deck: None)
    hanja_add_calls = []
    monkeypatch.setattr(anki, "add_note_hanja", lambda *a: (hanja_add_calls.append(a), 7)[1])

    _create(
        client,
        lemma="제일",
        deck="한자어",
        hanja=["第一"],
        back_items=[{"group": "", "kind": "dict", "text": "the most", "korean_def": "가장"}],
    )
    client.post("/api/anki/sync")

    assert hanja_add_calls == [("한자어", "제일", "第一", "the most", "가장")]


def test_sync_hanja_less_term_still_routes_through_two_way_model(client, monkeypatch):
    """A term with no hanja (the common reading-flow case) is untouched by Epic
    25 — it still syncs on the two-way model exactly as before."""
    monkeypatch.setattr(anki, "ping", lambda: None)
    _mock_model(monkeypatch)
    monkeypatch.setattr(anki, "create_deck", lambda deck: None)
    model_add_calls = []
    monkeypatch.setattr(anki, "add_note_model", lambda *a: (model_add_calls.append(a), 1)[1])
    hanja_add_calls = []
    monkeypatch.setattr(anki, "add_note_hanja", lambda *a: hanja_add_calls.append(a))

    term = _create(client)
    resp = client.post("/api/anki/sync")

    assert resp.json() == {"added": 1, "updated": 0, "failed": [], "promoted": 0}
    assert hanja_add_calls == []
    assert len(model_add_calls) == 1

    saved = client.get("/api/terms").json()[0]
    assert saved["id"] == term["id"]
    assert saved["hanja"] == []


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


def test_hanja_model_templates_pair_korean_and_hanja_on_front(monkeypatch):
    """Korean and Hanja sit together on the Front — the hanja disambiguates
    homographs (e.g. 제일 祭日 vs 第一), so it can't be the thing under test."""
    for tmpl in anki._HANJA_CARD_TEMPLATES:
        assert "{{Korean}}" in tmpl["Front"]
        assert "{{Hanja}}" in tmpl["Front"]


def test_ensure_hanja_model_is_idempotent(monkeypatch):
    calls = []

    def fake_invoke(action, **params):
        calls.append((action, params))
        if action == "modelNames":
            return [anki.HANJA_MODEL_NAME]  # already present
        return None

    monkeypatch.setattr(anki, "_invoke", fake_invoke)
    anki.ensure_hanja_model()

    assert [c[0] for c in calls] == ["modelNames"]  # no createModel call


def test_ensure_hanja_model_creates_when_absent(monkeypatch):
    calls = []

    def fake_invoke(action, **params):
        calls.append((action, params))
        if action == "modelNames":
            return ["Basic"]
        return None

    monkeypatch.setattr(anki, "_invoke", fake_invoke)
    anki.ensure_hanja_model()

    actions = [c[0] for c in calls]
    assert actions == ["modelNames", "createModel"]
    created = calls[1][1]
    assert created["modelName"] == anki.HANJA_MODEL_NAME
    assert created["inOrderFields"] == ["Korean", "Hanja", "English", "KoreanDef"]


def test_sync_updates_new_model_term(client, monkeypatch):
    monkeypatch.setattr(anki, "ping", lambda: None)
    _mock_model(monkeypatch)
    monkeypatch.setattr(anki, "create_deck", lambda deck: None)
    monkeypatch.setattr(anki, "add_note_model", lambda deck, k, e, x: 999)

    term = _create(client)
    first = client.post("/api/anki/sync")
    assert first.json() == {"added": 1, "updated": 0, "failed": [], "promoted": 0}

    client.patch(f"/api/terms/{term['id']}", json={"translation": "to put on"})

    update_model_calls = []
    monkeypatch.setattr(
        anki,
        "update_note_model",
        lambda note_id, k, e, x: update_model_calls.append((note_id, k, e, x)),
    )

    second = client.post("/api/anki/sync")
    assert second.json() == {"added": 0, "updated": 1, "failed": [], "promoted": 0}
    assert update_model_calls == [(999, "입다", "to put on", "")]

    assert client.get("/api/terms").json()[0]["anki_dirty"] is False


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
    assert resp.json() == {"added": 0, "updated": 0, "failed": [], "promoted": 0}
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


def test_note_payloads_carry_model_fields_and_tag(monkeypatch):
    calls = []
    monkeypatch.setattr(anki, "_invoke", lambda action, **p: calls.append((action, p)) or 5)

    assert anki.add_note_hanja("한자어", "제일", "第一", "the most", "가장") == 5
    anki.update_note_model(9, "입다", "to wear", "")

    add, update = calls
    assert add == ("addNote", {"note": {
        "deckName": "한자어", "modelName": anki.HANJA_MODEL_NAME,
        "fields": {"Korean": "제일", "Hanja": "第一", "English": "the most", "KoreanDef": "가장"},
        "tags": ["korean-reader"], "options": {"allowDuplicate": False},
    }})
    assert update == ("updateNoteFields", {"note": {
        "id": 9, "fields": {"Korean": "입다", "English": "to wear", "Examples": ""},
    }})


def test_sync_converted_reading_term_adds_a_hanja_note_carrying_the_sentence(client, monkeypatch):
    """Epic 27: a term converted from a reading save is new to Anki again, routes to the
    hanja model, and its book sentence lands in KoreanDef."""
    monkeypatch.setattr(anki, "ping", lambda: None)
    _mock_model(monkeypatch)
    monkeypatch.setattr(anki, "create_deck", lambda deck: None)
    calls = []

    def fake_add_note_hanja(deck, korean, hanja, english, korean_def):
        calls.append((deck, korean, hanja, english, korean_def))
        return 5150

    monkeypatch.setattr(anki, "add_note_hanja", fake_add_note_hanja)
    monkeypatch.setattr(anki, "add_note_model", lambda *a: calls.append("two-way"))

    term = _create(client, lemma="입다", deck="Korean", sentence="그는 옷을 입었다.")
    resp = client.post(
        f"/api/terms/{term['id']}/convert-to-hanja",
        json={
            "hanja": "着用",
            "deck": "한자어",
            "back_items": [{"group": "", "kind": "dict", "text": "wear", "korean_def": "옷을 걸치다."}],
        },
    )
    assert resp.status_code == 200
    assert client.post("/api/anki/sync").json() == {"added": 1, "updated": 0, "failed": [], "promoted": 0}
    assert calls == [("한자어", "입다", "着用", "wear", "그는 옷을 입었다.<br><br>옷을 걸치다.")]


def test_sync_moves_a_dirty_terms_cards_to_its_deck(client, monkeypatch):
    monkeypatch.setattr(anki, "ping", lambda: None)
    _mock_model(monkeypatch)
    monkeypatch.setattr(anki, "create_deck", lambda deck: None)
    monkeypatch.setattr(anki, "add_note_model", lambda *a: 4242)
    monkeypatch.setattr(anki, "update_note_model", lambda *a: None)
    moves = []
    monkeypatch.setattr(anki, "move_note_to_deck", lambda note_id, deck: moves.append((note_id, deck)))

    term = _create(client)
    client.post("/api/anki/sync")
    assert moves == []

    client.patch(f"/api/terms/{term['id']}", json={"deck": "Other"})
    assert client.post("/api/anki/sync").json() == {"added": 0, "updated": 1, "failed": [], "promoted": 0}
    assert moves == [(4242, "Other")]


def test_sync_readds_a_reading_term_moved_to_the_hanja_deck_as_a_hanja_note(client, monkeypatch):
    """The popover path: deck changed to 한자어 and hanja added on a synced 2-way term."""
    monkeypatch.setattr(anki, "ping", lambda: None)
    _mock_model(monkeypatch)
    monkeypatch.setattr(anki, "create_deck", lambda deck: None)
    monkeypatch.setattr(anki, "add_note_model", lambda *a: 4242)
    term = _create(client, lemma="풍경", translation="scenery")
    client.post("/api/anki/sync")

    client.patch(f"/api/terms/{term['id']}", json={"deck": "한자어", "hanja": ["風景"]})
    hanja_adds = []
    monkeypatch.setattr(anki, "add_note_hanja", lambda *a: (hanja_adds.append(a), 9001)[1])
    model_updates = []
    monkeypatch.setattr(anki, "update_note_model", lambda *a: model_updates.append(a))

    assert client.post("/api/anki/sync").json() == {"added": 1, "updated": 0, "failed": [], "promoted": 0}
    assert hanja_adds == [("한자어", "풍경", "風景", "scenery", "")]
    assert model_updates == []
    saved = client.get("/api/terms").json()[0]
    assert saved["anki_note_id"] == 9001
    assert saved["anki_dirty"] is False

    assert client.post("/api/anki/sync").json() == {"added": 0, "updated": 0, "failed": [], "promoted": 0}


def test_sync_leaves_a_hanja_bearing_term_outside_the_hanja_deck_on_its_note(client, monkeypatch):
    monkeypatch.setattr(anki, "ping", lambda: None)
    _mock_model(monkeypatch)
    monkeypatch.setattr(anki, "create_deck", lambda deck: None)
    monkeypatch.setattr(anki, "add_note_model", lambda *a: 4242)
    term = _create(client, lemma="자연계", translation="nature")
    client.post("/api/anki/sync")
    client.patch(f"/api/terms/{term['id']}", json={"hanja": ["自然界"]})
    monkeypatch.setattr(anki, "update_note_model", lambda *a: None)
    monkeypatch.setattr(anki, "add_note_hanja", lambda *a: 1 / 0)

    assert client.post("/api/anki/sync").json() == {"added": 0, "updated": 1, "failed": [], "promoted": 0}
    assert client.get("/api/terms").json()[0]["anki_note_id"] == 4242


def test_move_note_to_deck_skips_cards_already_in_the_deck_or_a_subdeck(monkeypatch):
    calls = []

    def fake_invoke(action, **params):
        calls.append((action, params))
        if action == "findCards":
            return [1, 2, 3]
        if action == "cardsInfo":
            return [
                {"cardId": 1, "deckName": "Korean"},
                {"cardId": 2, "deckName": "한자어"},
                {"cardId": 3, "deckName": "한자어::Sub"},
            ]

    monkeypatch.setattr(anki, "_invoke", fake_invoke)
    anki.move_note_to_deck(77, "한자어")
    assert calls[0] == ("findCards", {"query": "nid:77"})
    assert calls[-1] == ("changeDeck", {"cards": [1], "deck": "한자어"})


def test_min_intervals_takes_shortest_card_per_note(monkeypatch):
    def fake_invoke(action, **params):
        if action == "findCards":
            assert params == {"query": "nid:7,8"}
            return [1, 2, 3]
        return [
            {"cardId": 1, "note": 7, "interval": 30},
            {"cardId": 2, "note": 7, "interval": 12},
            {"cardId": 3, "note": 8, "interval": 40},
        ]

    monkeypatch.setattr(anki, "_invoke", fake_invoke)
    assert anki.min_intervals([7, 8]) == {7: 12, 8: 40}


def test_sync_promotes_mature_notes_to_known(client, monkeypatch):
    monkeypatch.setattr(anki, "ping", lambda: None)
    _mock_model(monkeypatch)
    monkeypatch.setattr(anki, "create_deck", lambda deck: None)
    note_ids = iter([101, 102])
    monkeypatch.setattr(anki, "add_note_model", lambda *a: next(note_ids))
    mature = _create(client, lemma="입다")
    young = _create(client, lemma="가다")
    client.post("/api/anki/sync")

    monkeypatch.setattr(anki, "min_intervals", lambda ids: {101: 21, 102: 20})
    assert client.post("/api/anki/sync").json()["promoted"] == 1

    statuses = {t["id"]: t["status"] for t in client.get("/api/terms").json()}
    assert statuses == {mature["id"]: "known", young["id"]: "learning"}

    # A known term's edits still reach its Anki note.
    client.patch(f"/api/terms/{mature['id']}", json={"translation": "to put on"})
    updates = []
    monkeypatch.setattr(anki, "update_note_model", lambda note_id, *a: updates.append(note_id))
    assert client.post("/api/anki/sync").json()["updated"] == 1
    assert updates == [101]


def test_sync_promotion_failure_does_not_fail_sync(client, monkeypatch):
    monkeypatch.setattr(anki, "ping", lambda: None)
    _mock_model(monkeypatch)
    monkeypatch.setattr(anki, "create_deck", lambda deck: None)
    monkeypatch.setattr(anki, "add_note_model", lambda *a: 101)

    def boom(ids):
        raise anki.AnkiError("cardsInfo failed")

    monkeypatch.setattr(anki, "min_intervals", boom)
    _create(client)
    assert client.post("/api/anki/sync").json() == {"added": 1, "updated": 0, "failed": [], "promoted": 0}
    assert client.get("/api/terms").json()[0]["status"] == "learning"
