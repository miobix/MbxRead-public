from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.main import _WebOut


def test_next_segment_request_finds_the_nested_export_file(tmp_path):
    (tmp_path / "read" / "__next.read").mkdir(parents=True)
    (tmp_path / "read" / "__next.read" / "__PAGE__.txt").write_text("page")
    (tmp_path / "read" / "__next._tree.txt").write_text("tree")
    (tmp_path / "404.html").write_text("missing")
    app = FastAPI()
    app.mount("/", _WebOut(directory=tmp_path, html=True))
    client = TestClient(app)

    assert client.get("/read/__next.read.__PAGE__.txt").text == "page"
    assert client.get("/read/__next._tree.txt").text == "tree"
    assert client.get("/read/__next.nope.__PAGE__.txt").status_code == 404


def test_pages_revalidate_but_hashed_chunks_stay_cacheable(tmp_path):
    (tmp_path / "terms").mkdir()
    (tmp_path / "terms" / "index.html").write_text("terms")
    (tmp_path / "_next" / "static").mkdir(parents=True)
    (tmp_path / "_next" / "static" / "a.js").write_text("js")
    app = FastAPI()
    app.mount("/", _WebOut(directory=tmp_path, html=True))
    client = TestClient(app)

    assert client.get("/terms/").headers["cache-control"] == "no-cache"
    assert "cache-control" not in client.get("/_next/static/a.js").headers
