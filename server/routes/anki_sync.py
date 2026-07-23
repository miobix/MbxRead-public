"""POST /api/anki/sync. See docs/SPEC.md section 8."""
import json
import sqlite3

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from .. import anki
from .. import db as db_module

router = APIRouter(prefix="/api/anki", tags=["anki"])

DEFAULT_DECK = "Default"


def _render_back(translation: str, sentence: str) -> str:
    """Legacy `Basic` note back (translation + captured sentence)."""
    if sentence:
        return f"{translation}<br><br><i>{sentence}</i>"
    return translation


def _forms(conn: sqlite3.Connection, term_id: int) -> list[str]:
    return [
        r["form"]
        for r in conn.execute(
            "SELECT form FROM term_forms WHERE term_id = ? ORDER BY rowid", (term_id,)
        )
    ]


def _render_korean(conn: sqlite3.Connection, term_id: int, lemma: str) -> str:
    """The card's Korean face: the lemma plus any extra forms, e.g.
    `승인 / 승인서 / 승인하다`. No forms → just the lemma (Epic 20)."""
    return " / ".join([lemma, *_forms(conn, term_id)])


def _render_examples(examples: list[str], sentence: str) -> str:
    """Epic 21: the custom note's Examples field — clicked-in krdict collocations
    plus the captured reading sentence, one per line. Rendered on the *back* of
    both cards only."""
    parts = [*examples]
    if sentence:
        parts.append(sentence)
    return "<br>".join(parts)


@router.post("/sync")
def sync(conn: sqlite3.Connection = Depends(db_module.get_db)):
    try:
        anki.ping()
    except anki.AnkiError as e:
        return JSONResponse(status_code=503, content={"error": str(e)})

    # Best-effort like create_deck below — if the model can't be created, the
    # per-note addNote calls fail and land in `failed`, isolated from the rest.
    try:
        anki.ensure_model()
    except anki.AnkiError:
        pass

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

    # New terms → the Epic 21 two-way model (Korean/English/Examples), tagged with
    # the model name so later edits update it in place rather than the legacy path.
    for row in new_terms:
        korean = _render_korean(conn, row["id"], row["lemma"])
        examples = _render_examples(json.loads(row["examples"]), row["sentence"])
        try:
            note_id = anki.add_note_model(
                row["deck"] or DEFAULT_DECK, korean, row["translation"], examples
            )
            conn.execute(
                "UPDATE terms SET anki_note_id = ?, anki_model = ?, anki_dirty = 0 "
                "WHERE id = ?",
                (note_id, anki.MODEL_NAME, row["id"]),
            )
            added += 1
        except anki.AnkiError as e:
            failed.append({"lemma": row["lemma"], "error": str(e)})

    for row in dirty_terms:
        korean = _render_korean(conn, row["id"], row["lemma"])
        try:
            if row["anki_model"] == anki.MODEL_NAME:
                examples = _render_examples(json.loads(row["examples"]), row["sentence"])
                anki.update_note_model(
                    row["anki_note_id"], korean, row["translation"], examples
                )
            else:
                # Legacy `Basic` note (synced before Epic 21): keep the Front/Back
                # shape so its SRS scheduling history is preserved.
                back = _render_back(row["translation"], row["sentence"])
                anki.update_note_fields(row["anki_note_id"], korean, back)
            conn.execute("UPDATE terms SET anki_dirty = 0 WHERE id = ?", (row["id"],))
            updated += 1
        except anki.AnkiError as e:
            failed.append({"lemma": row["lemma"], "error": str(e)})

    conn.commit()
    return {"added": added, "updated": updated, "failed": failed}
