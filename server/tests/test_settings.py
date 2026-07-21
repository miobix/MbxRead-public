def test_get_settings_defaults(client):
    resp = client.get("/api/settings")
    assert resp.status_code == 200
    assert resp.json() == {
        "decks": ["Korean"],
        "default_deck": "Korean",
        "translator_backend": "deepl",
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
    }

    resp = client.get("/api/settings")
    assert resp.json() == {
        "decks": ["Korean", "Slang"],
        "default_deck": "Slang",
        "translator_backend": "deepl",
    }


def test_put_settings_partial_update_leaves_other_keys(client):
    client.put("/api/settings", json={"decks": ["Korean", "Slang"]})
    resp = client.put("/api/settings", json={"translator_backend": "claude"})
    assert resp.status_code == 200
    assert resp.json() == {
        "decks": ["Korean", "Slang"],
        "default_deck": "Korean",
        "translator_backend": "claude",
    }


def test_put_settings_overwrites_existing_key(client):
    client.put("/api/settings", json={"default_deck": "Slang"})
    resp = client.put("/api/settings", json={"default_deck": "Korean"})
    assert resp.status_code == 200
    assert resp.json()["default_deck"] == "Korean"
