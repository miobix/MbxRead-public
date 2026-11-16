"""Reading-activity log: a book counts once per local day it was read.

The client pings after a few seconds of visible reading; later pings that day no-op.
"""
from datetime import date

import psycopg
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import db as db_module

router = APIRouter(prefix="/api/reads", tags=["reads"])


class ReadCreate(BaseModel):
    book_id: int


@router.post("", status_code=201)
def mark_read(body: ReadCreate, conn: psycopg.Connection = Depends(db_module.get_db)):
    book = conn.execute("SELECT id FROM books WHERE id = %s", (body.book_id,)).fetchone()
    if book is None:
        raise HTTPException(status_code=404, detail="book not found")
    # Process-local day (TZ in Docker), matching how /api/stats buckets every other day.
    cur = conn.execute(
        "INSERT INTO read_days (book_id, day) VALUES (%s, %s) ON CONFLICT DO NOTHING",
        (body.book_id, date.today().isoformat()),
    )
    conn.commit()
    # rowcount is 0 when this book was already logged today — a no-op, not counted.
    return {"counted": cur.rowcount > 0}
