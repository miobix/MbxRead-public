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
from ..paging import snap_back, snap_forward, split_pages_by_rows
from ..tokenizer import tokenize
from .settings import get_chars_per_row, get_page_rows
from .terms import _back_items_for, _forms_for

router = APIRouter(prefix="/api/books", tags=["books"])

BookStatus = Literal["library", "candidate", "discarded"]

# Epic 24: how much text one /text request serves. 20k chars covers a median book
# (1.8k) whole and takes ~3 fetches for 어린 왕자 (45k), while keeping the token JSON
# for one response small enough to send to a phone over Tailscale. MAX caps what a
# caller can ask for so a hand-crafted `?window=` can't force a 100k-char tokenize.
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
    current_page: int | None = None
    # Epic 24: the reader's real position. ge=0 only — the upper bound is the book's
    # length, which the client already respects and which a stale write can't usefully
    # exceed (the text endpoint clamps anything past the end).
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
    # Epic 24: the denominator for reading progress. current_page stopped moving when
    # the reader switched to character offsets, so the Library reports
    # current_offset/total_chars as a percentage instead of a page number.
    total_chars = conn.execute(
        "SELECT COALESCE(SUM(LENGTH(content)), 0) FROM pages WHERE book_id = ?",
        (book_id,),
    ).fetchone()[0]
    return {
        "id": row["id"],
        "title": row["title"],
        "source": row["source"],
        "current_page": row["current_page"],
        "current_offset": row["current_offset"],
        "page_count": page_count,
        "total_chars": total_chars,
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
        "last_opened": row["last_opened"],
    }


def _get_book_or_404(conn: sqlite3.Connection, book_id: int) -> dict:
    book = _book_dict(conn, book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="book not found")
    return book


class DuplicateSourceRef(Exception):
    """Raised when source_ref collides with an already-imported book."""


def _purge_queue_text(conn: sqlite3.Connection, book_ids: list[int]) -> None:
    """Deletes `pages` rows for the given books, restricted to source in
    ('article', 'yt') — the only two sources the Queue ever holds (the feed
    fetcher's candidates). paste/pdf/epub/txt content is kept indefinitely even
    if such a book is ever discarded — the user's explicit call (2026-07-24) was
    to reclaim storage from unpromoted feed content, never from anything
    manually imported. Called from both discard sites: routes/feeds.py's
    auto-expiry and patch_book's manual discard below. The `books` row itself is
    never touched here — title/source_ref/topic/stats stay put so dedup and the
    Epic 19 curation stats breakdown are unaffected."""
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
    pages = split_pages_by_rows(text, get_page_rows(conn), get_chars_per_row(conn))
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


# 2026-07-24: server-side sort, so pagination (LIMIT/OFFSET) is actually correct —
# sorting only the current page client-side would silently reorder rows as you
# page through. "recent" (id ascending) is the pre-existing default, unchanged, so
# omitting `sort` entirely (every caller before this change) shifts nothing.
_SORT_CLAUSES = {
    "recent": "id DESC",
    # never-opened books (NULL) sort after anything with a real timestamp, falling
    # back to most-recently-added within that group.
    "opened": "(last_opened IS NULL) ASC, last_opened DESC, id DESC",
    "easiest": "(new_per_page IS NULL) ASC, new_per_page ASC",
    # mirrors web/lib/length.ts's estimatedMinutes heuristic (250 wpm for text,
    # real yt-dlp duration for video) so "Shortest first" stays correct across
    # pages instead of only within whatever page happened to be fetched.
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
        "current_page": book["current_page"],
        "current_offset": book["current_offset"],
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


@router.get("/{book_id}/pages/{page_no}")
def get_page(
    book_id: int, page_no: int, conn: sqlite3.Connection = Depends(db_module.get_db)
):
    _get_book_or_404(conn, book_id)
    # 2026-07-24: stamps every time a page is actually viewed — drives the
    # Library's "most recently opened" default sort. Deliberately on the
    # page-content fetch (the one call the reader makes to actually display a
    # page), not on create/patch, so it reflects real reading activity.
    conn.execute("UPDATE books SET last_opened = CURRENT_TIMESTAMP WHERE id = ?", (book_id,))
    conn.commit()
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
    terms = _terms_for_lemmas(conn, {t.lemma for t in tokens})

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


def _terms_for_lemmas(conn: sqlite3.Connection, lemmas: set[str]) -> dict:
    """Every saved term a set of page/window token lemmas should light up, keyed by the
    string that matched (the term's own lemma, or one of its extra `forms`). Extracted
    from get_page in Epic 24 so the new text-window endpoint highlights identically —
    behaviour unchanged, this is a straight lift."""
    terms: dict = {}
    if lemmas:
        placeholders = ", ".join("?" for _ in lemmas)
        rows = conn.execute(
            f"SELECT id, lemma, translation, notes, status, deck, examples FROM terms "
            f"WHERE lemma IN ({placeholders})",
            tuple(lemmas),
        ).fetchall()
        for row in rows:
            terms[row["lemma"]] = {
                "id": row["id"],
                "lemma": row["lemma"],
                "translation": row["translation"],
                "notes": row["notes"],
                "status": row["status"],
                "deck": row["deck"],
                "forms": [],
                "examples": json.loads(row["examples"]),
                "back_items": [],
            }
        # Epic 20: a term also highlights via any of its extra `forms`. Match those
        # against the page's token lemmas too, keyed by the form string (so a token
        # whose lemma is 승인서 lights up as the 승인 term). A direct lemma match wins
        # if a string is both — hence the `not in terms` guard.
        form_rows = conn.execute(
            f"SELECT tf.form, t.id, t.lemma, t.translation, t.notes, t.status, t.deck, "
            f"t.examples FROM term_forms tf JOIN terms t ON t.id = tf.term_id "
            f"WHERE tf.form IN ({placeholders})",
            tuple(lemmas),
        ).fetchall()
        for row in form_rows:
            if row["form"] not in terms:
                terms[row["form"]] = {
                    "id": row["id"],
                    "lemma": row["lemma"],
                    "translation": row["translation"],
                    "notes": row["notes"],
                    "status": row["status"],
                    "deck": row["deck"],
                    "forms": [],
                    "examples": json.loads(row["examples"]),
                    "back_items": [],
                }
        # Attach every matched term's full forms + back_items (so the reader popover
        # can rebuild the exact same Front/Back/Examples chip state when the token is
        # tapped) — reuses terms.py's own read helpers rather than a third copy of the
        # same query (Epic 22).
        matched_ids = {entry["id"] for entry in terms.values()}
        if matched_ids:
            forms_by_term = {tid: _forms_for(conn, tid) for tid in matched_ids}
            back_items_by_term = {tid: _back_items_for(conn, tid) for tid in matched_ids}
            for entry in terms.values():
                entry["forms"] = forms_by_term.get(entry["id"], [])
                entry["back_items"] = back_items_by_term.get(entry["id"], [])

    return terms


def _book_text(conn: sqlite3.Connection, book_id: int) -> str:
    """The book's full text, reassembled from its stored page slices. `pages` is now
    purely a storage substrate (Epic 24) — the slices are contiguous and lossless, so
    joining them with no separator round-trips the original import exactly."""
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
    """Epic 24: a character-addressed slice of the book, for the client-side paginator.

    The reader lays this out itself with CSS columns, so the server no longer decides
    where pages break — it just serves enough text to fill a screenful many times over
    and lets the browser wrap it. Windowed rather than whole-book because the long YT
    transcripts run past 100k chars (~MBs of token JSON), which is not something to
    push to a phone in one response.

    Both ends snap **outward** to a sentence/newline boundary, so a window never opens
    or closes mid-sentence; `offset` in the response is the snapped start, which may
    precede the requested one. Token offsets are relative to the returned `content`
    (exactly like the page endpoint), so the client's existing rendering and
    sentence-extraction work unchanged — absolute positions are `offset + token.s`.
    """
    _get_book_or_404(conn, book_id)
    # Moved here from get_page: this is now the call the reader makes to display text,
    # so it's what "most recently opened" should reflect.
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
