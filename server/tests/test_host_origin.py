import pytest
from fastapi.testclient import TestClient

from server.main import create_app
from translate_svc import config


@pytest.fixture
def app(db_url, monkeypatch):
    monkeypatch.setattr(config, "ALLOWED_HOSTS", ["127.0.0.1", "localhost", "mypc"])
    return create_app(db_url)


def test_foreign_host_header_is_refused(app):
    with TestClient(app, base_url="http://evil.example") as c:
        assert c.get("/api/health").status_code == 400


@pytest.mark.parametrize("host", ["127.0.0.1:8002", "localhost:8002", "mypc:8002"])
def test_allowed_hosts_answer(app, host):
    with TestClient(app, base_url=f"http://{host}") as c:
        assert c.get("/api/health").status_code == 200


@pytest.mark.parametrize("origin", ["http://evil.example", "null", "http://127.0.0.1.evil.example"])
def test_cross_site_write_is_refused(app, origin):
    with TestClient(app, base_url="http://127.0.0.1") as c:
        r = c.post("/api/score", json={}, headers={"Origin": origin})
        assert r.status_code == 403


@pytest.mark.parametrize("headers", [{}, {"Origin": "http://localhost:3000"}, {"Origin": "http://mypc:8002"}])
def test_same_site_or_originless_write_passes(app, headers):
    with TestClient(app, base_url="http://127.0.0.1") as c:
        # 422: past the middleware, refused only for the empty body.
        assert c.post("/api/score", json={}, headers=headers).status_code == 422


def test_cross_site_read_is_not_blocked_by_origin(app):
    with TestClient(app, base_url="http://127.0.0.1") as c:
        assert c.get("/api/health", headers={"Origin": "http://evil.example"}).status_code == 200
