from server.routes.settings import DEFAULT_CANDIDATE_RETENTION_DAYS


def test_get_settings_defaults(client):
    resp = client.get("/api/settings")
    assert resp.status_code == 200
    assert resp.json() == {
        "decks": ["Korean"],
        "default_deck": "Korean",
        "translator_backend": "deepl",
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
        "candidate_retention_days": DEFAULT_CANDIDATE_RETENTION_DAYS,
        "last_fetch_attempt": None,
    }

    resp = client.get("/api/settings")
    assert resp.json() == {
        "decks": ["Korean", "Slang"],
        "default_deck": "Slang",
        "translator_backend": "deepl",
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


def test_retired_pagination_settings_are_purged_from_storage(client, db_path):
    """Settings rows are merged *over* DEFAULTS, so dropping a key from DEFAULTS isn't
    enough — a row written before Epic 24 would keep surfacing in GET /api/settings.
    The migration deletes them."""
    import json
    import sqlite3

    from server import db as db_module

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executemany(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        [("page_rows", json.dumps(12)), ("chars_per_row", json.dumps(32)),
         ("page_size", json.dumps(1500))],
    )
    conn.commit()

    db_module._apply_migrations(conn)
    conn.commit()
    conn.close()

    body = client.get("/api/settings").json()
    for retired in ("page_rows", "chars_per_row", "page_size"):
        assert retired not in body
