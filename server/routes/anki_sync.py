"""POST /api/anki/sync. See docs/SPEC.md section 8."""
import json
import sqlite3

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from .. import anki
from .. import db as db_module
from .terms import _back_items_for, _forms_for

router = APIRouter(prefix="/api/anki", tags=["anki"])

DEFAULT_DECK = "Default"
MATURE_DAYS = 21


def _render_legacy_examples(examples: list[str], sentence: str) -> str:
    """Examples for a term without Back chips: the flat `examples` list plus the sentence."""
    parts = [*examples]
    if sentence:
        parts.append(sentence)
    return "<br>".join(parts)


def _front_entries(conn: sqlite3.Connection, term_id: int, lemma: str) -> list[dict]:
    """The Front stack: the lemma (group '') then each form, which is its own group key."""
    return [{"text": lemma, "kind": "lemma", "group": ""}] + [
        {"text": f["text"], "kind": f["kind"], "group": f["text"]}
        for f in _forms_for(conn, term_id)
    ]


def _render_korean(front_entries: list[dict]) -> str:
    """One entry renders bare; several render numbered so Back labels can point at them."""
    if len(front_entries) == 1:
        return front_entries[0]["text"]
    return "<br>".join(f"{i + 1}. {e['text']}" for i, e in enumerate(front_entries))


def _label_items(
    front_entries: list[dict], back_items: list[dict]
) -> list[tuple[str, dict]]:
    """Label each back item: `1.` for one item per entry, `1a.`/`1b.` for several, none
    when there is a single entry. Back and Examples share this so labels line up."""
    num_fronts = len(front_entries)
    by_group: dict[str, list[dict]] = {}
    for item in back_items:
        by_group.setdefault(item["group"], []).append(item)

    out: list[tuple[str, dict]] = []
    for i, entry in enumerate(front_entries):
        items = by_group.get(entry["group"], [])
        if len(items) == 1:
            label = f"{i + 1}." if num_fronts > 1 else ""
            out.append((label, items[0]))
        elif len(items) > 1:
            for j, item in enumerate(items):
                letter = chr(ord("a") + j)
                label = f"{i + 1}{letter}." if num_fronts > 1 else f"{letter}."
                out.append((label, item))
    return out


def _render_english(labeled: list[tuple[str, dict]]) -> str:
    return "<br>".join(f"{label} {item['text']}".strip() for label, item in labeled)


def _render_examples_field(
    sentence: str, labeled: list[tuple[str, dict]], notes: str
) -> str:
    """Sentence, labeled Korean definitions, then notes, as blank-line separated blocks."""
    definitions = [
        f"{label} {item['korean_def']}".strip()
        for label, item in labeled
        if item["kind"] == "dict" and item["korean_def"]
    ]
    blocks = []
    if sentence:
        blocks.append([sentence])
    if definitions:
        blocks.append(definitions)
    if notes:
        blocks.append([notes])
    return "<br><br>".join("<br>".join(block) for block in blocks)


def _render_two_way(conn: sqlite3.Connection, row: sqlite3.Row) -> tuple[str, str, str]:
    """Korean/English/Examples for the two-way model."""
    front_entries = _front_entries(conn, row["id"], row["lemma"])
    korean = _render_korean(front_entries)
    # Pre-Epic-32 hanja chips are grouped by a spelling no front entry has; keep them
    # on the card under the lemma.
    groups = {e["group"] for e in front_entries}
    back_items = [
        it if it["group"] in groups else {**it, "group": ""}
        for it in _back_items_for(conn, row["id"])
    ]
    if not back_items:
        english = row["translation"]
        examples = _render_legacy_examples(json.loads(row["examples"]), row["sentence"])
    else:
        labeled = _label_items(front_entries, back_items)
        english = _render_english(labeled)
        examples = _render_examples_field(row["sentence"], labeled, row["notes"])
    return korean, english, examples


@router.post("/sync")
def sync(conn: sqlite3.Connection = Depends(db_module.get_db)):
    try:
        anki.ping()
    except anki.AnkiError as e:
        return JSONResponse(status_code=503, content={"error": str(e)})

    # Best-effort: if the model is missing, its addNote calls fail per note in `failed`.
    try:
        anki.ensure_model()
    except anki.AnkiError:
        pass

    new_terms = conn.execute(
        "SELECT * FROM terms WHERE status = 'learning' AND anki_note_id IS NULL"
    ).fetchall()
    dirty_terms = conn.execute(
        "SELECT * FROM terms WHERE anki_dirty = 1 AND anki_note_id IS NOT NULL "
        "AND anki_model IS NOT ?",
        (anki.LEGACY_HANJA_MODEL,),
    ).fetchall()

    for deck in {row["deck"] or DEFAULT_DECK for row in (*new_terms, *dirty_terms)}:
        try:
            anki.create_deck(deck)
        except anki.AnkiError:
            pass  # best-effort; a real problem surfaces on the addNote/updateNoteFields call below

    added = 0
    updated = 0
    failed: list[dict] = []

    # Stamp anki_model so later edits update the right note type.
    for row in new_terms:
        try:
            korean, english, examples = _render_two_way(conn, row)
            note_id = anki.add_note_model(row["deck"] or DEFAULT_DECK, korean, english, examples)
            conn.execute(
                "UPDATE terms SET anki_note_id = ?, anki_model = ?, anki_dirty = 0 "
                "WHERE id = ?",
                (note_id, anki.MODEL_NAME, row["id"]),
            )
            added += 1
        except anki.AnkiError as e:
            failed.append({"lemma": row["lemma"], "error": str(e)})

    for row in dirty_terms:
        try:
            korean, english, examples = _render_two_way(conn, row)
            anki.update_note_model(row["anki_note_id"], korean, english, examples)
            anki.move_note_to_deck(row["anki_note_id"], row["deck"] or DEFAULT_DECK)
            conn.execute("UPDATE terms SET anki_dirty = 0 WHERE id = ?", (row["id"],))
            updated += 1
        except anki.AnkiError as e:
            failed.append({"lemma": row["lemma"], "error": str(e)})

    promoted = 0
    synced = conn.execute(
        "SELECT id, anki_note_id FROM terms WHERE status = 'learning' AND anki_note_id IS NOT NULL"
    ).fetchall()
    if synced:
        try:
            intervals = anki.min_intervals([row["anki_note_id"] for row in synced])
        except anki.AnkiError:
            intervals = {}
        for row in synced:
            if intervals.get(row["anki_note_id"], 0) >= MATURE_DAYS:
                conn.execute("UPDATE terms SET status = 'known' WHERE id = ?", (row["id"],))
                promoted += 1

    conn.commit()
    return {"added": added, "updated": updated, "failed": failed, "promoted": promoted}
