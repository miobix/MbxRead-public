import sqlite3
from datetime import datetime, timezone

import pytest

from scripts.sqlite_to_pg import migrate
from server import db


@pytest.fixture
def old_db(tmp_path):
    """A small reader.db in the pre-unit-4 shape (ids with gaps, UTC text timestamps)."""
    path = tmp_path / "reader.db"
    c = sqlite3.connect(path)
    c.executescript("""
        CREATE TABLE books (id INTEGER PRIMARY KEY, title TEXT, source TEXT,
          current_offset INTEGER, created TIMESTAMP, status TEXT, archived INTEGER,
          read INTEGER, tags TEXT, topic TEXT, source_url TEXT);
        CREATE TABLE pages (book_id INTEGER, page_no INTEGER, content TEXT);
        CREATE TABLE terms (id INTEGER PRIMARY KEY, lemma TEXT, translation TEXT, notes TEXT,
          status TEXT, deck TEXT, sentence TEXT, anki_note_id INTEGER, anki_dirty INTEGER,
          created TIMESTAMP, updated TIMESTAMP, examples TEXT, hanja TEXT);
        CREATE TABLE term_forms (term_id INTEGER, form TEXT, kind TEXT);
        CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE feeds (id INTEGER PRIMARY KEY, name TEXT, type TEXT,
          url_or_channel_id TEXT, topic TEXT, enabled INTEGER);
        INSERT INTO books VALUES (7, '소설', 'paste', 120, '2026-01-02 23:30:00', 'library',
          0, 1, '[]', '', '');
        INSERT INTO pages VALUES (7, 1, '첫 페이지'), (7, 2, '둘째 페이지');
        INSERT INTO terms VALUES (42, '입다', 'to wear', '', 'learning', 'Korean', '',
          1700000000000, 0, '2026-01-02 23:30:00', '2026-01-02 23:30:00', '[]', '[]');
        INSERT INTO term_forms VALUES (42, '입은', 'manual'), (42, '입고', 'manual');
        INSERT INTO settings VALUES ('default_deck', '"Korean"');
        INSERT INTO feeds VALUES (3, 'Mine', 'rss', 'https://example.org/rss', 'news', 1);
    """)
    c.commit()
    c.close()
    return path


def test_migrate_keeps_ids_counts_and_utc(old_db, db_url):
    counts = migrate(str(old_db), None, db_url)
    assert counts["books"] == 1 and counts["pages"] == 2 and counts["terms"] == 1
    assert counts["term_forms"] == 2 and counts["feeds"] == 1

    with db.get_connection(db_url) as conn:
        term = conn.execute("SELECT * FROM terms").fetchone()
        assert term["id"] == 42 and term["anki_note_id"] == 1700000000000
        assert term["created"] == datetime(2026, 1, 2, 23, 30, tzinfo=timezone.utc)
        forms = [r["form"] for r in conn.execute("SELECT form FROM term_forms ORDER BY id")]
        assert forms == ["입은", "입고"]  # insertion order survives
        assert [r["name"] for r in conn.execute("SELECT name FROM feeds")] == ["Mine"]
        # Identity sequences continue past the copied ids.
        new_id = conn.execute(
            "INSERT INTO terms (lemma) VALUES ('가다') RETURNING id"
        ).fetchone()["id"]
        assert new_id == 43


def test_migrate_refuses_a_target_with_data(old_db, db_url):
    migrate(str(old_db), None, db_url)
    with pytest.raises(SystemExit):
        migrate(str(old_db), None, db_url)
