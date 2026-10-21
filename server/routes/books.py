"""Books & pages API. See docs/SPEC.md section 5."""
import json
import sqlite3
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import db as db_module
from ..difficulty import (
    frequency_grades,
    known_lemmas,
    score_general_difficulty,
    score_text,
)
from ..paging import snap_back, snap_forward, split_pages
from ..tokenizer import tokenize
from .terms import _back_items_for, _forms_for, hanja_list

router = APIRouter(prefix="/api/books", tags=["books"])

BookStatus = Literal["library", "candidate", "discarded"]

# 20k covers a median book whole while keeping one response's token JSON phone-sized;
# MAX stops a hand-crafted `?window=` from forcing a huge tokenize.
DEFAULT_TEXT_WINDOW = 20_000
MAX_TEXT_WINDOW = 50_000


class BookCreate(BaseModel):
    title: str
    text: str
    source: str = "paste"
    topic: str = ""
    tags: list[str] = []
    source_url: str = ""
    source_ref: str | None = None
    fetched: str | None = None
    status: BookStatus = "library"


class BookPatch(BaseModel):
    # No upper bound: /text clamps anything past the end.
    current_offset: int | None = Field(default=None, ge=0)
    title: str | None = None
    topic: str | None = None
    tags: list[str] | None = None
    archived: bool | None = None
    read: bool | None = None
    status: BookStatus | None = None


def _book_dict(conn: sqlite3.Connection, book_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM books WHERE id = ?", (book_id,)).fetchone()
    if row is None:
        return None
    page_count = conn.execute(
        "SELECT COUNT(*) FROM pages WHERE book_id = ?", (book_id,)
    ).fetchone()[0]
    total_chars = conn.execute(
        "SELECT COALESCE(SUM(LENGTH(content)), 0) FROM pages WHERE book_id = ?",
        (book_id,),
    ).fetchone()[0]
    return {
        **dict(row),
        "page_count": page_count,
        "total_chars": total_chars,
        "tags": json.loads(row["tags"]),
        "archived": bool(row["archived"]),
        "read": bool(row["read"]),
    }


def _get_book_or_404(conn: sqlite3.Connection, book_id: int) -> dict:
    book = _book_dict(conn, book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="book not found")
    return book


class DuplicateSourceRef(Exception):
    """Raised when source_ref collides with an already-imported book."""


def _purge_queue_text(conn: sqlite3.Connection, book_ids: list[int]) -> None:
    """Drop the text of discarded feed candidates (article/yt only; manual imports are
    kept). The `books` row stays so dedup and curation stats still see it."""
    if not book_ids:
        return
    placeholders = ", ".join("?" for _ in book_ids)
    conn.execute(
        f"DELETE FROM pages WHERE book_id IN ("
        f"SELECT id FROM books WHERE id IN ({placeholders}) "
        f"AND source IN ('article', 'yt'))",
        book_ids,
    )


def insert_book(
    conn: sqlite3.Connection,
    *,
    title: str,
    text: str,
    source: str,
    topic: str = "",
    tags: list[str] | None = None,
    source_url: str = "",
    source_ref: str | None = None,
    fetched: str | None = None,
    status: BookStatus = "library",
    duration_seconds: int | None = None,
    feed_id: int | None = None,
) -> dict:
    """Insert the book row and its page slices; DuplicateSourceRef on a source_ref clash."""
    word_count = len(text.split())
    try:
        cur = conn.execute(
            "INSERT INTO books (title, source, topic, tags, source_url, source_ref, "
            "fetched, status, word_count, duration_seconds, feed_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                title, source, topic, json.dumps(tags or []), source_url, source_ref,
                fetched, status, word_count, duration_seconds, feed_id,
            ),
        )
    except sqlite3.IntegrityError:
        raise DuplicateSourceRef(source_ref)
    book_id = cur.lastrowid
    pages = split_pages(text)
    conn.executemany(
        "INSERT INTO pages (book_id, page_no, content) VALUES (?, ?, ?)",
        [(book_id, i + 1, page) for i, page in enumerate(pages)],
    )
    conn.commit()
    return _book_dict(conn, book_id)


def _score_and_cache(
    conn: sqlite3.Connection,
    book_id: int,
    text: str,
    known: set[str] | None = None,
    frequency: dict[str, str] | None = None,
) -> dict:
    """Compute personal + general difficulty and cache it on the book row. A fetch run
    passes `known`/`frequency` in so they load once, not once per candidate."""
    if known is None:
        known = known_lemmas(conn)
    if frequency is None:
        frequency = frequency_grades(conn)
    personal = score_text(text, known, frequency)
    general = score_general_difficulty(text, frequency)
    conn.execute(
        "UPDATE books SET coverage = ?, new_per_page = ?, general_coverage = ?, "
        "general_level = ?, scored_at = CURRENT_TIMESTAMP WHERE id = ?",
        (
            personal["coverage"],
            personal["new_per_page"],
            general["general_coverage"],
            general["general_level"],
            book_id,
        ),
    )
    conn.commit()
    return _book_dict(conn, book_id)


# Sorted server-side so LIMIT/OFFSET pages stay consistent.
_SORT_CLAUSES = {
    "recent": "id DESC",
    # never-opened books sort last, newest-added first among them
    "opened": "(last_opened IS NULL) ASC, last_opened DESC, id DESC",
    "easiest": "(new_per_page IS NULL) ASC, new_per_page ASC",
    # 250 wpm for text, real yt-dlp duration for video
    "shortest": (
        "COALESCE(CASE WHEN source = 'yt' THEN duration_seconds / 60.0 "
        "ELSE word_count / 250.0 END, 999999999) ASC"
    ),
}


@router.get("")
def list_books(
    topic: str | None = None,
    archived: bool | None = None,
    source: str | None = None,
    status: BookStatus | None = None,
    sort: str | None = None,
    limit: int | None = None,
    offset: int = 0,
    conn: sqlite3.Connection = Depends(db_module.get_db),
):
    # Defaults to the library so Queue candidates and discards stay out of the main list.
    query = "SELECT id FROM books WHERE 1=1"
    params: list = []
    if topic:
        query += " AND topic = ?"
        params.append(topic)
    if archived is not None:
        query += " AND archived = ?"
        params.append(int(archived))
    if source:
        query += " AND source = ?"
        params.append(source)
    query += " AND status = ?"
    params.append(status or "library")
    query += f" ORDER BY {_SORT_CLAUSES.get(sort, 'id')}"
    if limit is not None:
        query += " LIMIT ? OFFSET ?"
        params.append(limit)
        params.append(offset)
    rows = conn.execute(query, params).fetchall()
    return [_book_dict(conn, row["id"]) for row in rows]


@router.post("", status_code=201)
def create_book(body: BookCreate, conn: sqlite3.Connection = Depends(db_module.get_db)):
    try:
        return insert_book(
            conn,
            title=body.title,
            text=body.text,
            source=body.source,
            topic=body.topic,
            tags=body.tags,
            source_url=body.source_url,
            source_ref=body.source_ref,
            fetched=body.fetched,
            status=body.status,
        )
    except DuplicateSourceRef:
        raise HTTPException(
            status_code=409, detail="a book with this source_ref already exists"
        )


@router.get("/{book_id}")
def get_book(book_id: int, conn: sqlite3.Connection = Depends(db_module.get_db)):
    book = _get_book_or_404(conn, book_id)
    return {
        "id": book["id"],
        "title": book["title"],
        "current_offset": book["current_offset"],
        "total_chars": book["total_chars"],
        "page_count": book["page_count"],
    }


@router.patch("/{book_id}")
def patch_book(
    book_id: int, body: BookPatch, conn: sqlite3.Connection = Depends(db_module.get_db)
):
    _get_book_or_404(conn, book_id)
    fields = body.model_dump(exclude_unset=True)
    if "tags" in fields:
        fields["tags"] = json.dumps(fields["tags"])
    # Auto-expiry sets 'expired' in its own UPDATE (routes/feeds.py).
    if fields.get("status") == "discarded":
        fields["discard_reason"] = "user"
    if fields:
        set_clause = ", ".join(f"{key} = ?" for key in fields)
        conn.execute(
            f"UPDATE books SET {set_clause} WHERE id = ?",
            (*fields.values(), book_id),
        )
        conn.commit()
    if fields.get("status") == "discarded":
        _purge_queue_text(conn, [book_id])
        conn.commit()
    return _book_dict(conn, book_id)


@router.delete("/{book_id}", status_code=204)
def delete_book(book_id: int, conn: sqlite3.Connection = Depends(db_module.get_db)):
    _get_book_or_404(conn, book_id)
    conn.execute("DELETE FROM books WHERE id = ?", (book_id,))
    conn.commit()


@router.post("/{book_id}/score")
def score_book(book_id: int, conn: sqlite3.Connection = Depends(db_module.get_db)):
    """Compute the book's personal + general difficulty and cache it on the row."""
    _get_book_or_404(conn, book_id)
    rows = conn.execute(
        "SELECT content FROM pages WHERE book_id = ? ORDER BY page_no", (book_id,)
    ).fetchall()
    text = "\n".join(row["content"] for row in rows)
    return _score_and_cache(conn, book_id, text)


def _term_summary(row: sqlite3.Row) -> dict:
    """The reader popover's view of a term; forms and back_items are attached after."""
    return {
        "id": row["id"],
        "lemma": row["lemma"],
        "translation": row["translation"],
        "notes": row["notes"],
        "status": row["status"],
        "deck": row["deck"],
        "forms": [],
        "examples": json.loads(row["examples"]),
        "back_items": [],
        "hanja": hanja_list(row["hanja"]),
    }


def _terms_for_lemmas(conn: sqlite3.Connection, lemmas: set[str]) -> dict:
    """Every saved term a set of window token lemmas should light up, keyed by the
    string that matched (the term's own lemma, or one of its extra `forms`)."""
    terms: dict = {}
    if lemmas:
        placeholders = ", ".join("?" for _ in lemmas)
        rows = conn.execute(
            f"SELECT id, lemma, translation, notes, status, deck, examples, hanja FROM terms "
            f"WHERE lemma IN ({placeholders})",
            tuple(lemmas),
        ).fetchall()
        for row in rows:
            terms[row["lemma"]] = _term_summary(row)
        # A term also lights up via its forms; a direct lemma match wins over a form.
        form_rows = conn.execute(
            f"SELECT tf.form, t.id, t.lemma, t.translation, t.notes, t.status, t.deck, "
            f"t.examples, t.hanja FROM term_forms tf JOIN terms t ON t.id = tf.term_id "
            f"WHERE tf.form IN ({placeholders})",
            tuple(lemmas),
        ).fetchall()
        for row in form_rows:
            if row["form"] not in terms:
                terms[row["form"]] = _term_summary(row)
        # Full forms + back_items so the popover can rebuild the saved card when tapped.
        matched_ids = {entry["id"] for entry in terms.values()}
        if matched_ids:
            forms_by_term = {tid: _forms_for(conn, tid) for tid in matched_ids}
            back_items_by_term = {tid: _back_items_for(conn, tid) for tid in matched_ids}
            for entry in terms.values():
                entry["forms"] = forms_by_term.get(entry["id"], [])
                entry["back_items"] = back_items_by_term.get(entry["id"], [])

    return terms


def _book_text(conn: sqlite3.Connection, book_id: int) -> str:
    """The full text. Page slices are contiguous, so joining with "" is lossless."""
    return "".join(
        row["content"] for row in conn.execute(
            "SELECT content FROM pages WHERE book_id = ? ORDER BY page_no", (book_id,)
        )
    )


@router.get("/{book_id}/text")
def get_text(
    book_id: int,
    offset: int = 0,
    window: int = DEFAULT_TEXT_WINDOW,
    conn: sqlite3.Connection = Depends(db_module.get_db),
):
    """A window of the book for the client-side paginator, snapped outward to sentence
    boundaries. Token offsets are relative to `content`; absolute is `offset + s`."""
    _get_book_or_404(conn, book_id)
    # The reader's display call, so it's what "most recently opened" reflects.
    conn.execute("UPDATE books SET last_opened = CURRENT_TIMESTAMP WHERE id = ?", (book_id,))
    conn.commit()

    text = _book_text(conn, book_id)
    window = max(1, min(window, MAX_TEXT_WINDOW))
    start = snap_back(text, max(0, min(offset, len(text))))
    end = snap_forward(text, min(start + window, len(text)))

    content = text[start:end]
    tokens = tokenize(content)
    return {
        "offset": start,
        "total_chars": len(text),
        "content": content,
        "tokens": [
            {"s": t.s, "e": t.e, "surface": t.surface, "lemma": t.lemma, "pos": t.pos}
            for t in tokens
        ],
        "terms": _terms_for_lemmas(conn, {t.lemma for t in tokens}),
    }
