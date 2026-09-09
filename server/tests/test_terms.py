import sqlite3


def _create(client, **overrides):
    body = {"lemma": "입다", "translation": "to wear"}
    body.update(overrides)
    return client.post("/api/terms", json=body)


def _forms(*texts, kind="manual"):
    return [{"text": t, "kind": kind} for t in texts]


def _back(group, kind, text, korean_def=""):
    return {"group": group, "kind": kind, "text": text, "korean_def": korean_def}


def test_create_term_defaults(client):
    resp = _create(client)
    assert resp.status_code == 201
    body = resp.json()
    assert body["lemma"] == "입다"
    assert body["translation"] == "to wear"
    assert body["notes"] == ""
    assert body["status"] == "learning"
    assert body["deck"] == ""
    assert body["sentence"] == ""
    assert body["anki_note_id"] is None
    assert body["anki_dirty"] is False
    assert body["created"]
    assert body["updated"]


def test_create_term_defaults_hanja_empty(client):
    resp = _create(client)
    assert resp.json()["hanja"] == []


def test_create_and_patch_round_trip_hanja(client):
    term_id = _create(client, lemma="제일", hanja=[" 第一 "]).json()["id"]
    resp = client.get("/api/terms")
    assert [t["hanja"] for t in resp.json() if t["id"] == term_id] == [["第一"]]

    resp = client.patch(f"/api/terms/{term_id}", json={"hanja": [" 祭日 "]})
    assert resp.status_code == 200
    assert resp.json()["hanja"] == ["祭日"]


def test_hanja_list_keeps_order_and_drops_blanks_and_dupes(client):
    """Epic 26: one lemma, several senses (시장 = 市場 market + 市長 mayor)."""
    resp = _create(client, lemma="시장", hanja=["市場", " ", "市長", "市場"])
    assert resp.json()["hanja"] == ["市場", "市長"]


def test_append_a_hanja_sense_to_an_existing_term(client):
    term_id = _create(client, lemma="시장", hanja=["市場"]).json()["id"]
    resp = client.patch(
        f"/api/terms/{term_id}",
        json={
            "hanja": ["市場", "市長"],
            "back_items": [_back("市場", "dict", "market"), _back("市長", "dict", "mayor")],
        },
    )
    assert resp.status_code == 200
    assert resp.json()["hanja"] == ["市場", "市長"]
    assert resp.json()["translation"] == "market; mayor"


def test_get_term_by_lemma(client):
    term_id = _create(client, lemma="시장", hanja=["市場"]).json()["id"]
    resp = client.get("/api/terms/by-lemma", params={"lemma": " 시장 "})
    assert resp.status_code == 200
    assert resp.json()["id"] == term_id


def test_get_term_by_lemma_404_when_unsaved(client):
    assert client.get("/api/terms/by-lemma", params={"lemma": "시장"}).status_code == 404


def test_patch_hanja_after_sync_marks_dirty(client, db_path):
    term_id = _create(client, hanja=["第一"]).json()["id"]

    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE terms SET anki_note_id = 12345 WHERE id = ?", (term_id,))
    conn.commit()
    conn.close()

    resp = client.patch(f"/api/terms/{term_id}", json={"hanja": ["祭日"]})
    assert resp.status_code == 200
    assert resp.json()["anki_dirty"] is True


def test_patch_same_hanja_after_sync_does_not_mark_dirty(client, db_path):
    term_id = _create(client, hanja=["第一"]).json()["id"]

    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE terms SET anki_note_id = 12345 WHERE id = ?", (term_id,))
    conn.commit()
    conn.close()

    resp = client.patch(f"/api/terms/{term_id}", json={"hanja": ["第一"]})
    assert resp.status_code == 200
    assert resp.json()["anki_dirty"] is False


def test_create_term_duplicate_lemma_409(client):
    _create(client)
    resp = _create(client, translation="different")
    assert resp.status_code == 409


def test_list_terms_filters_by_status(client):
    _create(client, lemma="입다", status="learning")
    _create(client, lemma="가다", status="known")

    resp = client.get("/api/terms", params={"status": "known"})
    assert resp.status_code == 200
    lemmas = [t["lemma"] for t in resp.json()]
    assert lemmas == ["가다"]


def test_list_terms_filters_by_deck(client):
    _create(client, lemma="입다", deck="Korean")
    _create(client, lemma="가다", deck="Verbs")

    resp = client.get("/api/terms", params={"deck": "Verbs"})
    assert [t["lemma"] for t in resp.json()] == ["가다"]


def test_list_terms_filters_by_query(client):
    _create(client, lemma="입다", translation="to wear")
    _create(client, lemma="가다", translation="to go")

    resp = client.get("/api/terms", params={"q": "wear"})
    assert [t["lemma"] for t in resp.json()] == ["입다"]


def test_patch_before_sync_stays_clean(client):
    term_id = _create(client).json()["id"]
    resp = client.patch(f"/api/terms/{term_id}", json={"translation": "to put on"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["translation"] == "to put on"
    assert body["anki_dirty"] is False


def test_patch_after_sync_marks_dirty(client, db_path):
    term_id = _create(client).json()["id"]

    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE terms SET anki_note_id = 12345 WHERE id = ?", (term_id,))
    conn.commit()
    conn.close()

    resp = client.patch(f"/api/terms/{term_id}", json={"translation": "to put on"})
    assert resp.status_code == 200
    assert resp.json()["anki_dirty"] is True


def test_patch_status_change_after_sync_does_not_mark_dirty(client, db_path):
    term_id = _create(client).json()["id"]

    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE terms SET anki_note_id = 12345 WHERE id = ?", (term_id,))
    conn.commit()
    conn.close()

    resp = client.patch(f"/api/terms/{term_id}", json={"status": "known"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "known"
    assert body["anki_dirty"] is False


def test_patch_lemma_change_after_sync_does_not_mark_dirty(client, db_path):
    term_id = _create(client).json()["id"]

    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE terms SET anki_note_id = 12345 WHERE id = ?", (term_id,))
    conn.commit()
    conn.close()

    resp = client.patch(f"/api/terms/{term_id}", json={"lemma": "입으시다"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["lemma"] == "입으시다"
    assert body["anki_dirty"] is False


def test_patch_setting_same_value_after_sync_does_not_mark_dirty(client, db_path):
    term_id = _create(client, translation="to wear").json()["id"]

    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE terms SET anki_note_id = 12345 WHERE id = ?", (term_id,))
    conn.commit()
    conn.close()

    resp = client.patch(f"/api/terms/{term_id}", json={"translation": "to wear"})
    assert resp.json()["anki_dirty"] is False


def test_patch_lemma_conflict_409(client):
    _create(client, lemma="입다")
    other_id = _create(client, lemma="가다").json()["id"]

    resp = client.patch(f"/api/terms/{other_id}", json={"lemma": "입다"})
    assert resp.status_code == 409


def test_patch_missing_term_404(client):
    assert client.patch("/api/terms/999", json={"translation": "x"}).status_code == 404


def test_create_term_round_trips_forms(client):
    body = _create(client, lemma="승인", forms=_forms("승인서", "승인하다")).json()
    assert body["forms"] == _forms("승인서", "승인하다")
    assert client.get("/api/terms").json()[0]["forms"] == _forms("승인서", "승인하다")


def test_create_term_normalizes_forms(client):
    # blanks dropped, the lemma itself dropped, duplicates collapsed, order kept.
    body = _create(
        client, lemma="승인", forms=_forms(" 승인서 ", "승인", "승인하다", "승인서", "")
    ).json()
    assert body["forms"] == _forms("승인서", "승인하다")


def test_create_term_forms_keep_their_kind(client):
    body = _create(
        client,
        lemma="승인",
        forms=[{"text": "승인서", "kind": "dict"}, {"text": "승인권", "kind": "manual"}],
    ).json()
    assert body["forms"] == [
        {"text": "승인서", "kind": "dict"},
        {"text": "승인권", "kind": "manual"},
    ]


def test_patch_rewrites_forms(client):
    term_id = _create(client, lemma="승인", forms=_forms("승인서")).json()["id"]
    body = client.patch(
        f"/api/terms/{term_id}", json={"forms": _forms("승인하다", "승인권")}
    ).json()
    assert body["forms"] == _forms("승인하다", "승인권")


def test_patch_forms_after_sync_marks_dirty(client, db_path):
    term_id = _create(client, lemma="승인").json()["id"]

    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE terms SET anki_note_id = 12345 WHERE id = ?", (term_id,))
    conn.commit()
    conn.close()

    resp = client.patch(f"/api/terms/{term_id}", json={"forms": _forms("승인서")})
    assert resp.status_code == 200
    assert resp.json()["anki_dirty"] is True


def test_patch_same_forms_after_sync_does_not_mark_dirty(client, db_path):
    term_id = _create(client, lemma="승인", forms=_forms("승인서")).json()["id"]

    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE terms SET anki_note_id = 12345 WHERE id = ?", (term_id,))
    conn.commit()
    conn.close()

    resp = client.patch(f"/api/terms/{term_id}", json={"forms": _forms("승인서")})
    assert resp.json()["anki_dirty"] is False


def test_delete_term_cascades_forms(client, db_path):
    term_id = _create(client, lemma="승인", forms=_forms("승인서")).json()["id"]
    assert client.delete(f"/api/terms/{term_id}").status_code == 204

    conn = sqlite3.connect(db_path)
    remaining = conn.execute(
        "SELECT COUNT(*) FROM term_forms WHERE term_id = ?", (term_id,)
    ).fetchone()[0]
    conn.close()
    assert remaining == 0


def test_create_term_round_trips_back_items(client):
    body = _create(
        client,
        lemma="승인",
        back_items=[_back("", "dict", "approval", "허가함"), _back("", "translate", "approve")],
    ).json()
    assert body["back_items"] == [
        _back("", "dict", "approval", "허가함"),
        _back("", "translate", "approve"),
    ]
    # Epic 22: translation is derived from back_items, join order preserved.
    assert body["translation"] == "approval; approve"


def test_create_term_without_back_items_keeps_translation_as_given(client):
    body = _create(client, lemma="승인", translation="hand-typed").json()
    assert body["back_items"] == []
    assert body["translation"] == "hand-typed"


def test_patch_back_items_rewrites_and_marks_dirty(client, db_path):
    term_id = _create(client, lemma="승인", back_items=[_back("", "dict", "approval")]).json()[
        "id"
    ]

    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE terms SET anki_note_id = 12345 WHERE id = ?", (term_id,))
    conn.commit()
    conn.close()

    resp = client.patch(
        f"/api/terms/{term_id}",
        json={"back_items": [_back("", "dict", "approval", "허가함")]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["back_items"] == [_back("", "dict", "approval", "허가함")]
    assert body["anki_dirty"] is True


def test_patch_same_back_items_after_sync_does_not_mark_dirty(client, db_path):
    term_id = _create(client, lemma="승인", back_items=[_back("", "dict", "approval")]).json()[
        "id"
    ]

    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE terms SET anki_note_id = 12345 WHERE id = ?", (term_id,))
    conn.commit()
    conn.close()

    resp = client.patch(
        f"/api/terms/{term_id}", json={"back_items": [_back("", "dict", "approval")]}
    )
    assert resp.json()["anki_dirty"] is False


def test_delete_term_cascades_back_items(client, db_path):
    term_id = _create(client, lemma="승인", back_items=[_back("", "dict", "approval")]).json()[
        "id"
    ]
    assert client.delete(f"/api/terms/{term_id}").status_code == 204

    conn = sqlite3.connect(db_path)
    remaining = conn.execute(
        "SELECT COUNT(*) FROM term_back_items WHERE term_id = ?", (term_id,)
    ).fetchone()[0]
    conn.close()
    assert remaining == 0


def test_create_term_defaults_examples_empty(client):
    body = _create(client).json()
    assert body["examples"] == []


def test_create_and_patch_round_trip_examples(client):
    term_id = _create(
        client, lemma="기타", examples=[" 기타를 치다 ", "기타를 치다", ""]
    ).json()["id"]
    # normalized: trimmed, deduped, blanks dropped
    assert client.get("/api/terms").json()[0]["examples"] == ["기타를 치다"]

    body = client.patch(
        f"/api/terms/{term_id}", json={"examples": ["기타를 배우다", "기타를 치다"]}
    ).json()
    assert body["examples"] == ["기타를 배우다", "기타를 치다"]


def test_patch_examples_after_sync_marks_dirty(client, db_path):
    term_id = _create(client, lemma="기타").json()["id"]

    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE terms SET anki_note_id = 12345 WHERE id = ?", (term_id,))
    conn.commit()
    conn.close()

    resp = client.patch(f"/api/terms/{term_id}", json={"examples": ["기타를 치다"]})
    assert resp.status_code == 200
    assert resp.json()["anki_dirty"] is True


def test_patch_same_examples_after_sync_does_not_mark_dirty(client, db_path):
    term_id = _create(client, lemma="기타", examples=["기타를 치다"]).json()["id"]

    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE terms SET anki_note_id = 12345 WHERE id = ?", (term_id,))
    conn.commit()
    conn.close()

    resp = client.patch(f"/api/terms/{term_id}", json={"examples": ["기타를 치다"]})
    assert resp.json()["anki_dirty"] is False


def test_delete_term(client):
    term_id = _create(client).json()["id"]
    assert client.delete(f"/api/terms/{term_id}").status_code == 204
    assert client.get("/api/terms").json() == []


def test_delete_missing_term_404(client):
    assert client.delete("/api/terms/999").status_code == 404
