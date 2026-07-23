"""POST /api/feeds/fetch — Epic 15 curation queue. Iterates enabled feeds, parses
each via server.feeds, fetches+cleans new items via server.article, scores them
(personal + general difficulty), and inserts them as status='candidate' books for
the user to browse and promote/discard on the Queue page.
"""
import sqlite3

from fastapi import APIRouter, Depends

from .. import db as db_module
from ..article import ArticleError, fetch_article
from ..difficulty import frequency_grades, known_lemmas
from ..feeds import FeedFetchError, fetch_feed_xml, parse_rss
from .books import DuplicateSourceRef, _score_and_cache, insert_book

router = APIRouter(prefix="/api/feeds", tags=["feeds"])


@router.post("/fetch")
def fetch_feeds(
    feed_id: int | None = None, conn: sqlite3.Connection = Depends(db_module.get_db)
):
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
        if feed["type"] != "rss":
            skipped_feed_types += 1
            feed_summaries.append(
                {"id": feed["id"], "name": feed["name"], "skipped_type": feed["type"]}
            )
            continue

        checked_feeds += 1
        summary = {
            "id": feed["id"],
            "name": feed["name"],
            "items_seen": 0,
            "created": 0,
            "skipped_duplicate": 0,
            "failed": 0,
        }

        try:
            xml_bytes = fetch_feed_xml(feed["url_or_channel_id"])
            items = parse_rss(xml_bytes)
        except FeedFetchError as e:
            summary["fetch_error"] = str(e)
            feed_summaries.append(summary)
            continue

        summary["items_seen"] = len(items)
        for item in items:
            source_ref = f"article:{item.link}"
            exists = conn.execute(
                "SELECT 1 FROM books WHERE source_ref = ?", (source_ref,)
            ).fetchone()
            if exists:
                summary["skipped_duplicate"] += 1
                continue

            try:
                title, text = fetch_article(item.link)
            except ArticleError:
                summary["failed"] += 1
                continue

            try:
                book = insert_book(
                    conn,
                    title=title or item.title,
                    text=text,
                    source="article",
                    topic=feed["topic"],
                    tags=[feed["name"]],
                    source_url=item.link,
                    source_ref=source_ref,
                    status="candidate",
                )
            except DuplicateSourceRef:
                summary["skipped_duplicate"] += 1
                continue

            _score_and_cache(conn, book["id"], text, known=known, frequency=frequency)
            summary["created"] += 1
            candidates_created += 1

        conn.execute(
            "UPDATE feeds SET last_fetched = CURRENT_TIMESTAMP WHERE id = ?", (feed["id"],)
        )
        conn.commit()
        feed_summaries.append(summary)

    return {
        "checked_feeds": checked_feeds,
        "skipped_feed_types": skipped_feed_types,
        "candidates_created": candidates_created,
        "feeds": feed_summaries,
    }
