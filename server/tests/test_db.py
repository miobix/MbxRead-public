import psycopg
import pytest

from server import db


def test_schema_creates_every_table(db_url):
    with db.get_connection(db_url) as conn:
        tables = {
            r["tablename"]
            for r in conn.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        }
    assert {
        "books", "pages", "terms", "term_forms", "term_back_items", "settings", "feeds",
        "vocab_levels", "read_days", "translate_cache", "krdict_cache", "krdict_state",
    } <= tables


def test_init_db_is_idempotent(db_url):
    db.init_db(db_url)  # the template already ran it once; must not raise


def test_new_books_default_to_library_status(db_url):
    with db.get_connection(db_url) as conn:
        conn.execute("INSERT INTO books (title) VALUES ('a')")
        row = conn.execute("SELECT status FROM books WHERE title = 'a'").fetchone()
    assert row["status"] == "library"


def test_feeds_seeded_and_idempotent(db_url):
    seed_count = len(db._SEED_FEEDS)
    with db.get_connection(db_url) as conn:
        rows = conn.execute("SELECT name, url_or_channel_id FROM feeds").fetchall()
        assert len(rows) == seed_count
        urls = {r["url_or_channel_id"] for r in rows}
        assert "https://webzine.inven.co.kr/news/rss.php" in urls
        assert "UCZ0bi2aVJngKLwFTU5g_fLQ" in urls
        # A hand-added feed must survive re-seeding, and seeds must not duplicate.
        conn.execute(
            "INSERT INTO feeds (name, type, url_or_channel_id, topic) VALUES (%s, %s, %s, %s)",
            ("My channel", "youtube", "UCxxxx", "gaming"),
        )

    db.init_db(db_url)
    with db.get_connection(db_url) as conn:
        names = {r["name"] for r in conn.execute("SELECT name FROM feeds")}
    assert len(names) == seed_count + 1
    assert "My channel" in names


def test_deleted_seed_feed_stays_deleted(db_url):
    with db.get_connection(db_url) as conn:
        conn.execute(
            "DELETE FROM feeds WHERE url_or_channel_id = %s",
            ("https://webzine.inven.co.kr/news/rss.php",),
        )
    db.init_db(db_url)
    with db.get_connection(db_url) as conn:
        urls = {r["url_or_channel_id"] for r in conn.execute("SELECT url_or_channel_id FROM feeds")}
    assert "https://webzine.inven.co.kr/news/rss.php" not in urls
    assert len(urls) == len(db._SEED_FEEDS) - 1


def test_source_ref_unique_index_ignores_nulls(db_url):
    with db.get_connection(db_url) as conn:
        conn.execute("INSERT INTO books (title) VALUES ('a')")
        conn.execute("INSERT INTO books (title) VALUES ('b')")  # two NULL source_refs, fine
        conn.execute("INSERT INTO books (title, source_ref) VALUES ('c', 'x')")
        with pytest.raises(psycopg.errors.UniqueViolation):
            conn.execute("INSERT INTO books (title, source_ref) VALUES ('d', 'x')")


def test_vocab_levels_seeded_once(db_url):
    count = "SELECT COUNT(*) n FROM vocab_levels"
    with db.get_connection(db_url) as conn:
        first = conn.execute(count).fetchone()["n"]
        grade = conn.execute(
            "SELECT grade FROM vocab_levels WHERE lemma = %s", ("가다",)
        ).fetchone()["grade"]
    assert first > 5000  # the bundled NIKL list has ~5.5k entries
    assert grade == "A"

    db.init_db(db_url)
    with db.get_connection(db_url) as conn:
        assert conn.execute(count).fetchone()["n"] == first


def test_foreign_keys_cascade(db_url):
    with db.get_connection(db_url) as conn:
        book_id = conn.execute("INSERT INTO books (title) VALUES ('a') RETURNING id").fetchone()["id"]
        conn.execute("INSERT INTO pages (book_id, page_no, content) VALUES (%s, 1, 'x')", (book_id,))
        conn.execute("DELETE FROM books WHERE id = %s", (book_id,))
        assert conn.execute("SELECT COUNT(*) n FROM pages").fetchone()["n"] == 0
