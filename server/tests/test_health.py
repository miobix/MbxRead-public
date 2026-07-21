from fastapi.testclient import TestClient

from server.main import create_app


def test_health_ok(tmp_path):
    app = create_app(tmp_path / "test.db")
    with TestClient(app) as client:
        resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "version": "0.1.0"}
