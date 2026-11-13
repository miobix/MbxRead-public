"""Settings API. See docs/SPEC.md sections 4-5, 7."""
import json
import sqlite3

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from .. import db as db_module

router = APIRouter(prefix="/api/settings", tags=["settings"])

# Days a Queue candidate waits before a fetch auto-discards it.
DEFAULT_CANDIDATE_RETENTION_DAYS = 7

DEFAULTS = {
    "decks": ["Korean"],
    "default_deck": "Korean",
    "translator_backend": "deepl",
    "candidate_retention_days": DEFAULT_CANDIDATE_RETENTION_DAYS,
    # System-managed: stamped by POST /api/feeds/fetch, absent from SettingsPut.
    "last_fetch_attempt": None,
}


class SettingsPut(BaseModel):
    decks: list[str] | None = None
    default_deck: str | None = None
    translator_backend: str | None = None
    candidate_retention_days: int | None = Field(default=None, ge=1, le=90)
    # No last_fetch_attempt: pydantic drops it from a PUT body, so users can't set it.


def _read(conn: sqlite3.Connection) -> dict:
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    stored = {row["key"]: json.loads(row["value"]) for row in rows}
    return {**DEFAULTS, **stored}


def get_candidate_retention_days(conn: sqlite3.Connection) -> int:
    return _read(conn)["candidate_retention_days"]


def stamp_last_fetch_attempt(conn: sqlite3.Connection) -> None:
    """Record a fetch attempt, successful or not. SQLite's clock keeps the format of
    every other TIMESTAMP column."""
    now = conn.execute("SELECT CURRENT_TIMESTAMP").fetchone()[0]
    conn.execute(
        "INSERT INTO settings (key, value) VALUES ('last_fetch_attempt', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (json.dumps(now),),
    )
    conn.commit()


@router.get("")
def get_settings(conn: sqlite3.Connection = Depends(db_module.get_db)):
    return _read(conn)


@router.put("")
def put_settings(body: SettingsPut, conn: sqlite3.Connection = Depends(db_module.get_db)):
    fields = body.model_dump(exclude_unset=True)
    for key, value in fields.items():
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, json.dumps(value)),
        )
    conn.commit()
    return _read(conn)
