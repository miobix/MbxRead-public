import pytest
from fastapi.testclient import TestClient

from server.main import create_app


@pytest.fixture(autouse=True)
def _no_live_anki(monkeypatch):
    """Anki is often open on this machine; an unmocked call must fail, not edit it."""
    from server import anki

    monkeypatch.setattr(anki, "ANKICONNECT_URL", "http://127.0.0.1:9")


@pytest.fixture(autouse=True)
def _temp_krdict_cache(monkeypatch, tmp_path):
    from translate_svc import krdict

    monkeypatch.setattr(krdict, "CACHE_DB", tmp_path / "krdict_cache.sqlite3")


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "test.db"


@pytest.fixture
def client(db_path):
    app = create_app(db_path)
    with TestClient(app) as c:
        yield c
