"""Settings API. See docs/SPEC.md sections 4-5, 7."""
import json
import sqlite3

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from .. import db as db_module

router = APIRouter(prefix="/api/settings", tags=["settings"])

# Epic 24 removed `page_rows` and `chars_per_row`. Reader pagination is client-side
# now (CSS columns, exact N rendered lines), and lines-per-page is a *per-device*
# localStorage value — a phone and a laptop fit different amounts of text per line,
# so a single server-side value could only ever be right on one of them. The
# repaginate_all machinery that ran on every change went with them.

# Epic 17: how many days an unpromoted/undiscarded candidate sits in the Queue
# before the fetch job auto-discards it (see _expire_stale_candidates in
# routes/feeds.py). Tunable from /settings.
DEFAULT_CANDIDATE_RETENTION_DAYS = 7

DEFAULTS = {
    "decks": ["Korean"],
    "default_deck": "Korean",
    "translator_backend": "deepl",
    "candidate_retention_days": DEFAULT_CANDIDATE_RETENTION_DAYS,
    # Epic 17: system-managed, not user-editable — see SettingsPut below. Stamped by
    # POST /api/feeds/fetch (scheduled or manual) via stamp_last_fetch_attempt().
    "last_fetch_attempt": None,
}


class SettingsPut(BaseModel):
    decks: list[str] | None = None
    default_deck: str | None = None
    translator_backend: str | None = None
    candidate_retention_days: int | None = Field(default=None, ge=1, le=90)
    # last_fetch_attempt is deliberately NOT a field here — it's stamped internally
    # by the fetch job, never by the user, so a PUT body can't overwrite it (an
    # unknown field in the request body is simply ignored by pydantic).


def _read(conn: sqlite3.Connection) -> dict:
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    stored = {row["key"]: json.loads(row["value"]) for row in rows}
    return {**DEFAULTS, **stored}


def get_candidate_retention_days(conn: sqlite3.Connection) -> int:
    return _read(conn)["candidate_retention_days"]


def stamp_last_fetch_attempt(conn: sqlite3.Connection) -> None:
    """Records that a fetch was attempted, regardless of whether it succeeds —
    called first thing in POST /api/feeds/fetch so a run that errors out partway
    still leaves an accurate timestamp. Uses SQLite's own CURRENT_TIMESTAMP (not
    Python's clock) to match every other TIMESTAMP column's format in this app."""
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
    # No setting re-paginates the library any more (Epic 24) — a plain write.
    return _read(conn)
