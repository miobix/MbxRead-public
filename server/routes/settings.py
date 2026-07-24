"""Settings API. See docs/SPEC.md sections 4-5, 7."""
import json
import sqlite3

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from .. import db as db_module
from ..paging import DEFAULT_CHARS_PER_ROW, DEFAULT_MAX_ROWS, split_pages_by_rows

router = APIRouter(prefix="/api/settings", tags=["settings"])

# page_rows/chars_per_row — how many *visual rows* a reader page holds, replacing
# Epic 16's char-count page_size (2026-07-24 ad hoc change, not a numbered epic: a
# char budget looks wildly different on screen depending on how newline-dense the
# text is — subtitle/dialogue-heavy text with lots of short lines ballooned past
# what fits on screen at the same char count as dense prose). chars_per_row is a
# wrap-width estimate the user tunes to their own device from /settings; see
# paging.estimate_rows. Tunable; changing either re-paginates the whole library.
DEFAULT_PAGE_ROWS = DEFAULT_MAX_ROWS
# DEFAULT_CHARS_PER_ROW is re-exported (imported above) for callers/tests that want
# the settings-layer default without reaching into server.paging directly.

# Epic 17: how many days an unpromoted/undiscarded candidate sits in the Queue
# before the fetch job auto-discards it (see _expire_stale_candidates in
# routes/feeds.py). Tunable from /settings.
DEFAULT_CANDIDATE_RETENTION_DAYS = 7

DEFAULTS = {
    "decks": ["Korean"],
    "default_deck": "Korean",
    "translator_backend": "deepl",
    "page_rows": DEFAULT_PAGE_ROWS,
    "chars_per_row": DEFAULT_CHARS_PER_ROW,
    "candidate_retention_days": DEFAULT_CANDIDATE_RETENTION_DAYS,
    # Epic 17: system-managed, not user-editable — see SettingsPut below. Stamped by
    # POST /api/feeds/fetch (scheduled or manual) via stamp_last_fetch_attempt().
    "last_fetch_attempt": None,
}


class SettingsPut(BaseModel):
    decks: list[str] | None = None
    default_deck: str | None = None
    translator_backend: str | None = None
    page_rows: int | None = Field(default=None, ge=3, le=200)
    chars_per_row: int | None = Field(default=None, ge=10, le=120)
    candidate_retention_days: int | None = Field(default=None, ge=1, le=90)
    # last_fetch_attempt is deliberately NOT a field here — it's stamped internally
    # by the fetch job, never by the user, so a PUT body can't overwrite it (an
    # unknown field in the request body is simply ignored by pydantic).


def _read(conn: sqlite3.Connection) -> dict:
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    stored = {row["key"]: json.loads(row["value"]) for row in rows}
    return {**DEFAULTS, **stored}


def get_page_rows(conn: sqlite3.Connection) -> int:
    return _read(conn)["page_rows"]


def get_chars_per_row(conn: sqlite3.Connection) -> int:
    return _read(conn)["chars_per_row"]


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


def repaginate_all(conn: sqlite3.Connection, new_rows: int, new_chars_per_row: int) -> None:
    """Re-split every non-discarded book's stored pages to `new_rows`/`new_chars_per_row`,
    preserving each book's reading position by character offset. A book's page boundaries
    move, so its page_reads rows (keyed by page_no) no longer map — they're cleared, which
    resets that book's pages-read count. Acceptable: re-pagination is a deliberate,
    occasional action (see docs/DECISIONS.md)."""
    book_ids = [
        row["id"] for row in conn.execute(
            "SELECT id FROM books WHERE status != 'discarded'"
        )
    ]
    for book_id in book_ids:
        old_pages = [
            row["content"] for row in conn.execute(
                "SELECT content FROM pages WHERE book_id = ? ORDER BY page_no", (book_id,)
            )
        ]
        if not old_pages:
            continue
        # Joining the stored slices is lossless — split_pages_by_rows produces
        # contiguous slices that cover the whole text with no separators added.
        text = "".join(old_pages)
        current = conn.execute(
            "SELECT current_page FROM books WHERE id = ?", (book_id,)
        ).fetchone()["current_page"]
        offset = sum(len(p) for p in old_pages[: max(current - 1, 0)])

        new_pages = split_pages_by_rows(text, new_rows, new_chars_per_row)
        new_current, acc = len(new_pages), 0
        for i, p in enumerate(new_pages):
            if offset < acc + len(p):
                new_current = i + 1
                break
            acc += len(p)

        conn.execute("DELETE FROM pages WHERE book_id = ?", (book_id,))
        conn.executemany(
            "INSERT INTO pages (book_id, page_no, content) VALUES (?, ?, ?)",
            [(book_id, i + 1, p) for i, p in enumerate(new_pages)],
        )
        conn.execute("DELETE FROM page_reads WHERE book_id = ?", (book_id,))
        conn.execute(
            "UPDATE books SET current_page = ? WHERE id = ?", (new_current, book_id)
        )
    conn.commit()


@router.get("")
def get_settings(conn: sqlite3.Connection = Depends(db_module.get_db)):
    return _read(conn)


@router.put("")
def put_settings(body: SettingsPut, conn: sqlite3.Connection = Depends(db_module.get_db)):
    fields = body.model_dump(exclude_unset=True)
    old = _read(conn)
    for key, value in fields.items():
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, json.dumps(value)),
        )
    conn.commit()
    merged = _read(conn)
    if (merged["page_rows"], merged["chars_per_row"]) != (old["page_rows"], old["chars_per_row"]):
        repaginate_all(conn, merged["page_rows"], merged["chars_per_row"])
    return _read(conn)
