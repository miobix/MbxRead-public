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
# same generic dirty check as the plain text columns. `translation` also changes
# whenever `back_items` (Epic 22) does — see the derived-mirror note on patch_term.
_DIRTY_TRIGGER_FIELDS = {"translation", "notes", "deck", "sentence", "examples", "hanja"}


class FormIn(BaseModel):
    text: str
    kind: Literal["dict", "manual"] = "manual"


class BackItemIn(BaseModel):
    group: str = ""  # '' = the lemma's group; else must match a form's text
    kind: Literal["dict", "translate", "manual"]
    text: str
    korean_def: str = ""


class TermCreate(BaseModel):
    lemma: str
    translation: str
    notes: str = ""
    status: Status = "learning"
    deck: str = ""
    sentence: str = ""
    # Epic 20: extra surface forms this term also covers (승인서/승인하다 under 승인).
    # Epic 22: each now carries `kind` (dict-clicked vs hand-typed) for the popover.
    forms: list[FormIn] = []
    # Epic 21: usage examples (krdict collocations + the reading sentence) shown on
    # the back of the Anki card. Display-only, never matched against page tokens.
    examples: list[str] = []
    # Epic 22: the structured card builder's Back chips, grouped by `group`.
    back_items: list[BackItemIn] = []
    # Epic 16: which book/page this term was first saved from (reader passes both).
    # Nullable — terms saved outside the reader (e.g. from /terms) have no origin.
    source_book_id: int | None = None
    source_page: int | None = None
    # Epic 25/26: hanja spellings for on-demand Sino-Korean word saves, one per
    # sense (시장 = 市場 market + 市長 mayor), ordered. Empty for every reading-flow
    # term. Each sense's meanings are the back_items whose `group` is that spelling.
    hanja: list[str] = []


class TermPatch(BaseModel):
    lemma: str | None = None
    translation: str | None = None
    notes: str | None = None
    status: Status | None = None
    deck: str | None = None
    sentence: str | None = None
    forms: list[FormIn] | None = None
    examples: list[str] | None = None
    back_items: list[BackItemIn] | None = None
    hanja: list[str] | None = None


def _normalize_forms(forms: list[dict], lemma: str) -> list[dict]:
    """Trim, drop blanks and the lemma itself, and dedupe by text (keeping the
    first-seen `kind`) while keeping order."""
    seen: dict[str, str] = {}
    for f in forms:
        text = (f.get("text") or "").strip()
        kind = f.get("kind") or "manual"
        if text and text != lemma:
            seen.setdefault(text, kind)
    return [{"text": text, "kind": kind} for text, kind in seen.items()]


def _normalize_examples(examples: list[str]) -> list[str]:
    """Trim, drop blanks, and dedupe while keeping order."""
    seen: dict[str, None] = {}
    for raw in examples:
        ex = raw.strip()
        if ex:
            seen.setdefault(ex, None)
    return list(seen)


def _normalize_hanja(hanja: list[str]) -> list[str]:
    """Trim, drop blanks, and dedupe while keeping order — the sense list."""
    seen: dict[str, None] = {}
    for raw in hanja:
        text = raw.strip()
        if text:
            seen.setdefault(text, None)
    return list(seen)


def hanja_list(value: str | None) -> list[str]:
    """Parse the stored column. Tolerates a pre-Epic-26 bare spelling and a NULL so
    a caller never has to care whether _backfill_hanja_json has run yet."""
    text = (value or "").strip()
    if not text:
        return []
    if not text.startswith("["):
        return [text]
    return json.loads(text)


def _normalize_back_items(items: list[dict]) -> list[dict]:
    """Trim, drop blank-text items, and dedupe exact (group, kind, text) repeats
    while keeping order."""
    seen: set[tuple[str, str, str]] = set()
    out: list[dict] = []
    for it in items:
        group = (it.get("group") or "").strip()
        kind = it.get("kind")
        text = (it.get("text") or "").strip()
        korean_def = (it.get("korean_def") or "").strip()
        if not text:
            continue
        key = (group, kind, text)
        if key in seen:
            continue
        seen.add(key)
        out.append({"group": group, "kind": kind, "text": text, "korean_def": korean_def})
    return out


def _forms_for(conn: sqlite3.Connection, term_id: int) -> list[dict]:
    return [
        {"text": r["form"], "kind": r["kind"]}
        for r in conn.execute(
            "SELECT form, kind FROM term_forms WHERE term_id = ? ORDER BY rowid", (term_id,)
        )
    ]


def _set_forms(conn: sqlite3.Connection, term_id: int, forms: list[dict]) -> None:
    conn.execute("DELETE FROM term_forms WHERE term_id = ?", (term_id,))
    conn.executemany(
        "INSERT INTO term_forms (term_id, form, kind) VALUES (?, ?, ?)",
        [(term_id, f["text"], f["kind"]) for f in forms],
    )


def _back_items_for(conn: sqlite3.Connection, term_id: int) -> list[dict]:
    return [
        {
            "group": r["group_key"],
            "kind": r["kind"],
            "text": r["text"],
            "korean_def": r["korean_def"],
        }
        for r in conn.execute(
            "SELECT group_key, kind, text, korean_def FROM term_back_items "
            "WHERE term_id = ? ORDER BY id",
            (term_id,),
        )
    ]


def _set_back_items(conn: sqlite3.Connection, term_id: int, items: list[dict]) -> None:
    conn.execute("DELETE FROM term_back_items WHERE term_id = ?", (term_id,))
    conn.executemany(
        "INSERT INTO term_back_items (term_id, group_key, kind, text, korean_def) "
        "VALUES (?, ?, ?, ?, ?)",
        [(term_id, it["group"], it["kind"], it["text"], it["korean_def"]) for it in items],
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
        "back_items": _back_items_for(conn, row["id"]),
        "anki_note_id": row["anki_note_id"],
        "anki_dirty": bool(row["anki_dirty"]),
        "created": row["created"],
        "updated": row["updated"],
        "source_book_id": row["source_book_id"],
        "source_page": row["source_page"],
        "hanja": hanja_list(row["hanja"]),
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


@router.get("/by-lemma")
def get_term_by_lemma(lemma: str, conn: sqlite3.Connection = Depends(db_module.get_db)):
    """Exact-lemma lookup. The list endpoint's `q` is a LIKE across three columns,
    which can't answer "is this word already saved?" — the question the popover asks
    before it offers to append a hanja sense to an existing term (Epic 26)."""
    row = conn.execute("SELECT * FROM terms WHERE lemma = ?", (lemma.strip(),)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="term not found")
    return _term_dict(conn, row)


@router.post("", status_code=201)
def create_term(body: TermCreate, conn: sqlite3.Connection = Depends(db_module.get_db)):
    back_items = _normalize_back_items([it.model_dump() for it in body.back_items])
    # Epic 22: when the popover's card builder was used, `translation` is derived
    # from the Back chips (join order = group order), not typed directly — purely so
    # /terms' list/search/inline-edit still shows something sensible. An empty
    # back_items list (e.g. a direct API call, or /terms-style flat creation) leaves
    # `translation` exactly as given, unchanged from today's behavior.
    translation = "; ".join(it["text"] for it in back_items) if back_items else body.translation
    try:
        cur = conn.execute(
            "INSERT INTO terms (lemma, translation, notes, status, deck, sentence, "
            "examples, source_book_id, source_page, hanja) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                body.lemma,
                translation,
                body.notes,
                body.status,
                body.deck,
                body.sentence,
                json.dumps(_normalize_examples(body.examples)),
                body.source_book_id,
                body.source_page,
                json.dumps(_normalize_hanja(body.hanja), ensure_ascii=False),
            ),
        )
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="a term with this lemma already exists")
    _set_forms(
        conn,
        cur.lastrowid,
        _normalize_forms([f.model_dump() for f in body.forms], body.lemma),
    )
    _set_back_items(conn, cur.lastrowid, back_items)
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

    # `back_items` is not a terms column either — same treatment. Epic 22: whenever
    # the popover sends a (complete, replace-all) back_items array, `translation` is
    # re-derived from it, overriding anything separately sent — see create_term.
    back_items_provided = "back_items" in fields
    new_back_items = (
        _normalize_back_items(fields.pop("back_items") or []) if back_items_provided else None
    )
    if back_items_provided:
        fields["translation"] = (
            "; ".join(it["text"] for it in new_back_items) if new_back_items else ""
        )

    # `examples` IS a column (JSON), but the value arrives as a list — normalize and
    # re-encode it back into `fields` so the generic UPDATE + dirty check below both
    # handle it (it's in _DIRTY_TRIGGER_FIELDS; the DB stores its JSON string).
    if "examples" in fields:
        fields["examples"] = json.dumps(_normalize_examples(fields["examples"] or []))

    # Same treatment as `examples`: a real column whose value arrives as a list, so
    # re-encode it here and the generic UPDATE + dirty check below both just work.
    if "hanja" in fields:
        fields["hanja"] = json.dumps(_normalize_hanja(fields["hanja"] or []), ensure_ascii=False)

    if not fields and not forms_provided and not back_items_provided:
        return _term_dict(conn, row)

    if "lemma" in fields and fields["lemma"] != row["lemma"]:
        conflict = conn.execute(
            "SELECT id FROM terms WHERE lemma = ? AND id != ?", (fields["lemma"], term_id)
        ).fetchone()
        if conflict is not None:
            raise HTTPException(status_code=409, detail="a term with this lemma already exists")

    forms_changed = forms_provided and new_forms != _forms_for(conn, term_id)
    back_items_changed = (
        back_items_provided and new_back_items != _back_items_for(conn, term_id)
    )
    becomes_dirty = row["anki_note_id"] is not None and (
        any(key in _DIRTY_TRIGGER_FIELDS and value != row[key] for key, value in fields.items())
        or forms_changed
        or back_items_changed
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
    if back_items_provided:
        _set_back_items(conn, term_id, new_back_items)
    conn.commit()
    return _term_dict(conn, _get_term_or_404(conn, term_id))


class HanjaConvert(BaseModel):
    hanja: str
    back_items: list[BackItemIn]
    deck: str


@router.post("/{term_id}/convert-to-hanja")
def convert_to_hanja(
    term_id: int, body: HanjaConvert, conn: sqlite3.Connection = Depends(db_module.get_db)
):
    """Turn a reading-saved term into a hanja term in place (Epic 27). Same row, so the
    reader still highlights it and its sentence/examples/source survive; sync state is
    reset so the next sync adds a fresh Hanja-model note. The old Anki note is not
    touched (the response names it)."""
    row = _get_term_or_404(conn, term_id)
    if hanja_list(row["hanja"]):
        raise HTTPException(status_code=409, detail="term already has hanja; append a sense")
    senses = _normalize_hanja([body.hanja])
    if not senses:
        raise HTTPException(status_code=422, detail="hanja can't be empty")
    items = _normalize_back_items([{**it.model_dump(), "group": senses[0]} for it in body.back_items])
    conn.execute(
        "UPDATE terms SET deck = ?, hanja = ?, translation = ?, status = 'learning', "
        "anki_note_id = NULL, anki_model = NULL, anki_dirty = 0, updated = CURRENT_TIMESTAMP "
        "WHERE id = ?",
        (
            body.deck,
            json.dumps(senses, ensure_ascii=False),
            "; ".join(it["text"] for it in items),
            term_id,
        ),
    )
    _set_back_items(conn, term_id, items)
    conn.commit()
    return {
        **_term_dict(conn, _get_term_or_404(conn, term_id)),
        "previous": {
            "anki_note_id": row["anki_note_id"],
            "deck": row["deck"],
            "status": row["status"],
        },
    }


@router.delete("/{term_id}", status_code=204)
def delete_term(term_id: int, conn: sqlite3.Connection = Depends(db_module.get_db)):
    _get_term_or_404(conn, term_id)
    conn.execute("DELETE FROM terms WHERE id = ?", (term_id,))
    conn.commit()
