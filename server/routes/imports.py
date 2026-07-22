"""Import wiring — YouTube subs / PDF / article URL -> a scored-ready book.

Epic 12. Thin routes: each fetches/extracts text via an existing tool
(`import_tools.yt_subs`, `import_tools.pdf_text`, `server.article`), then
delegates to `books.insert_book` for the shared page-split + source_ref-dedup
insert. Tests mock at this module's boundary (`imports.fetch_subs`, etc.),
same convention as `routes/translate.py`.
"""
import hashlib
import sqlite3
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from import_tools.pdf_text import extract as extract_pdf
from import_tools.pdf_text import parse_page_range
from import_tools.yt_subs import fetch_subs

from .. import db as db_module
from ..article import ArticleError, fetch_article
from .books import DuplicateSourceRef, insert_book

router = APIRouter(prefix="/api/import", tags=["import"])


class UrlImport(BaseModel):
    url: str
    topic: str = ""
    tags: list[str] = []


@router.post("/youtube", status_code=201)
def import_youtube(body: UrlImport, conn: sqlite3.Connection = Depends(db_module.get_db)):
    try:
        title, text, video_id = fetch_subs(body.url)
    except Exception as e:
        return JSONResponse(status_code=502, content={"error": str(e)})
    try:
        return insert_book(
            conn,
            title=title,
            text=text,
            source="yt",
            topic=body.topic,
            tags=body.tags,
            source_url=body.url,
            source_ref=f"yt:{video_id}",
        )
    except DuplicateSourceRef:
        raise HTTPException(status_code=409, detail="this video has already been imported")


@router.post("/article", status_code=201)
def import_article(body: UrlImport, conn: sqlite3.Connection = Depends(db_module.get_db)):
    try:
        title, text = fetch_article(body.url)
    except ArticleError as e:
        return JSONResponse(status_code=502, content={"error": str(e)})
    try:
        return insert_book(
            conn,
            title=title,
            text=text,
            source="article",
            topic=body.topic,
            tags=body.tags,
            source_url=body.url,
            source_ref=f"article:{body.url}",
        )
    except DuplicateSourceRef:
        raise HTTPException(status_code=409, detail="this article has already been imported")


@router.post("/pdf", status_code=201)
async def import_pdf(
    file: UploadFile,
    title: str = Form(""),
    topic: str = Form(""),
    tags: str = Form(""),
    pages: str = Form(""),
    conn: sqlite3.Connection = Depends(db_module.get_db),
):
    content = await file.read()
    page_range = parse_page_range(pages) if pages else None
    try:
        text = extract_pdf(content, page_range)
    except Exception as e:
        return JSONResponse(status_code=502, content={"error": str(e)})
    book_title = title.strip() or Path(file.filename or "untitled.pdf").stem
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    digest = hashlib.sha256(content).hexdigest()
    try:
        return insert_book(
            conn,
            title=book_title,
            text=text,
            source="pdf",
            topic=topic,
            tags=tag_list,
            source_ref=f"pdf:{digest}",
        )
    except DuplicateSourceRef:
        raise HTTPException(status_code=409, detail="this PDF has already been imported")
