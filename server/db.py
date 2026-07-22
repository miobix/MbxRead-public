"""SQLite connection and schema management for reader.db."""
import csv
import sqlite3
from pathlib import Path
from typing import Generator

from fastapi import Request

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "reader.db"

# Epic 13: bundled reference data seeded into `vocab_levels` on first init. See
# docs/DECISIONS.md for provenance (국립국어원 한국어 학습용 어휘 목록, 2003).
VOCAB_LEVELS_TSV = Path(__file__).resolve().parent / "data" / "vocab_levels.tsv"

SCHEMA = """
CREATE TABLE IF NOT EXISTS books (
  id INTEGER PRIMARY KEY,
  title TEXT NOT NULL,
  source TEXT NOT NULL DEFAULT 'paste',
  current_page INTEGER NOT NULL DEFAULT 1,
  created TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS pages (
  book_id INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
  page_no INTEGER NOT NULL,
  content TEXT NOT NULL,
  PRIMARY KEY (book_id, page_no)
);
CREATE TABLE IF NOT EXISTS terms (
  id INTEGER PRIMARY KEY,
  lemma TEXT NOT NULL UNIQUE,
  translation TEXT NOT NULL DEFAULT '',
  notes TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'learning'
    CHECK (status IN ('learning','known','ignored')),
  deck TEXT NOT NULL DEFAULT '',
  sentence TEXT NOT NULL DEFAULT '',
  anki_note_id INTEGER,
  anki_dirty INTEGER NOT NULL DEFAULT 0,
  created TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS feeds (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  type TEXT NOT NULL CHECK (type IN ('rss','youtube','scraper')),
  url_or_channel_id TEXT NOT NULL,
  topic TEXT NOT NULL DEFAULT '',
  enabled INTEGER NOT NULL DEFAULT 1,
  difficulty_min REAL,
  difficulty_max REAL,
  last_fetched TIMESTAMP
);
-- Epic 13: cold-start difficulty signal. grade A (beginner/common) .. C (advanced/
-- rare), rank is a frequency rank across the whole list (lower = more frequent),
-- nullable since ~1% of source rows have no rank recorded. Seeded once from
-- VOCAB_LEVELS_TSV by _seed_vocab_levels, not hand-maintained.
CREATE TABLE IF NOT EXISTS vocab_levels (
  lemma TEXT PRIMARY KEY,
  grade TEXT NOT NULL CHECK (grade IN ('A','B','C')),
  rank INTEGER
);
"""

# Additive columns introduced after the initial schema. Applied idempotently by
# init_db so an existing reader.db upgrades in place (SQLite has no ADD COLUMN IF
# NOT EXISTS, so we guard on PRAGMA table_info). Epic 9: cached difficulty scores.
# Epic 11: content-catalog metadata (topic/tags/provenance/archived/read).
_ADDED_COLUMNS: dict[str, dict[str, str]] = {
    "books": {
        "coverage": "REAL",
        "new_per_page": "REAL",
        "scored_at": "TIMESTAMP",
        "topic": "TEXT NOT NULL DEFAULT ''",
        "tags": "TEXT NOT NULL DEFAULT '[]'",
        "source_url": "TEXT NOT NULL DEFAULT ''",
        "source_ref": "TEXT",
        "fetched": "TIMESTAMP",
        "archived": "INTEGER NOT NULL DEFAULT 0",
        "read": "INTEGER NOT NULL DEFAULT 0",
    },
}


def _apply_migrations(conn: sqlite3.Connection) -> None:
    for table, columns in _ADDED_COLUMNS.items():
        existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
        for name, decl in columns.items():
            if name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")
    # Partial index: NULL source_ref (paste/txt books) never collides, but two
    # imports of the same video id / feed guid do — the dedup guarantee Epic 12's
    # importers and Epic 14's daily job rely on.
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_books_source_ref "
        "ON books(source_ref) WHERE source_ref IS NOT NULL"
    )


def _seed_vocab_levels(conn: sqlite3.Connection) -> None:
    """Populate `vocab_levels` from the bundled TSV, once. A fresh reader.db (or a
    fresh temp test DB) starts with an empty table; this fills it on the first
    init_db call and is a no-op on every call after (guarded by COUNT(*))."""
    (count,) = conn.execute("SELECT COUNT(*) FROM vocab_levels").fetchone()
    if count > 0:
        return
    with open(VOCAB_LEVELS_TSV, encoding="utf-8", newline="") as f:
        rows = [
            (row["lemma"], row["grade"], int(row["rank"]) if row["rank"] else None)
            for row in csv.DictReader(f, delimiter="\t")
        ]
    conn.executemany(
        "INSERT INTO vocab_levels (lemma, grade, rank) VALUES (?, ?, ?)", rows
    )


def get_connection(db_path: Path | str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: Path | str = DEFAULT_DB_PATH) -> None:
    conn = get_connection(db_path)
    try:
        conn.executescript(SCHEMA)
        _apply_migrations(conn)
        _seed_vocab_levels(conn)
        conn.commit()
    finally:
        conn.close()


def get_db(request: Request) -> Generator[sqlite3.Connection, None, None]:
    """FastAPI dependency yielding a per-request connection to the app's DB."""
    conn = get_connection(request.app.state.db_path)
    try:
        yield conn
    finally:
        conn.close()
