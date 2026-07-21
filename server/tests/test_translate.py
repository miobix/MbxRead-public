from translate_svc.translators import TranslationError

from server.routes import translate as translate_route


def test_translate_success(client, monkeypatch):
    monkeypatch.setattr(translate_route, "translate", lambda text, backend=None: ("사랑", "deepl", False))

    resp = client.post("/api/translate", json={"text": "love"})
    assert resp.status_code == 200
    assert resp.json() == {"translation": "사랑", "backend": "deepl", "cached": False}


def test_translate_passes_backend_through(client, monkeypatch):
    calls = []

    def fake_translate(text, backend=None):
        calls.append((text, backend))
        return ("결과", backend or "deepl", True)

    monkeypatch.setattr(translate_route, "translate", fake_translate)

    resp = client.post("/api/translate", json={"text": "테스트", "backend": "claude"})
    assert resp.status_code == 200
    assert resp.json() == {"translation": "결과", "backend": "claude", "cached": True}
    assert calls == [("테스트", "claude")]


def test_translate_error_returns_502_with_error_body(client, monkeypatch):
    def raise_error(text, backend=None):
        raise TranslationError("DEEPL_API_KEY is not set — add it to .env")

    monkeypatch.setattr(translate_route, "translate", raise_error)

    resp = client.post("/api/translate", json={"text": "안녕"})
    assert resp.status_code == 502
    assert resp.json() == {"error": "DEEPL_API_KEY is not set — add it to .env"}


def test_dict_lookup_returns_entries(client, monkeypatch):
    fake_entries = [
        {
            "word": "사랑",
            "pos": "명사",
            "definitions": [{"ko": "정의", "en_word": "love", "en_def": "a strong feeling"}],
        }
    ]
    monkeypatch.setattr(translate_route.krdict, "lookup", lambda word, max_entries=3: fake_entries)

    resp = client.get("/api/dict", params={"word": "사랑"})
    assert resp.status_code == 200
    assert resp.json() == fake_entries


def test_dict_lookup_empty_when_no_entries(client, monkeypatch):
    monkeypatch.setattr(translate_route.krdict, "lookup", lambda word, max_entries=3: [])

    resp = client.get("/api/dict", params={"word": "zzzzz"})
    assert resp.status_code == 200
    assert resp.json() == []
