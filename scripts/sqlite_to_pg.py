"""One-off cutover: copy a pre-unit-4 reader.db (and optionally translate_cache.sqlite3)
into an empty Postgres database. Ids are kept, so terms keep their anki_note_id links.

    .venv\\Scripts\\python.exe -m scripts.sqlite_to_pg TARGET_URL reader.db [translate_cache.sqlite3]

The target URL is required, never a default. Refuses missing source files and a target
that already has data; the source files are opened read-only.
"""
import sqlite3
import sys
from pathlib import Path

import psycopg
from psycopg.conninfo import conninfo_to_dict

from server import db

# FK order. (sqlite table, postgres table, extra select expressions)
TABLES = [
    ("books", "books", {}),
    ("pages", "pages", {}),
    ("terms", "terms", {}),
    ("term_forms", "term_forms", {"id": "rowid"}),
    ("term_back_items", "term_back_items", {}),
    ("settings", "settings", {}),
    ("read_days", "read_days", {}),
    ("feeds", "feeds", {}),
    ("vocab_levels", "vocab_levels", {}),
]
CACHE_TABLES = [("cache", "translate_cache", {}), ("krdict_cache", "krdict_cache", {})]
IDENTITY_TABLES = ["books", "terms", "term_forms", "term_back_items", "feeds"]


def _copy(src: sqlite3.Connection, dst: psycopg.Connection, s_table, d_table, extra) -> int:
    if not src.execute("SELECT 1 FROM sqlite_master WHERE name = ?", (s_table,)).fetchone():
        return 0
    s_cols = {r[1] for r in src.execute(f"PRAGMA table_info({s_table})")}
    d_cols = [
        r[0]
        for r in dst.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = %s",
            (d_table,),
        )
    ]
    cols = [c for c in d_cols if c in s_cols or c in extra]
    select = ", ".join(extra.get(c, c) for c in cols)
    rows = src.execute(f"SELECT {select} FROM {s_table}").fetchall()
    placeholders = ", ".join(["%s"] * len(cols))
    dst.cursor().executemany(
        f"INSERT INTO {d_table} ({', '.join(cols)}) VALUES ({placeholders})", rows
    )
    return len(rows)


def migrate(reader_db: str, cache_db: str | None, url: str) -> dict[str, int]:
    for path in filter(None, (reader_db, cache_db)):
        if not Path(path).is_file():
            raise SystemExit(f"no such SQLite file: {path}")
    db.init_db(url)
    counts = {}
    # SQLite's CURRENT_TIMESTAMP text is UTC with no offset.
    with psycopg.connect(url, options="-c timezone=UTC") as dst:
        for table in ("books", "terms", "settings"):
            if dst.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone():
                raise SystemExit(f"target already has rows in {table}; refusing to merge")
        # init_db seeded these; the old DB's copies (edited feeds included) win.
        dst.execute("DELETE FROM feeds")
        dst.execute("DELETE FROM vocab_levels")
        jobs = [(reader_db, TABLES)] + ([(cache_db, CACHE_TABLES)] if cache_db else [])
        for path, tables in jobs:
            src = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)
            try:
                for s_table, d_table, extra in tables:
                    counts[d_table] = _copy(src, dst, s_table, d_table, extra)
            finally:
                src.close()
        for table in IDENTITY_TABLES:
            dst.execute(
                f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                f"COALESCE(MAX(id), 0) + 1, false) FROM {table}"
            )
    return counts


if __name__ == "__main__":
    if len(sys.argv) not in (3, 4):
        raise SystemExit(__doc__)
    target = sys.argv[1]
    info = conninfo_to_dict(target)
    print(f"target: {info.get('host')}:{info.get('port')}/{info.get('dbname')}")
    for table, n in migrate(sys.argv[2], sys.argv[3] if len(sys.argv) == 4 else None,
                            target).items():
        print(f"{table:16} {n}")
