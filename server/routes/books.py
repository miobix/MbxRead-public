"""Books & pages API. See docs/SPEC.md section 5."""
import json
import sqlite3
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import db as db_module
from ..difficulty import (
    frequency_grades,
    known_lemmas,
    score_general_difficulty,
    score_text,
)
from ..paging import split_pages
from ..tokenizer import tokenize
from .settings import get_page_size

router = APIRouter(prefix="/api/books", tags=["books"])

BookStatus = Literal["library", "candidate", "discarded"]


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
    current_page: int | None = None
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
    return {
        "id": row["id"],
        "title": row["title"],
        "source": row["source"],
        "current_page": row["current_page"],
        "page_count": page_count,
        "created": row["created"],
        "coverage": row["coverage"],
        "new_per_page": row["new_per_page"],
        "scored_at": row["scored_at"],
        "topic": row["topic"],
        "tags": json.loads(row["tags"]),
        "source_url": row["source_url"],
        "source_ref": row["source_ref"],
        "fetched": row["fetched"],
        "archived": bool(row["archived"]),
        "read": bool(row["read"]),
        "status": row["status"],
        "general_coverage": row["general_coverage"],
        "general_level": row["general_level"],
        "word_count": row["word_count"],
        "duration_seconds": row["duration_seconds"],
        "feed_id": row["feed_id"],
        "discard_reason": row["discard_reason"],
    }


def _get_book_or_404(conn: sqlite3.Connection, book_id: int) -> dict:
    book = _book_dict(conn, book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="book not found")
    return book


class DuplicateSourceRef(Exception):
    """Raised when source_ref collides with an already-imported book."""


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
    """Shared by the paste/txt route, the Epic 12 importers, and Epic 15's feed
    fetcher: insert the book row + split pages, or raise DuplicateSourceRef on a
    source_ref collision. word_count (Epic 18) is derived from `text` for every
    source; duration_seconds is only ever passed for source='yt' (real yt-dlp
    video length, not a transcript-based estimate). feed_id (Epic 19) is only
    ever passed by routes/feeds.py — manual imports leave it NULL."""
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
    pages = split_pages(text, get_page_size(conn))
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
    """Shared by POST /api/books/{id}/score and Epic 15's feed fetcher: compute
    both personal (score_text) and general/public (score_general_difficulty)
    difficulty and cache all five fields onto the book row under one scored_at.
    `known`/`frequency` are optional so a caller scoring many candidates in one
    fetch run can load them once and pass them through, rather than re-querying
    per item."""
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


@router.get("")
def list_books(
    topic: str | None = None,
    archived: bool | None = None,
    source: str | None = None,
    status: BookStatus | None = None,
    conn: sqlite3.Connection = Depends(db_module.get_db),
):
    # Epic 15: defaults to "library" when omitted, so candidates/discarded books
    # don't clutter the main list — the one behavior change to this endpoint (see
    # docs/DECISIONS.md; every pre-Epic-15 book defaults to 'library' so nothing
    # currently visible becomes hidden).
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
    query += " ORDER BY id"
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
        "current_page": book["current_page"],
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
    # Epic 19: the manual discard path (the Queue's Discard button) is what sets
    # discard_reason='user' — the other write site, auto-expiry, sets 'expired'
    # directly in its own UPDATE (routes/feeds.py._expire_stale_candidates).
    if fields.get("status") == "discarded":
        fields["discard_reason"] = "user"
    if fields:
        set_clause = ", ".join(f"{key} = ?" for key in fields)
        conn.execute(
            f"UPDATE books SET {set_clause} WHERE id = ?",
            (*fields.values(), book_id),
        )
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


@router.get("/{book_id}/pages/{page_no}")
def get_page(
    book_id: int, page_no: int, conn: sqlite3.Connection = Depends(db_module.get_db)
):
    _get_book_or_404(conn, book_id)
    page_count = conn.execute(
        "SELECT COUNT(*) FROM pages WHERE book_id = ?", (book_id,)
    ).fetchone()[0]
    page = conn.execute(
        "SELECT content FROM pages WHERE book_id = ? AND page_no = ?",
        (book_id, page_no),
    ).fetchone()
    if page is None:
        raise HTTPException(status_code=404, detail="page not found")

    content = page["content"]
    tokens = tokenize(content)
    lemmas = {t.lemma for t in tokens}

    terms: dict = {}
    if lemmas:
        placeholders = ", ".join("?" for _ in lemmas)
        rows = conn.execute(
            f"SELECT id, lemma, translation, status, deck FROM terms "
            f"WHERE lemma IN ({placeholders})",
            tuple(lemmas),
        ).fetchall()
        for row in rows:
            terms[row["lemma"]] = {
                "id": row["id"],
                "lemma": row["lemma"],
                "translation": row["translation"],
                "status": row["status"],
                "deck": row["deck"],
                "forms": [],
            }
        # Epic 20: a term also highlights via any of its extra `forms`. Match those
        # against the page's token lemmas too, keyed by the form string (so a token
        # whose lemma is 승인서 lights up as the 승인 term). A direct lemma match wins
        # if a string is both — hence the `not in terms` guard.
        form_rows = conn.execute(
            f"SELECT tf.form, t.id, t.lemma, t.translation, t.status, t.deck "
            f"FROM term_forms tf JOIN terms t ON t.id = tf.term_id "
            f"WHERE tf.form IN ({placeholders})",
            tuple(lemmas),
        ).fetchall()
        for row in form_rows:
            if row["form"] not in terms:
                terms[row["form"]] = {
                    "id": row["id"],
                    "lemma": row["lemma"],
                    "translation": row["translation"],
                    "status": row["status"],
                    "deck": row["deck"],
                    "forms": [],
                }
        # Attach every matched term's full forms list (so the reader popover can edit
        # them when the token is tapped), in one grouped query over the matched ids.
        matched_ids = {entry["id"] for entry in terms.values()}
        if matched_ids:
            id_ph = ", ".join("?" for _ in matched_ids)
            forms_by_term: dict[int, list] = {}
            for r in conn.execute(
                f"SELECT term_id, form FROM term_forms WHERE term_id IN ({id_ph}) "
                f"ORDER BY rowid",
                tuple(matched_ids),
            ):
                forms_by_term.setdefault(r["term_id"], []).append(r["form"])
            for entry in terms.values():
                entry["forms"] = forms_by_term.get(entry["id"], [])

    return {
        "page_no": page_no,
        "page_count": page_count,
        "content": content,
        "tokens": [
            {"s": t.s, "e": t.e, "surface": t.surface, "lemma": t.lemma, "pos": t.pos}
            for t in tokens
        ],
        "terms": terms,
    }
