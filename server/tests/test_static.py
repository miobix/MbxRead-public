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
