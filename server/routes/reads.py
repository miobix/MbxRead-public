"""Reading-activity log API (Epic 16). See docs/SPEC.md section 5.

A page counts once, the first time it's genuinely read. The client only pings this
after a dwell gate (a few seconds of visible time on the page), and the PRIMARY KEY
+ INSERT OR IGNORE here means any later revisit is a silent no-op — so re-checking a
word on a page read yesterday never double-counts toward today.
"""
import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import db as db_module

router = APIRouter(prefix="/api/reads", tags=["reads"])


class ReadCreate(BaseModel):
    book_id: int
    page_no: int


@router.post("", status_code=201)
def mark_page_read(body: ReadCreate, conn: sqlite3.Connection = Depends(db_module.get_db)):
    book = conn.execute("SELECT id FROM books WHERE id = ?", (body.book_id,)).fetchone()
    if book is None:
        raise HTTPException(status_code=404, detail="book not found")
    cur = conn.execute(
        "INSERT OR IGNORE INTO page_reads (book_id, page_no) VALUES (?, ?)",
        (body.book_id, body.page_no),
    )
    conn.commit()
    # rowcount is 0 when the page was already logged (revisit) — a no-op, not counted.
    return {"counted": cur.rowcount > 0}
