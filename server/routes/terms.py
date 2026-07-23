"""Terms API. See docs/SPEC.md section 5."""
import json
import sqlite3
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import db as db_module

router = APIRouter(prefix="/api/terms", tags=["terms"])

Status = Literal["learning", "known", "ignored"]
# A change to any of these re-syncs the Anki card. `examples` (Epic 21) is a real
# JSON column but the value is compared as its stored JSON string, so it fits the
# same generic dirty check as the plain text columns.
_DIRTY_TRIGGER_FIELDS = {"translation", "notes", "deck", "sentence", "examples"}


class TermCreate(BaseModel):
    lemma: str
    translation: str
    notes: str = ""
    status: Status = "learning"
    deck: str = ""
    sentence: str = ""
    # Epic 20: extra surface forms this term also covers (승인서/승인하다 under 승인).
    forms: list[str] = []
    # Epic 21: usage examples (krdict collocations + the reading sentence) shown on
    # the back of the Anki card. Display-only, never matched against page tokens.
    examples: list[str] = []
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
    forms: list[str] | None = None
    examples: list[str] | None = None


def _normalize_forms(forms: list[str], lemma: str) -> list[str]:
    """Trim, drop blanks and the lemma itself, and dedupe while keeping order."""
    seen: dict[str, None] = {}
    for raw in forms:
        form = raw.strip()
        if form and form != lemma:
            seen.setdefault(form, None)
    return list(seen)


def _normalize_examples(examples: list[str]) -> list[str]:
    """Trim, drop blanks, and dedupe while keeping order."""
    seen: dict[str, None] = {}
    for raw in examples:
        ex = raw.strip()
        if ex:
            seen.setdefault(ex, None)
    return list(seen)


def _forms_for(conn: sqlite3.Connection, term_id: int) -> list[str]:
    return [
        r["form"]
        for r in conn.execute(
            "SELECT form FROM term_forms WHERE term_id = ? ORDER BY rowid", (term_id,)
        )
    ]


def _set_forms(conn: sqlite3.Connection, term_id: int, forms: list[str]) -> None:
    conn.execute("DELETE FROM term_forms WHERE term_id = ?", (term_id,))
    conn.executemany(
        "INSERT INTO term_forms (term_id, form) VALUES (?, ?)",
        [(term_id, f) for f in forms],
    )


def _term_dict(conn: sqlite3.Connection, row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "lemma": row["lemma"],
        "translation": row["translation"],
        "notes": row["notes"],
        "status": row["status"],
        "deck": row["deck"],
        "sentence": row["sentence"],
        "forms": _forms_for(conn, row["id"]),
        "examples": json.loads(row["examples"]),
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
    return [_term_dict(conn, row) for row in rows]


@router.post("", status_code=201)
def create_term(body: TermCreate, conn: sqlite3.Connection = Depends(db_module.get_db)):
    try:
        cur = conn.execute(
            "INSERT INTO terms (lemma, translation, notes, status, deck, sentence, "
            "examples, source_book_id, source_page) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                body.lemma,
                body.translation,
                body.notes,
                body.status,
                body.deck,
                body.sentence,
                json.dumps(_normalize_examples(body.examples)),
                body.source_book_id,
                body.source_page,
            ),
        )
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="a term with this lemma already exists")
    _set_forms(conn, cur.lastrowid, _normalize_forms(body.forms, body.lemma))
    conn.commit()
    return _term_dict(conn, _get_term_or_404(conn, cur.lastrowid))


@router.patch("/{term_id}")
def patch_term(
    term_id: int, body: TermPatch, conn: sqlite3.Connection = Depends(db_module.get_db)
):
    row = _get_term_or_404(conn, term_id)
    fields = body.model_dump(exclude_unset=True)

    # `forms` is not a terms column — pull it out and persist it separately. It's a
    # dirty trigger like translation/deck (it changes the Anki card's Korean face).
    forms_provided = "forms" in fields
    new_forms = (
        _normalize_forms(fields.pop("forms") or [], fields.get("lemma", row["lemma"]))
        if forms_provided
        else None
    )

    # `examples` IS a column (JSON), but the value arrives as a list — normalize and
    # re-encode it back into `fields` so the generic UPDATE + dirty check below both
    # handle it (it's in _DIRTY_TRIGGER_FIELDS; the DB stores its JSON string).
    if "examples" in fields:
        fields["examples"] = json.dumps(_normalize_examples(fields["examples"] or []))

    if not fields and not forms_provided:
        return _term_dict(conn, row)

    if "lemma" in fields and fields["lemma"] != row["lemma"]:
        conflict = conn.execute(
            "SELECT id FROM terms WHERE lemma = ? AND id != ?", (fields["lemma"], term_id)
        ).fetchone()
        if conflict is not None:
            raise HTTPException(status_code=409, detail="a term with this lemma already exists")

    forms_changed = forms_provided and new_forms != _forms_for(conn, term_id)
    becomes_dirty = row["anki_note_id"] is not None and (
        any(key in _DIRTY_TRIGGER_FIELDS and value != row[key] for key, value in fields.items())
        or forms_changed
    )

    set_parts = [f"{key} = ?" for key in fields]
    values = list(fields.values())
    set_parts.append("updated = CURRENT_TIMESTAMP")
    if becomes_dirty:
        set_parts.append("anki_dirty = 1")

    conn.execute(
        f"UPDATE terms SET {', '.join(set_parts)} WHERE id = ?", (*values, term_id)
    )
    if forms_provided:
        _set_forms(conn, term_id, new_forms)
    conn.commit()
    return _term_dict(conn, _get_term_or_404(conn, term_id))


@router.delete("/{term_id}", status_code=204)
def delete_term(term_id: int, conn: sqlite3.Connection = Depends(db_module.get_db)):
    _get_term_or_404(conn, term_id)
    conn.execute("DELETE FROM terms WHERE id = ?", (term_id,))
    conn.commit()
