import os
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.conninfo import make_conninfo

from server import db
from server.main import create_app
from translate_svc import config

# Any database on this server works; tests create and drop their own.
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL", "postgresql://mbxread:mbxread@127.0.0.1:5433/postgres"
)
_TEMPLATE = "mbxread_test_template"


@pytest.fixture(autouse=True)
def _no_live_anki(monkeypatch):
    """Anki is often open on this machine; an unmocked call must fail, not edit it."""
    from server import anki

    monkeypatch.setattr(anki, "ANKICONNECT_URL", "http://127.0.0.1:9")


@pytest.fixture(autouse=True)
def _no_live_models(monkeypatch):
    """A local .env may point at the embed/Ollama containers; tests never call them."""
    monkeypatch.setattr(config, "EMBED_URL", "")
    monkeypatch.setattr(config, "OLLAMA_URL", "http://127.0.0.1:9")


@pytest.fixture(autouse=True)
def _no_live_db(monkeypatch):
    """The default URL is the live database; a test that didn't ask for db_url must fail."""
    monkeypatch.setattr(config, "DATABASE_URL", "postgresql://nobody@127.0.0.1:9/none?connect_timeout=1")


@pytest.fixture(scope="session")
def _admin():
    """Builds the schema + seeds once; each test copies it (CREATE DATABASE … TEMPLATE)."""
    admin = psycopg.connect(TEST_DATABASE_URL, autocommit=True)
    admin.execute(f"DROP DATABASE IF EXISTS {_TEMPLATE}")
    admin.execute(f"CREATE DATABASE {_TEMPLATE}")
    db.init_db(make_conninfo(TEST_DATABASE_URL, dbname=_TEMPLATE))
    yield admin
    admin.execute(f"DROP DATABASE IF EXISTS {_TEMPLATE}")
    admin.close()


@pytest.fixture
def db_url(_admin, monkeypatch):
    name = f"mbxread_test_{uuid4().hex[:12]}"
    _admin.execute(f"CREATE DATABASE {name} TEMPLATE {_TEMPLATE}")
    url = make_conninfo(TEST_DATABASE_URL, dbname=name)
    monkeypatch.setattr(config, "DATABASE_URL", url)
    yield url
    _admin.execute(f"DROP DATABASE {name} WITH (FORCE)")


@pytest.fixture
def client(db_url):
    app = create_app(db_url)
    with TestClient(app) as c:
        yield c
