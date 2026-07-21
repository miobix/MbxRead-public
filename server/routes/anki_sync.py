"""POST /api/anki/sync. See docs/SPEC.md section 8."""
import sqlite3

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from .. import anki
from .. import db as db_module

router = APIRouter(prefix="/api/anki", tags=["anki"])

DEFAULT_DECK = "Default"


def _render_back(translation: str, sentence: str) -> str:
    if sentence:
        return f"{translation}<br><br><i>{sentence}</i>"
    return translation


@router.post("/sync")
def sync(conn: sqlite3.Connection = Depends(db_module.get_db)):
    try:
        anki.ping()
    except anki.AnkiError as e:
        return JSONResponse(status_code=503, content={"error": str(e)})

    new_terms = conn.execute(
        "SELECT * FROM terms WHERE status = 'learning' AND anki_note_id IS NULL"
    ).fetchall()
    dirty_terms = conn.execute(
        "SELECT * FROM terms WHERE anki_dirty = 1 AND anki_note_id IS NOT NULL"
    ).fetchall()

    for deck in {row["deck"] or DEFAULT_DECK for row in (*new_terms, *dirty_terms)}:
        try:
            anki.create_deck(deck)
        except anki.AnkiError:
            pass  # best-effort; a real problem surfaces on the addNote/updateNoteFields call below

    added = 0
    updated = 0
    failed: list[dict] = []

    for row in new_terms:
        back = _render_back(row["translation"], row["sentence"])
        try:
            note_id = anki.add_note(row["deck"] or DEFAULT_DECK, row["lemma"], back)
            conn.execute(
                "UPDATE terms SET anki_note_id = ?, anki_dirty = 0 WHERE id = ?",
                (note_id, row["id"]),
            )
            added += 1
        except anki.AnkiError as e:
            failed.append({"lemma": row["lemma"], "error": str(e)})

    for row in dirty_terms:
        back = _render_back(row["translation"], row["sentence"])
        try:
            anki.update_note_fields(row["anki_note_id"], row["lemma"], back)
            conn.execute("UPDATE terms SET anki_dirty = 0 WHERE id = ?", (row["id"],))
            updated += 1
        except anki.AnkiError as e:
            failed.append({"lemma": row["lemma"], "error": str(e)})

    conn.commit()
    return {"added": added, "updated": updated, "failed": failed}
