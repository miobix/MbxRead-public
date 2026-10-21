"""Feeds API: the roster CRUD and the fetch job that fills the Queue with candidates.

Items are deduped on source_ref before the expensive fetch, and failures are isolated
per feed and per item so one bad source never blocks the rest.
"""
import sqlite3
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import db as db_module
from ..article import ArticleError, fetch_article
from ..difficulty import frequency_grades, known_lemmas
from ..feeds import (
    FeedFetchError,
    fetch_feed_xml,
    parse_rss,
    parse_youtube_feed,
    youtube_feed_url,
)
from import_tools.yt_subs import NoSubtitlesError, fetch_subs

from . import settings as settings_route
from .books import DuplicateSourceRef, _purge_queue_text, _score_and_cache, insert_book

router = APIRouter(prefix="/api/feeds", tags=["feeds"])

FeedType = Literal["rss", "youtube"]

# Each transcript is a yt-dlp round trip; uncapped, a first run stalls the manual
# "Fetch" button for minutes. Later runs pick up the rest.
YOUTUBE_MAX_PER_FETCH = 5


# --- CRUD ---


class FeedCreate(BaseModel):
    name: str
    type: FeedType
    url_or_channel_id: str
    topic: str = ""
    enabled: bool = True


class FeedPatch(BaseModel):
    name: str | None = None
    type: FeedType | None = None
    url_or_channel_id: str | None = None
    topic: str | None = None
    enabled: bool | None = None


def _feed_dict(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "type": row["type"],
        "url_or_channel_id": row["url_or_channel_id"],
        "topic": row["topic"],
        "enabled": bool(row["enabled"]),
        "last_fetched": row["last_fetched"],
    }


def _get_feed_or_404(conn: sqlite3.Connection, feed_id: int) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM feeds WHERE id = ?", (feed_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="feed not found")
    return row


@router.get("")
def list_feeds(conn: sqlite3.Connection = Depends(db_module.get_db)):
    rows = conn.execute("SELECT * FROM feeds ORDER BY topic, name").fetchall()
    return [_feed_dict(row) for row in rows]


@router.post("", status_code=201)
def create_feed(body: FeedCreate, conn: sqlite3.Connection = Depends(db_module.get_db)):
    cur = conn.execute(
        "INSERT INTO feeds (name, type, url_or_channel_id, topic, enabled) VALUES (?, ?, ?, ?, ?)",
        (body.name, body.type, body.url_or_channel_id, body.topic, int(body.enabled)),
    )
    conn.commit()
    return _feed_dict(_get_feed_or_404(conn, cur.lastrowid))


@router.patch("/{feed_id}")
def patch_feed(
    feed_id: int, body: FeedPatch, conn: sqlite3.Connection = Depends(db_module.get_db)
):
    _get_feed_or_404(conn, feed_id)
    fields = body.model_dump(exclude_unset=True)
    if "enabled" in fields:
        fields["enabled"] = int(fields["enabled"])
    if fields:
        set_clause = ", ".join(f"{key} = ?" for key in fields)
        conn.execute(
            f"UPDATE feeds SET {set_clause} WHERE id = ?", (*fields.values(), feed_id)
        )
        conn.commit()
    return _feed_dict(_get_feed_or_404(conn, feed_id))


@router.delete("/{feed_id}", status_code=204)
def delete_feed(feed_id: int, conn: sqlite3.Connection = Depends(db_module.get_db)):
    _get_feed_or_404(conn, feed_id)
    conn.execute("DELETE FROM feeds WHERE id = ?", (feed_id,))
    conn.commit()


# --- Fetch job ---


def _already_imported(conn: sqlite3.Connection, source_ref: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM books WHERE source_ref = ?", (source_ref,)
        ).fetchone()
        is not None
    )


def _process_rss(conn, feed, known, frequency) -> dict:
    summary = {
        "id": feed["id"],
        "name": feed["name"],
        "items_seen": 0,
        "created": 0,
        "skipped_duplicate": 0,
        "failed": 0,
    }
    try:
        items = parse_rss(fetch_feed_xml(feed["url_or_channel_id"]))
    except FeedFetchError as e:
        summary["fetch_error"] = str(e)
        return summary

    summary["items_seen"] = len(items)
    for item in items:
        source_ref = f"article:{item.link}"
        if _already_imported(conn, source_ref):
            summary["skipped_duplicate"] += 1
            continue
        try:
            title, text = fetch_article(item.link)
        except ArticleError:
            summary["failed"] += 1
            continue
        _insert_and_score(
            conn, title or item.title, text, "article", item.link, source_ref,
            feed, known, frequency, summary,
        )
    return summary


def _process_youtube(conn, feed, known, frequency) -> dict:
    summary = {
        "id": feed["id"],
        "name": feed["name"],
        "items_seen": 0,
        "created": 0,
        "skipped_duplicate": 0,
        "skipped_no_subs": 0,
        "failed": 0,
    }
    try:
        items = parse_youtube_feed(fetch_feed_xml(youtube_feed_url(feed["url_or_channel_id"])))
    except FeedFetchError as e:
        summary["fetch_error"] = str(e)
        return summary

    summary["items_seen"] = len(items)
    processed = 0
    for item in items:
        source_ref = f"yt:{item.guid}"  # guid is the video id
        if _already_imported(conn, source_ref):
            summary["skipped_duplicate"] += 1
            continue
        if processed >= YOUTUBE_MAX_PER_FETCH:
            break
        processed += 1
        try:
            title, text, _vid, duration = fetch_subs(item.link)
        except NoSubtitlesError:
            summary["skipped_no_subs"] += 1
            continue
        except Exception:  # noqa: BLE001 — one bad video never blocks the feed
            summary["failed"] += 1
            continue
        _insert_and_score(
            conn, title or item.title, text, "yt", item.link, source_ref,
            feed, known, frequency, summary, duration_seconds=duration,
        )
    return summary


def _insert_and_score(
    conn, title, text, source, source_url, source_ref, feed, known, frequency, summary,
    duration_seconds=None,
) -> None:
    try:
        book = insert_book(
            conn,
            title=title,
            text=text,
            source=source,
            topic=feed["topic"],
            tags=[feed["name"]],
            source_url=source_url,
            source_ref=source_ref,
            status="candidate",
            duration_seconds=duration_seconds,
            feed_id=feed["id"],
        )
    except DuplicateSourceRef:
        summary["skipped_duplicate"] += 1
        return
    _score_and_cache(conn, book["id"], text, known=known, frequency=frequency)
    summary["created"] += 1


def _expire_stale_candidates(conn: sqlite3.Connection) -> int:
    """Discard candidates older than the retention window (a normal, permanent discard)
    and purge their text. Cheap and idempotent, so it runs on every fetch call."""
    retention_days = settings_route.get_candidate_retention_days(conn)
    stale_ids = [
        row["id"]
        for row in conn.execute(
            "SELECT id FROM books WHERE status = 'candidate' "
            "AND created <= datetime('now', ?)",
            (f"-{retention_days} days",),
        )
    ]
    _purge_queue_text(conn, stale_ids)
    cur = conn.execute(
        "UPDATE books SET status = 'discarded', discard_reason = 'expired' "
        "WHERE status = 'candidate' AND created <= datetime('now', ?)",
        (f"-{retention_days} days",),
    )
    conn.commit()
    return cur.rowcount


@router.post("/fetch")
def fetch_feeds(
    feed_id: int | None = None, conn: sqlite3.Connection = Depends(db_module.get_db)
):
    # Stamped first so a run that dies partway still records the attempt.
    settings_route.stamp_last_fetch_attempt(conn)
    expired = _expire_stale_candidates(conn)

    query = "SELECT * FROM feeds WHERE enabled = 1"
    params: list = []
    if feed_id is not None:
        query += " AND id = ?"
        params.append(feed_id)
    feeds = conn.execute(query, params).fetchall()

    known = known_lemmas(conn)
    frequency = frequency_grades(conn)

    checked_feeds = 0
    candidates_created = 0
    feed_summaries = []

    for feed in feeds:
        if feed["type"] == "rss":
            summary = _process_rss(conn, feed, known, frequency)
        else:
            summary = _process_youtube(conn, feed, known, frequency)

        checked_feeds += 1
        candidates_created += summary["created"]
        conn.execute(
            "UPDATE feeds SET last_fetched = CURRENT_TIMESTAMP WHERE id = ?",
            (feed["id"],),
        )
        conn.commit()
        feed_summaries.append(summary)

    return {
        "checked_feeds": checked_feeds,
        "candidates_created": candidates_created,
        "expired": expired,
        "feeds": feed_summaries,
    }
