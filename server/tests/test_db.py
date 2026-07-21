import sqlite3

from server import db


def test_schema_creates_on_temp_db(tmp_path):
    db_path = tmp_path / "test.db"
    db.init_db(db_path)

    conn = sqlite3.connect(db_path)
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    conn.close()

    assert {"books", "pages", "terms", "settings"} <= tables


def test_init_db_is_idempotent(tmp_path):
    db_path = tmp_path / "test.db"
    db.init_db(db_path)
    db.init_db(db_path)  # must not raise


def test_get_connection_enables_foreign_keys(tmp_path):
    db_path = tmp_path / "test.db"
    db.init_db(db_path)
    conn = db.get_connection(db_path)
    try:
        fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
        assert fk == 1
    finally:
        conn.close()
