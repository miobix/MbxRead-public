"""Reading-activity log API (Epic 16, re-keyed by day in Epic 24). See docs/SPEC.md.

A book counts once per local day it was genuinely read. The client only pings this
after a dwell gate (a few seconds of visible time on the page), and the PRIMARY KEY
+ INSERT OR IGNORE here means every later page that day is a silent no-op.

Epic 24 replaced the per-page log with a per-day one: page numbers became
per-device (each device paginates for its own screen), so a `page_no` key no longer
identified the same stretch of text across devices and the counts wouldn't compose.
The pages-read *statistic* was dropped as unhelpful; this table survives because
`/api/stats` derives the streak from days-with-a-word-saved UNION days-with-reading,
so without it a day spent reading without saving a word would break the streak.
"""
import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import db as db_module

router = APIRouter(prefix="/api/reads", tags=["reads"])


class ReadCreate(BaseModel):
    book_id: int


@router.post("", status_code=201)
def mark_read(body: ReadCreate, conn: sqlite3.Connection = Depends(db_module.get_db)):
    book = conn.execute("SELECT id FROM books WHERE id = ?", (body.book_id,)).fetchone()
    if book is None:
        raise HTTPException(status_code=404, detail="book not found")
    # Local time, matching how /api/stats buckets every other day — the server runs
    # on the user's own PC, so server-local is user-local.
    cur = conn.execute(
        "INSERT OR IGNORE INTO read_days (book_id, day) "
        "VALUES (?, date('now', 'localtime'))",
        (body.book_id,),
    )
    conn.commit()
    # rowcount is 0 when this book was already logged today — a no-op, not counted.
    return {"counted": cur.rowcount > 0}
