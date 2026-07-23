import sqlite3


def _create(client, **overrides):
    body = {"lemma": "입다", "translation": "to wear"}
    body.update(overrides)
    return client.post("/api/terms", json=body)


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
    body = _create(client, lemma="승인", forms=["승인서", "승인하다"]).json()
    assert body["forms"] == ["승인서", "승인하다"]
    assert client.get("/api/terms").json()[0]["forms"] == ["승인서", "승인하다"]


def test_create_term_normalizes_forms(client):
    # blanks dropped, the lemma itself dropped, duplicates collapsed, order kept.
    body = _create(
        client, lemma="승인", forms=[" 승인서 ", "승인", "승인하다", "승인서", ""]
    ).json()
    assert body["forms"] == ["승인서", "승인하다"]


def test_patch_rewrites_forms(client):
    term_id = _create(client, lemma="승인", forms=["승인서"]).json()["id"]
    body = client.patch(
        f"/api/terms/{term_id}", json={"forms": ["승인하다", "승인권"]}
    ).json()
    assert body["forms"] == ["승인하다", "승인권"]


def test_patch_forms_after_sync_marks_dirty(client, db_path):
    term_id = _create(client, lemma="승인").json()["id"]

    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE terms SET anki_note_id = 12345 WHERE id = ?", (term_id,))
    conn.commit()
    conn.close()

    resp = client.patch(f"/api/terms/{term_id}", json={"forms": ["승인서"]})
    assert resp.status_code == 200
    assert resp.json()["anki_dirty"] is True


def test_patch_same_forms_after_sync_does_not_mark_dirty(client, db_path):
    term_id = _create(client, lemma="승인", forms=["승인서"]).json()["id"]

    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE terms SET anki_note_id = 12345 WHERE id = ?", (term_id,))
    conn.commit()
    conn.close()

    resp = client.patch(f"/api/terms/{term_id}", json={"forms": ["승인서"]})
    assert resp.json()["anki_dirty"] is False


def test_delete_term_cascades_forms(client, db_path):
    term_id = _create(client, lemma="승인", forms=["승인서"]).json()["id"]
    assert client.delete(f"/api/terms/{term_id}").status_code == 204

    conn = sqlite3.connect(db_path)
    remaining = conn.execute(
        "SELECT COUNT(*) FROM term_forms WHERE term_id = ?", (term_id,)
    ).fetchone()[0]
    conn.close()
    assert remaining == 0


def test_delete_term(client):
    term_id = _create(client).json()["id"]
    assert client.delete(f"/api/terms/{term_id}").status_code == 204
    assert client.get("/api/terms").json() == []


def test_delete_missing_term_404(client):
    assert client.delete("/api/terms/999").status_code == 404
