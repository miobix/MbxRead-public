import sqlite3
from contextlib import closing

from .config import CACHE_DB


def _conn():
    conn = sqlite3.connect(CACHE_DB)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS cache ("
        " backend TEXT NOT NULL,"
        " text TEXT NOT NULL,"
        " result TEXT NOT NULL,"
        " created TIMESTAMP DEFAULT CURRENT_TIMESTAMP,"
        " PRIMARY KEY (backend, text))"
    )
    return conn


def get(backend: str, text: str) -> str | None:
    with closing(_conn()) as conn:
        row = conn.execute(
            "SELECT result FROM cache WHERE backend=? AND text=?", (backend, text)
        ).fetchone()
    return row[0] if row else None


def put(backend: str, text: str, result: str) -> None:
    with closing(_conn()) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO cache (backend, text, result) VALUES (?,?,?)",
            (backend, text, result),
        )
        conn.commit()
