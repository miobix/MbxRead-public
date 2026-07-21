"""Books & pages API. See docs/SPEC.md section 5."""
import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import db as db_module
from ..difficulty import known_lemmas, score_text
from ..paging import split_pages
from ..tokenizer import tokenize

router = APIRouter(prefix="/api/books", tags=["books"])


class BookCreate(BaseModel):
    title: str
    text: str
    source: str = "paste"


class BookPatch(BaseModel):
    current_page: int | None = None
    title: str | None = None


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
    }


def _get_book_or_404(conn: sqlite3.Connection, book_id: int) -> dict:
    book = _book_dict(conn, book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="book not found")
    return book


@router.get("")
def list_books(conn: sqlite3.Connection = Depends(db_module.get_db)):
    rows = conn.execute("SELECT id FROM books ORDER BY id").fetchall()
    return [_book_dict(conn, row["id"]) for row in rows]


@router.post("", status_code=201)
def create_book(body: BookCreate, conn: sqlite3.Connection = Depends(db_module.get_db)):
    cur = conn.execute(
        "INSERT INTO books (title, source) VALUES (?, ?)", (body.title, body.source)
    )
    book_id = cur.lastrowid
    pages = split_pages(body.text)
    conn.executemany(
        "INSERT INTO pages (book_id, page_no, content) VALUES (?, ?, ?)",
        [(book_id, i + 1, page) for i, page in enumerate(pages)],
    )
    conn.commit()
    return _book_dict(conn, book_id)


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
    if fields:
        set_clause = ", ".join(f"{key} = ?" for key in fields)
        conn.execute(
            f"UPDATE books SET {set_clause} WHERE id = ?",
            (*fields.values(), book_id),
        )
        conn.commit()
    return get_book(book_id, conn)


@router.delete("/{book_id}", status_code=204)
def delete_book(book_id: int, conn: sqlite3.Connection = Depends(db_module.get_db)):
    _get_book_or_404(conn, book_id)
    conn.execute("DELETE FROM books WHERE id = ?", (book_id,))
    conn.commit()


@router.post("/{book_id}/score")
def score_book(book_id: int, conn: sqlite3.Connection = Depends(db_module.get_db)):
    """Compute the book's difficulty against the user's vocab and cache it on the row."""
    _get_book_or_404(conn, book_id)
    rows = conn.execute(
        "SELECT content FROM pages WHERE book_id = ? ORDER BY page_no", (book_id,)
    ).fetchall()
    text = "\n".join(row["content"] for row in rows)
    result = score_text(text, known_lemmas(conn))
    conn.execute(
        "UPDATE books SET coverage = ?, new_per_page = ?, scored_at = CURRENT_TIMESTAMP "
        "WHERE id = ?",
        (result["coverage"], result["new_per_page"], book_id),
    )
    conn.commit()
    return _book_dict(conn, book_id)


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
                "translation": row["translation"],
                "status": row["status"],
                "deck": row["deck"],
            }

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
