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
  -- Epic 24: reading position as a character offset. Replaced current_page, which
  -- could not mean the same thing on two devices once each paginates for its own
  -- screen. Also declared in _ADDED_COLUMNS so pre-Epic-24 databases gain it.
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
-- Epic 20: extra surface forms a single term also covers (e.g. 승인서/승인하다 under
-- lemma 승인). Each form both highlights in the reader (matched in books.get_page
-- alongside the term's own lemma) and renders on the Korean face of the Anki card.
-- `lemma` stays the one clean dictionary form so tokenizer matching is unaffected;
-- these are the aliases. Plain CREATE TABLE (like `pages`/`page_reads`); ON DELETE
-- CASCADE with the FK pragma already on, so deleting a term drops its forms.
CREATE TABLE IF NOT EXISTS term_forms (
  term_id INTEGER NOT NULL REFERENCES terms(id) ON DELETE CASCADE,
  form TEXT NOT NULL,
  PRIMARY KEY (term_id, form)
);
-- Epic 22: the popover's structured Front/Back card builder. One row per Back chip;
-- `group_key` is '' for the lemma's own group or a term_forms.form value for a form's
-- group — a stable id, not a live join on lemma text, so editing the lemma never
-- orphans its back items. `korean_def` (kind='dict' only) is the krdict Korean
-- definition, with any krdict example glued directly onto its end (no separator) —
-- feeds the Anki `Examples` field, never matched against page tokens.
CREATE TABLE IF NOT EXISTS term_back_items (
  id INTEGER PRIMARY KEY,
  term_id INTEGER NOT NULL REFERENCES terms(id) ON DELETE CASCADE,
  group_key TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('dict','translate','manual')),
  text TEXT NOT NULL,
  korean_def TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
-- Epic 24: reading-activity log, replacing Epic 16's page_reads. One row per book
-- per local day it was read (PRIMARY KEY dedup + INSERT OR IGNORE on write). The
-- pages-read *counts* were dropped as unhelpful, but this table has to survive,
-- because the stats screen derives the streak from days-with-a-word-saved UNION
-- days-with-reading — drop it entirely and the streak silently becomes words-only,
-- so a day spent reading without saving a word would break it. Keyed by day rather
-- than by page because page numbers are per-device now and would not compose.
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
# Epic 11: content-catalog metadata (topic/tags/provenance/archived/read). Epic 15:
# candidate-queue lifecycle (status) + cached general/public difficulty. Epic 16:
# term provenance (which book/page a term was first saved from) for per-book and
# per-page stats — both nullable, forward-only (historical terms stay NULL), no FK
# so a later book delete just leaves a harmless dangling id.
_ADDED_COLUMNS: dict[str, dict[str, str]] = {
    "terms": {
        "source_book_id": "INTEGER",
        "source_page": "INTEGER",
        # Epic 21: usage examples clicked in from krdict (collocations like 기타를 치다)
        # plus the captured reading sentence. Display-only — never matched against page
        # tokens — so a JSON-encoded list column, not a normalized table like term_forms.
        # They render on the *back* of the Anki card only. `anki_model` records which
        # AnkiConnect note type a synced term lives in (two-way or hanja model).
        "examples": "TEXT NOT NULL DEFAULT '[]'",
        "anki_model": "TEXT",
        # Epic 25: hanja spelling for on-demand Sino-Korean word saves (separate deck
        # + note type). Empty for every reading-flow term. Epic 26: a JSON list of
        # spellings, one per sense (시장 is 市場 *and* 市長), ordered — same
        # list-in-a-column shape as `examples`.
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
        # Epic 18: length stat for the Queue. word_count is set at insert time for
        # every source; duration_seconds is yt-dlp's real video length (not a
        # transcript estimate), set only for source='yt'. Both NULL for anything
        # inserted before this epic (backfilling is not attempted).
        "word_count": "INTEGER",
        "duration_seconds": "INTEGER",
        # Epic 19: promotion stats provenance. feed_id is a soft reference (no FK,
        # same convention as terms.source_book_id) set only for feed-sourced
        # candidates (routes/feeds.py); manual imports leave it NULL, which is also
        # how the curation stats query excludes them. discard_reason ('user' or
        # 'expired') is set at the two places status flips to 'discarded': the
        # manual PATCH path (routes/books.py) and Epic 17's auto-expiry UPDATE
        # (routes/feeds.py); left loose (no CHECK) since it's informational, not a
        # lifecycle gate like status.
        "feed_id": "INTEGER",
        "discard_reason": "TEXT",
        # 2026-07-24: "most recently opened" sort for the Library. Stamped every
        # time a page is actually viewed (routes/books.py's get_page), not on
        # create/patch, so it reflects reading activity rather than list churn.
        "last_opened": "TIMESTAMP",
    },
    "term_forms": {
        # Epic 22: was this form clicked in from the dictionary, or typed by hand via
        # the "Add entry" form? Existing rows default to 'manual' — they were all
        # typed into the old free-text "Also highlight" input, which is exactly what
        # they are. Drives chip color/behavior in the popover; matching against page
        # tokens (books.get_page) doesn't care about it.
        "kind": "TEXT NOT NULL DEFAULT 'manual'",
    },
}

# Epic 14: the curated multi-topic source roster, replacing Epic 15's two-feed
# proof-of-infrastructure seed. Every entry was verified live this session — RSS
# feeds fetched with the app's own no-UA httpx path (server.feeds.fetch_feed_xml),
# YouTube channel IDs resolved and confirmed against each channel's Atom feed
# (see docs/CONTENT_CATALOG.md for the full vetted list + channel IDs). Curated to
# the user's stated tastes: male-presenter, idea-exposition/science-focused
# essayists over variety/lifestyle content. youtube feeds store the bare UC channel
# id in url_or_channel_id; server.feeds.youtube_feed_url builds the fetch URL.
# Guarded per-URL by _seed_feeds (not a blanket COUNT(*)) so a hand-added or
# hand-edited feed survives re-seeding after an upgrade.
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

    # Partial index: NULL source_ref (paste/txt books) never collides, but two
    # imports of the same video id / feed guid do — the dedup guarantee Epic 12's
    # importers and Epic 15's feed fetcher rely on.
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_books_source_ref "
        "ON books(source_ref) WHERE source_ref IS NOT NULL"
    )


def _seed_feeds(conn: sqlite3.Connection) -> None:
    """Insert the Epic 15 seed feeds, once each, keyed by URL so a hand-added feed
    row (or a future curation session's rows) is never touched or duplicated."""
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
