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

