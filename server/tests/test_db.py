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

    assert {
        "books",
        "pages",
        "terms",
        "settings",
        "feeds",
        "vocab_levels",
        "read_days",
    } <= tables


def test_terms_migration_adds_epic16_provenance_idempotently(tmp_path):
    db_path = tmp_path / "test.db"
    db.init_db(db_path)
    db.init_db(db_path)

    conn = sqlite3.connect(db_path)
    cols = [row[1] for row in conn.execute("PRAGMA table_info(terms)")]
    conn.close()
    for name in ("source_book_id", "source_page"):
        assert cols.count(name) == 1


def test_terms_migration_adds_epic21_columns_idempotently(tmp_path):
    db_path = tmp_path / "test.db"
    db.init_db(db_path)
    db.init_db(db_path)

    conn = sqlite3.connect(db_path)
    cols = [row[1] for row in conn.execute("PRAGMA table_info(terms)")]
    conn.close()
    for name in ("examples", "anki_model"):
        assert cols.count(name) == 1


def test_term_forms_migration_adds_kind_idempotently(tmp_path):
    db_path = tmp_path / "test.db"
    db.init_db(db_path)
    db.init_db(db_path)

    conn = sqlite3.connect(db_path)
    cols = [row[1] for row in conn.execute("PRAGMA table_info(term_forms)")]
    conn.close()
    assert cols.count("kind") == 1


def test_term_back_items_table_created_idempotently(tmp_path):
    db_path = tmp_path / "test.db"
    db.init_db(db_path)
    db.init_db(db_path)  # must not raise — CREATE TABLE IF NOT EXISTS

    conn = sqlite3.connect(db_path)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(term_back_items)")}
    conn.close()
    assert cols == {"id", "term_id", "group_key", "kind", "text", "korean_def"}


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


def test_books_migration_adds_epic15_columns_idempotently(tmp_path):
    db_path = tmp_path / "test.db"
    db.init_db(db_path)
    db.init_db(db_path)

    conn = sqlite3.connect(db_path)
    cols = [row[1] for row in conn.execute("PRAGMA table_info(books)")]
    conn.close()
    for name in ("status", "general_coverage", "general_level"):
        assert cols.count(name) == 1


def test_books_migration_adds_epic18_columns_idempotently(tmp_path):
    db_path = tmp_path / "test.db"
    db.init_db(db_path)
    db.init_db(db_path)

    conn = sqlite3.connect(db_path)
    cols = [row[1] for row in conn.execute("PRAGMA table_info(books)")]
    conn.close()
    for name in ("word_count", "duration_seconds"):
        assert cols.count(name) == 1


def test_books_migration_adds_epic19_columns_idempotently(tmp_path):
    db_path = tmp_path / "test.db"
    db.init_db(db_path)
    db.init_db(db_path)

    conn = sqlite3.connect(db_path)
    cols = [row[1] for row in conn.execute("PRAGMA table_info(books)")]
    conn.close()
    for name in ("feed_id", "discard_reason"):
        assert cols.count(name) == 1


def test_existing_books_default_to_library_status(tmp_path):
    db_path = tmp_path / "test.db"
    db.init_db(db_path)
    conn = db.get_connection(db_path)
    try:
        conn.execute("INSERT INTO books (title) VALUES ('a')")
        conn.commit()
        row = conn.execute("SELECT status FROM books WHERE title = 'a'").fetchone()
        assert row["status"] == "library"
    finally:
        conn.close()


def test_feeds_seeded_and_idempotent(tmp_path):
    db_path = tmp_path / "test.db"
    db.init_db(db_path)
    seed_count = len(db._SEED_FEEDS)  # Epic 14: the full curated roster
    conn = db.get_connection(db_path)
    try:
        rows = conn.execute("SELECT name, url_or_channel_id FROM feeds").fetchall()
        assert len(rows) == seed_count
        urls = {r["url_or_channel_id"] for r in rows}
        assert "https://webzine.inven.co.kr/news/rss.php" in urls  # a seeded RSS feed
        assert "UCZ0bi2aVJngKLwFTU5g_fLQ" in urls  # a seeded YouTube channel id

        # A hand-added feed must survive re-seeding, and seeds must not duplicate.
        conn.execute(
            "INSERT INTO feeds (name, type, url_or_channel_id, topic) VALUES (?, ?, ?, ?)",
            ("My channel", "youtube", "UCxxxx", "gaming"),
        )
        conn.commit()
    finally:
        conn.close()

    db.init_db(db_path)
    conn = db.get_connection(db_path)
    try:
        rows = conn.execute("SELECT name FROM feeds").fetchall()
        assert len(rows) == seed_count + 1  # no seed re-duplicated
        assert "My channel" in {r["name"] for r in rows}
    finally:
        conn.close()


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


def test_vocab_levels_seeded_once_and_idempotent(tmp_path):
    db_path = tmp_path / "test.db"
    db.init_db(db_path)
    conn = db.get_connection(db_path)
    try:
        (count_first,) = conn.execute("SELECT COUNT(*) FROM vocab_levels").fetchone()
        assert count_first > 5000  # the bundled NIKL list has ~5.5k entries
        row = conn.execute(
            "SELECT grade FROM vocab_levels WHERE lemma = ?", ("가다",)
        ).fetchone()
        assert row["grade"] == "A"
    finally:
        conn.close()

    db.init_db(db_path)  # re-running must not duplicate the seed
    conn = db.get_connection(db_path)
    try:
        (count_second,) = conn.execute("SELECT COUNT(*) FROM vocab_levels").fetchone()
        assert count_second == count_first
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
