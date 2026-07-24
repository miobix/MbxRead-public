"""Feeds API — the curation subscription roster + the fetch job that fills the queue.

- CRUD (`GET/POST/PATCH/DELETE /api/feeds`, Epic 14) is what the `/feeds` management
  page edits, so the user can swap/enable/disable sources without touching code.
- `POST /api/feeds/fetch` (Epic 15 + Epic 14) iterates enabled feeds and lands new
  items as `status='candidate'` books for the Queue page:
    * rss   — parse items, fetch+clean each article via server.article (trafilatura).
    * youtube (Epic 14) — parse the channel's Atom feed, pull each new video's Korean
      transcript via import_tools.yt_subs (yt-dlp). Videos with no Korean subs are
      skipped, not failed.
    * scraper — no fetch logic yet, skipped gracefully.
  Every item is scored (personal + general difficulty) and deduped on source_ref
  BEFORE the expensive fetch. Per-feed/per-item failures are isolated so one bad feed
  or article never blocks the rest (same pattern as anki_sync's per-note failures).
  Epic 17: every call (scheduled via Task Scheduler + scripts/fetch_feeds.ps1, or the
  Queue's manual button) first stamps settings.last_fetch_attempt, then auto-discards
  any candidate older than settings.candidate_retention_days (see
  _expire_stale_candidates) before touching any feed.
  Epic 19: every feed-sourced book gets a `feed_id` (see _insert_and_score) and, if
  it's ever discarded, a `discard_reason` — 'expired' from _expire_stale_candidates
  above, 'user' from a manual PATCH in routes/books.py — so GET /api/stats can break
  down promoted/user_discarded/expired/pending by topic and by feed.
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

FeedType = Literal["rss", "youtube", "scraper"]

# Cap new videos processed per YouTube feed per run: the Atom feed only carries the
# ~15 latest anyway, and each transcript is a yt-dlp network round-trip, so an
# uncapped first run over 9 channels could take minutes and stall the interactive
# "Fetch new candidates" button. Newer runs pick up the rest; tunable.
YOUTUBE_MAX_PER_FETCH = 5


# --- CRUD (Epic 14) ---


class FeedCreate(BaseModel):
    name: str
    type: FeedType
    url_or_channel_id: str
    topic: str = ""
    enabled: bool = True
    difficulty_min: float | None = None
    difficulty_max: float | None = None


class FeedPatch(BaseModel):
    name: str | None = None
    type: FeedType | None = None
    url_or_channel_id: str | None = None
    topic: str | None = None
    enabled: bool | None = None
    difficulty_min: float | None = None
    difficulty_max: float | None = None


def _feed_dict(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "type": row["type"],
        "url_or_channel_id": row["url_or_channel_id"],
        "topic": row["topic"],
        "enabled": bool(row["enabled"]),
        "difficulty_min": row["difficulty_min"],
        "difficulty_max": row["difficulty_max"],
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
        "INSERT INTO feeds (name, type, url_or_channel_id, topic, enabled, "
        "difficulty_min, difficulty_max) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            body.name,
            body.type,
            body.url_or_channel_id,
            body.topic,
            int(body.enabled),
            body.difficulty_min,
            body.difficulty_max,
        ),
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


# --- Fetch job (Epic 15 + Epic 14) ---


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
    """Auto-discards candidates older than the configured retention window (Epic
    17). Reuses the existing status='discarded' value exactly — permanent, same as
    a manual discard — rather than a new status, per the user's confirmed choice.
    Runs on every call (scheduled, manual whole-roster, or a single-feed retry):
    it's a single indexed UPDATE, cheap and idempotent, so there's no reason to
    special-case any trigger path.

    Also purges the expired candidates' `pages` text (article/yt are the only two
    sources the feed fetcher ever creates as 'candidate' — see
    books._purge_queue_text) so an unpromoted queue item stops costing storage
    once it ages out; the `books` row itself is kept (title/source_ref/topic/
    stats) so dedup and the curation stats breakdown are unaffected."""
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
    # Stamped first, before touching any feed, so a run that errors out partway
    # still records that an attempt happened (Epic 17).
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
    skipped_feed_types = 0
    candidates_created = 0
    feed_summaries = []

    for feed in feeds:
        if feed["type"] == "rss":
            summary = _process_rss(conn, feed, known, frequency)
        elif feed["type"] == "youtube":
            summary = _process_youtube(conn, feed, known, frequency)
        else:  # scraper — no fetch logic yet
            skipped_feed_types += 1
            feed_summaries.append(
                {"id": feed["id"], "name": feed["name"], "skipped_type": feed["type"]}
            )
            continue

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
        "skipped_feed_types": skipped_feed_types,
        "candidates_created": candidates_created,
        "expired": expired,
        "feeds": feed_summaries,
    }
