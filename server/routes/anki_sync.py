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


def _render_back(translation: str, sentence: str) -> str:
    """Legacy `Basic` note back (translation + captured sentence)."""
    if sentence:
        return f"{translation}<br><br><i>{sentence}</i>"
    return translation


def _render_legacy_examples(examples: list[str], sentence: str) -> str:
    """Pre-Epic-22 Examples rendering, for a term the structured card builder has
    never touched (no term_back_items rows): clicked-in krdict collocations (the
    old flat `examples` JSON column) plus the captured reading sentence, one per
    line. Kept so an untouched term keeps syncing exactly as it did before this
    epic — the "legacy stays as it is" guarantee extended to the Anki side."""
    parts = [*examples]
    if sentence:
        parts.append(sentence)
    return "<br>".join(parts)


def _front_entries(conn: sqlite3.Connection, term_id: int, lemma: str) -> list[dict]:
    """The card's Front stack: the lemma's own group first, then each extra form
    (Epic 20), in save order. Each entry's `text` doubles as the group key used to
    look up its term_back_items — except the lemma, whose group key is the ''
    sentinel, so editing the lemma text never orphans its back items (Epic 22)."""
    return [{"text": lemma, "kind": "lemma"}] + [
        {"text": f["text"], "kind": f["kind"]} for f in _forms_for(conn, term_id)
    ]


def _group_key(front_entries: list[dict], index: int) -> str:
    return "" if index == 0 else front_entries[index]["text"]


def _render_korean(front_entries: list[dict]) -> str:
    """Front face. One entry (just the lemma — Epic 20's common no-forms case)
    renders exactly as before: the bare lemma, no numbering. Two or more entries
    render as a numbered stack, one per line, so the Back/Examples labels below
    have something to reference (Epic 22)."""
    if len(front_entries) == 1:
        return front_entries[0]["text"]
    return "<br>".join(f"{i + 1}. {e['text']}" for i, e in enumerate(front_entries))


def _label_items(
    front_entries: list[dict], back_items: list[dict]
) -> list[tuple[str, dict]]:
    """Pairs every back item with its display label. A front entry with exactly
    one back item gets a bare number (or no label at all, if there's only one
    front entry too — today's simple one-word-one-meaning case); a front entry
    with several back items letters them `1a.`/`1b.` so it's unambiguous which
    word they came from. Back and Examples both render from this same list, so
    their labels always line up."""
    num_fronts = len(front_entries)
    by_group: dict[str, list[dict]] = {}
    for item in back_items:
        by_group.setdefault(item["group"], []).append(item)

    out: list[tuple[str, dict]] = []
    for i, entry in enumerate(front_entries):
        items = by_group.get(_group_key(front_entries, i), [])
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
    """Epic 22: the reading sentence, then each dict-sourced item's Korean
    definition (its krdict example, if any, glued directly onto the end — no
    separator — at add-time in the popover), labeled to match the Back field, then
    the free-typed Notes block last. The three blocks (sentence / definitions /
    notes) are blank-line separated so the captured sentence doesn't crowd the first
    definition on the Anki card."""
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
    # One <br> between lines within a block, a blank line (<br><br>) between blocks.
    return "<br><br>".join("<br>".join(block) for block in blocks)


def _render_two_way(conn: sqlite3.Connection, row: sqlite3.Row) -> tuple[str, str, str]:
    """Korean/English/Examples for the two-way model. A term with no back_items
    yet (never touched by the Epic 22 popover) renders English/Examples exactly as
    it did before this epic — flat `translation`, old `examples` JSON column."""
    front_entries = _front_entries(conn, row["id"], row["lemma"])
    korean = _render_korean(front_entries)
    back_items = _back_items_for(conn, row["id"])
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
        korean, english, examples = _render_two_way(conn, row)
        try:
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
            if row["anki_model"] == anki.MODEL_NAME:
                korean, english, examples = _render_two_way(conn, row)
                anki.update_note_model(row["anki_note_id"], korean, english, examples)
            else:
                # Legacy `Basic` note (synced before Epic 21): keep the Front/Back
                # shape so its SRS scheduling history is preserved.
                front_entries = _front_entries(conn, row["id"], row["lemma"])
                korean = _render_korean(front_entries)
                back = _render_back(row["translation"], row["sentence"])
                anki.update_note_fields(row["anki_note_id"], korean, back)
            conn.execute("UPDATE terms SET anki_dirty = 0 WHERE id = ?", (row["id"],))
            updated += 1
        except anki.AnkiError as e:
            failed.append({"lemma": row["lemma"], "error": str(e)})

    conn.commit()
    return {"added": added, "updated": updated, "failed": failed}
