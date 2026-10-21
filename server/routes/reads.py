"""Reading-activity log: a book counts once per local day it was read.

The client pings after a few seconds of visible reading; later pings that day no-op.
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
