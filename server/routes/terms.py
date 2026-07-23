"""Terms API. See docs/SPEC.md section 5."""
import sqlite3
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import db as db_module

router = APIRouter(prefix="/api/terms", tags=["terms"])

Status = Literal["learning", "known", "ignored"]
_DIRTY_TRIGGER_FIELDS = {"translation", "notes", "deck", "sentence"}


class TermCreate(BaseModel):
    lemma: str
    translation: str
    notes: str = ""
    status: Status = "learning"
    deck: str = ""
    sentence: str = ""
    # Epic 16: which book/page this term was first saved from (reader passes both).
    # Nullable — terms saved outside the reader (e.g. from /terms) have no origin.
    source_book_id: int | None = None
    source_page: int | None = None


class TermPatch(BaseModel):
    lemma: str | None = None
    translation: str | None = None
    notes: str | None = None
    status: Status | None = None
    deck: str | None = None
    sentence: str | None = None


def _term_dict(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "lemma": row["lemma"],
        "translation": row["translation"],
        "notes": row["notes"],
        "status": row["status"],
        "deck": row["deck"],
        "sentence": row["sentence"],
        "anki_note_id": row["anki_note_id"],
        "anki_dirty": bool(row["anki_dirty"]),
        "created": row["created"],
        "updated": row["updated"],
        "source_book_id": row["source_book_id"],
        "source_page": row["source_page"],
    }


def _get_term_or_404(conn: sqlite3.Connection, term_id: int) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM terms WHERE id = ?", (term_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="term not found")
    return row


@router.get("")
def list_terms(
    status: Status | None = None,
    deck: str | None = None,
    q: str | None = None,
    conn: sqlite3.Connection = Depends(db_module.get_db),
):
    query = "SELECT * FROM terms WHERE 1=1"
    params: list = []
    if status:
        query += " AND status = ?"
        params.append(status)
    if deck:
        query += " AND deck = ?"
        params.append(deck)
    if q:
        query += " AND (lemma LIKE ? OR translation LIKE ? OR notes LIKE ?)"
        like = f"%{q}%"
        params.extend([like, like, like])
    query += " ORDER BY id"

    rows = conn.execute(query, params).fetchall()
    return [_term_dict(row) for row in rows]


@router.post("", status_code=201)
def create_term(body: TermCreate, conn: sqlite3.Connection = Depends(db_module.get_db)):
    try:
        cur = conn.execute(
            "INSERT INTO terms (lemma, translation, notes, status, deck, sentence, "
            "source_book_id, source_page) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                body.lemma,
                body.translation,
                body.notes,
                body.status,
                body.deck,
                body.sentence,
                body.source_book_id,
                body.source_page,
            ),
        )
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="a term with this lemma already exists")
    conn.commit()
    return _term_dict(_get_term_or_404(conn, cur.lastrowid))


@router.patch("/{term_id}")
def patch_term(
    term_id: int, body: TermPatch, conn: sqlite3.Connection = Depends(db_module.get_db)
):
    row = _get_term_or_404(conn, term_id)
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        return _term_dict(row)

    if "lemma" in fields and fields["lemma"] != row["lemma"]:
        conflict = conn.execute(
            "SELECT id FROM terms WHERE lemma = ? AND id != ?", (fields["lemma"], term_id)
        ).fetchone()
        if conflict is not None:
            raise HTTPException(status_code=409, detail="a term with this lemma already exists")

    becomes_dirty = row["anki_note_id"] is not None and any(
        key in _DIRTY_TRIGGER_FIELDS and value != row[key] for key, value in fields.items()
    )

    set_parts = [f"{key} = ?" for key in fields]
    values = list(fields.values())
    set_parts.append("updated = CURRENT_TIMESTAMP")
    if becomes_dirty:
        set_parts.append("anki_dirty = 1")

    conn.execute(
        f"UPDATE terms SET {', '.join(set_parts)} WHERE id = ?", (*values, term_id)
    )
    conn.commit()
    return _term_dict(_get_term_or_404(conn, term_id))


@router.delete("/{term_id}", status_code=204)
def delete_term(term_id: int, conn: sqlite3.Connection = Depends(db_module.get_db)):
    _get_term_or_404(conn, term_id)
    conn.execute("DELETE FROM terms WHERE id = ?", (term_id,))
    conn.commit()
