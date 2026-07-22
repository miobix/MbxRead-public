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

    assert {"books", "pages", "terms", "settings", "feeds"} <= tables


def test_init_db_is_idempotent(tmp_path):
    db_path = tmp_path / "test.db"
    db.init_db(db_path)
    db.init_db(db_path)  # must not raise


def test_books_migration_adds_epic11_columns_idempotently(tmp_path):
    db_path = tmp_path / "test.db"
    db.init_db(db_path)
    db.init_db(db_path)

    conn = sqlite3.connect(db_path)
    cols = [row[1] for row in conn.execute("PRAGMA table_info(books)")]
    conn.close()
    for name in ("topic", "tags", "source_url", "source_ref", "fetched", "archived", "read"):
        assert cols.count(name) == 1


def test_source_ref_unique_index_ignores_nulls(tmp_path):
    db_path = tmp_path / "test.db"
    db.init_db(db_path)
    conn = db.get_connection(db_path)
    try:
        conn.execute("INSERT INTO books (title) VALUES ('a')")
        conn.execute("INSERT INTO books (title) VALUES ('b')")  # two NULL source_refs, fine
        conn.commit()
        conn.execute("INSERT INTO books (title, source_ref) VALUES ('c', 'x')")
        conn.commit()
        try:
            conn.execute("INSERT INTO books (title, source_ref) VALUES ('d', 'x')")
            conn.commit()
            assert False, "expected a UNIQUE constraint violation"
        except sqlite3.IntegrityError:
            pass
    finally:
        conn.close()


def test_get_connection_enables_foreign_keys(tmp_path):
    db_path = tmp_path / "test.db"
    db.init_db(db_path)
    conn = db.get_connection(db_path)
    try:
        fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
        assert fk == 1
    finally:
        conn.close()
