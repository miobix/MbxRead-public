"""SQLite connection and schema management for reader.db."""
import csv
import sqlite3
from pathlib import Path
from typing import Generator

from fastapi import Request

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "reader.db"

# NIKL learner vocabulary list (2003); provenance in docs/DECISIONS.md.
VOCAB_LEVELS_TSV = Path(__file__).resolve().parent / "data" / "vocab_levels.tsv"

SCHEMA = """
CREATE TABLE IF NOT EXISTS books (
  id INTEGER PRIMARY KEY,
  title TEXT NOT NULL,
  source TEXT NOT NULL DEFAULT 'paste',
  -- A character offset, not a page: each device paginates for its own screen.
  current_offset INTEGER NOT NULL DEFAULT 0,
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
-- Aliases a term also highlights as (승인서 under 승인); `lemma` stays the one clean
-- dictionary form so tokenizer matching is unaffected.
CREATE TABLE IF NOT EXISTS term_forms (
  term_id INTEGER NOT NULL REFERENCES terms(id) ON DELETE CASCADE,
  form TEXT NOT NULL,
  PRIMARY KEY (term_id, form)
);
-- One row per Back chip. `group_key` is '' for the lemma's own group (not the lemma
-- text) so editing the lemma never orphans its chips.
CREATE TABLE IF NOT EXISTS term_back_items (
  id INTEGER PRIMARY KEY,
  term_id INTEGER NOT NULL REFERENCES terms(id) ON DELETE CASCADE,
  group_key TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('dict','translate','manual')),
  text TEXT NOT NULL,
  korean_def TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
-- Days read per book. Needed by the stats streak (word-saved days UNION read days), so a
-- day spent reading without saving a word still counts.
CREATE TABLE IF NOT EXISTS read_days (
  book_id INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
  day TEXT NOT NULL,
  PRIMARY KEY (book_id, day)
);
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
-- Grade A (common) .. C (rare); rank NULL for the ~1% of source rows without one.
CREATE TABLE IF NOT EXISTS vocab_levels (
  lemma TEXT PRIMARY KEY,
  grade TEXT NOT NULL CHECK (grade IN ('A','B','C')),
  rank INTEGER
);
"""

# Columns added after the initial schema; init_db adds any that are missing, since
# SQLite has no ADD COLUMN IF NOT EXISTS. This is also how a fresh DB gets them.
_ADDED_COLUMNS: dict[str, dict[str, str]] = {
    "terms": {
        # Soft references (no FK): deleting a book leaves a harmless dangling id.
        "source_book_id": "INTEGER",
        "source_page": "INTEGER",
        # JSON lists in a column: display-only, never matched against tokens.
        "examples": "TEXT NOT NULL DEFAULT '[]'",
        "anki_model": "TEXT",
        "hanja": "TEXT NOT NULL DEFAULT '[]'",
    },
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
        "status": (
            "TEXT NOT NULL DEFAULT 'library' "
            "CHECK (status IN ('library','candidate','discarded'))"
        ),
        "general_coverage": "REAL",
        "general_level": "TEXT",
        "word_count": "INTEGER",
        # yt-dlp's real video length, so only set for source='yt'.
        "duration_seconds": "INTEGER",
        # NULL for manual imports, which is how curation stats exclude them.
        "feed_id": "INTEGER",
        "discard_reason": "TEXT",
        # Stamped on reading, not on create/patch, so it reflects activity.
        "last_opened": "TIMESTAMP",
    },
    "term_forms": {
        "kind": "TEXT NOT NULL DEFAULT 'manual'",
    },
}

# Curated roster (vetting notes in docs/CONTENT_CATALOG.md). youtube feeds store the bare
# UC channel id; server.feeds.youtube_feed_url builds the fetch URL.
_SEED_FEEDS: list[tuple[str, str, str, str]] = [
    # gaming
    ("Inven game news", "rss", "https://webzine.inven.co.kr/news/rss.php", "gaming"),
    ("Ruliweb PS/game news", "rss", "https://bbs.ruliweb.com/news/524/rss", "gaming"),
    ("김성회의 G식백과", "youtube", "UCZ0bi2aVJngKLwFTU5g_fLQ", "gaming"),
    ("중년게이머 김실장", "youtube", "UCSgvQDek_7CQj08fu7kp1Iw", "gaming"),
    # ideas (society, philosophy, urbanism, geopolitics)
    ("슈카월드", "youtube", "UCsJ6RuBiTVWRX156FVbeaGg", "ideas"),
    ("충코의 철학", "youtube", "UCUV9bHklegmYbdt091TNvjA", "ideas"),
    ("셜록현준", "youtube", "UC7uDyFIqExDnfXAIZqumFrQ", "ideas"),
    ("최준영 박사의 지구본 연구소", "youtube", "UCstI8HwGQsHdqLDgyH0PImw", "ideas"),
    # science
    ("리뷰엉이", "youtube", "UCrBpV_pG2kyMMEHCMTNzjAQ", "science"),
    # fitness
    ("김명섭의 헬스교실", "youtube", "UCc5mVNF4R6ywMqbty91J0rQ", "fitness"),
    # tech / software
    ("조코딩", "youtube", "UCQNE2JmbasNYbjGAcuBiRRg", "tech"),
    ("요즘IT", "rss", "https://yozm.wishket.com/magazine/feed/", "tech"),
    # news / long-form essays
    ("ㅍㅍㅅㅅ", "rss", "https://www.ppss.kr/rss/allArticle.xml", "news"),
    ("슬로우뉴스", "rss", "https://slownews.kr/feed", "news"),
    ("뉴스페퍼민트", "rss", "https://newspeppermint.com/feed/", "news"),
]


def _apply_migrations(conn: sqlite3.Connection) -> None:
    for table, columns in _ADDED_COLUMNS.items():
        existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
        for name, decl in columns.items():
            if name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")

    # Partial: books without a source_ref (pastes) never collide; re-imports do.
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_books_source_ref "
        "ON books(source_ref) WHERE source_ref IS NOT NULL"
    )


def _seed_feeds(conn: sqlite3.Connection) -> None:
    """Insert each seed feed once, keyed by URL, so hand-added or edited feeds survive."""
    existing = {
        row["url_or_channel_id"] for row in conn.execute("SELECT url_or_channel_id FROM feeds")
    }
    for name, type_, url, topic in _SEED_FEEDS:
        if url not in existing:
            conn.execute(
                "INSERT INTO feeds (name, type, url_or_channel_id, topic) VALUES (?, ?, ?, ?)",
                (name, type_, url, topic),
            )


def _seed_vocab_levels(conn: sqlite3.Connection) -> None:
    """Fill `vocab_levels` from the bundled TSV on first init; a no-op afterwards."""
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
        _seed_feeds(conn)
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
