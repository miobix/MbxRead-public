import psycopg

from . import config


def get(backend: str, text: str) -> str | None:
    with psycopg.connect(config.DATABASE_URL) as conn:
        row = conn.execute(
            "SELECT result FROM translate_cache WHERE backend=%s AND text=%s", (backend, text)
        ).fetchone()
    return row[0] if row else None


def put(backend: str, text: str, result: str) -> None:
    with psycopg.connect(config.DATABASE_URL) as conn:
        conn.execute(
            "INSERT INTO translate_cache (backend, text, result) VALUES (%s,%s,%s) "
            "ON CONFLICT (backend, text) DO UPDATE SET result = excluded.result",
            (backend, text, result),
        )
