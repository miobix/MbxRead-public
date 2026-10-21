"""Import routes: extract text with an import tool, then `books.insert_book`.

Tests mock the extractors at this module's boundary (`imports.fetch_subs`, etc.).
"""
import hashlib
import sqlite3
from pathlib import Path
from typing import Callable

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from import_tools.epub_text import extract as extract_epub
from import_tools.pdf_text import extract as extract_pdf
from import_tools.pdf_text import parse_page_range
from import_tools.subtitles import SubtitleError, clean_title
from import_tools.subtitles import extract as extract_subtitles
from import_tools.yt_subs import fetch_subs

from .. import db as db_module
from ..article import ArticleError, fetch_article
from .books import DuplicateSourceRef, insert_book

router = APIRouter(prefix="/api/import", tags=["import"])


class UrlImport(BaseModel):
    url: str
    topic: str = ""
    tags: list[str] = []


def _split_tags(tags: str) -> list[str]:
    return [t.strip() for t in tags.split(",") if t.strip()]


async def _import_file(
    conn: sqlite3.Connection,
    file: UploadFile,
    extract: Callable[[bytes], str],
    source: str,
    title: str,
    topic: str,
    tags: str,
):
    content = await file.read()
    try:
        text = extract(content)
    except Exception as e:
        return JSONResponse(status_code=502, content={"error": str(e)})
    if not text.strip():
        return JSONResponse(
            status_code=502, content={"error": f"No extractable text in this {source.upper()}."}
        )
    try:
        return insert_book(
            conn,
            title=title.strip() or Path(file.filename or f"untitled.{source}").stem,
            text=text,
            source=source,
            topic=topic,
            tags=_split_tags(tags),
            source_ref=f"{source}:{hashlib.sha256(content).hexdigest()}",
        )
    except DuplicateSourceRef:
        raise HTTPException(
            status_code=409, detail=f"this {source.upper()} has already been imported"
        )


@router.post("/youtube", status_code=201)
def import_youtube(body: UrlImport, conn: sqlite3.Connection = Depends(db_module.get_db)):
    try:
        title, text, video_id, duration = fetch_subs(body.url)
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
            duration_seconds=duration,
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
    page_range = parse_page_range(pages) if pages else None
    return await _import_file(
        conn, file, lambda c: extract_pdf(c, page_range), "pdf", title, topic, tags
    )


@router.post("/epub", status_code=201)
async def import_epub(
    file: UploadFile,
    title: str = Form(""),
    topic: str = Form(""),
    tags: str = Form(""),
    conn: sqlite3.Connection = Depends(db_module.get_db),
):
    return await _import_file(conn, file, extract_epub, "epub", title, topic, tags)


@router.post("/subtitles", status_code=201)
async def import_subtitles(
    files: list[UploadFile],
    title: str = Form(""),
    topic: str = Form(""),
    tags: str = Form(""),
    conn: sqlite3.Connection = Depends(db_module.get_db),
):
    """One book per subtitle file, in filename order so a season lands in episode order.
    Always 201 with a per-file summary, since partial success is normal for a batch."""
    ordered = sorted(files, key=lambda f: (f.filename or "").lower())
    tag_list = _split_tags(tags)
    imported: list[dict] = []
    skipped: list[dict] = []
    failed: list[dict] = []

    for upload in ordered:
        filename = upload.filename or "untitled.srt"
        content = await upload.read()
        try:
            text, duration = extract_subtitles(content, filename)
        except SubtitleError as e:
            failed.append({"filename": filename, "error": str(e)})
            continue
        except Exception as e:  # a malformed file must not sink the rest of the batch
            failed.append({"filename": filename, "error": str(e)})
            continue
        book_title = (
            title.strip() if (title.strip() and len(ordered) == 1) else clean_title(filename)
        )
        digest = hashlib.sha256(content).hexdigest()
        try:
            imported.append(
                insert_book(
                    conn,
                    title=book_title,
                    text=text,
                    source="subs",
                    topic=topic,
                    tags=tag_list,
                    source_ref=f"subs:{digest}",
                    duration_seconds=duration,
                )
            )
        except DuplicateSourceRef:
            skipped.append({"filename": filename, "reason": "already imported"})

    return {"imported": imported, "skipped": skipped, "failed": failed}
