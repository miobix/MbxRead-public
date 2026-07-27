"""Reading stats API (Epic 16). See docs/SPEC.md section 5.

One aggregate blob for the stats screen. All day-buckets are in LOCAL time
(`date(..., 'localtime')`) — the server runs on the user's own PC, so server-local
is user-local — which is what makes "today" and the streak line up with the wall
clock. Activity feeding the streak/heatmap is the UNION of two signals: days a word
was saved (`terms.created`) and days something was read (`read_days.day`, Epic 24 —
formerly `page_reads.read_at`, re-keyed by day when page numbers became per-device).
"""
import sqlite3
from datetime import date, timedelta

from fastapi import APIRouter, Depends

from .. import db as db_module

router = APIRouter(prefix="/api/stats", tags=["stats"])

ACTIVITY_WINDOW_DAYS = 365


CURATION_BUCKETS = ("promoted", "user_discarded", "expired", "pending")


def _curation_breakdown(conn: sqlite3.Connection) -> dict:
    """Promoted/user_discarded/expired/pending counts by topic and by feed, over
    feed-sourced books only (feed_id IS NOT NULL — manual imports never set it, so
    they're naturally excluded, per SPEC's "what gets read vs. what doesn't" framing
    being about the automated pipeline specifically). status='library' counts as
    promoted, status='candidate' as pending, and status='discarded' splits by
    discard_reason ('user' vs 'expired') — a discarded row with no reason (e.g. a
    pre-Epic-19 discard) isn't counted in any of the four buckets, since it's
    genuinely ambiguous which one it belongs to."""
    rows = conn.execute(
        "SELECT b.topic, b.feed_id, f.name feed_name, b.status, b.discard_reason, "
        "  COUNT(*) c "
        "FROM books b LEFT JOIN feeds f ON f.id = b.feed_id "
        "WHERE b.feed_id IS NOT NULL "
        "GROUP BY b.topic, b.feed_id, b.status, b.discard_reason"
    ).fetchall()

    by_topic: dict[str, dict] = {}
    by_feed: dict[int, dict] = {}

    for row in rows:
        if row["status"] == "library":
            bucket = "promoted"
        elif row["status"] == "candidate":
            bucket = "pending"
        elif row["discard_reason"] == "user":
            bucket = "user_discarded"
        elif row["discard_reason"] == "expired":
            bucket = "expired"
        else:
            continue

        topic_counts = by_topic.setdefault(
            row["topic"], {b: 0 for b in CURATION_BUCKETS}
        )
        topic_counts[bucket] += row["c"]

        feed_counts = by_feed.setdefault(
            row["feed_id"],
            {"feed_name": row["feed_name"] or f"(deleted feed #{row['feed_id']})",
             **{b: 0 for b in CURATION_BUCKETS}},
        )
        feed_counts[bucket] += row["c"]

    return {
        "by_topic": [
            {"topic": topic, **counts} for topic, counts in sorted(by_topic.items())
        ],
        "by_feed": [
            {"feed_id": feed_id, **counts}
            for feed_id, counts in sorted(by_feed.items())
        ],
    }


def _streak(active_days: set[date], today: date) -> dict:
    """current: consecutive active days ending today (or yesterday, so a day that
    isn't over yet doesn't prematurely break the streak). longest: the longest run
    anywhere in the history."""
    if not active_days:
        return {"current": 0, "longest": 0}

    ordered = sorted(active_days)
    longest = run = 1
    for prev, cur in zip(ordered, ordered[1:]):
        run = run + 1 if cur - prev == timedelta(days=1) else 1
        longest = max(longest, run)

    if today in active_days:
        anchor = today
    elif (today - timedelta(days=1)) in active_days:
        anchor = today - timedelta(days=1)
    else:
        return {"current": 0, "longest": longest}

    current = 0
    day = anchor
    while day in active_days:
        current += 1
        day -= timedelta(days=1)
    return {"current": current, "longest": longest}


@router.get("")
def get_stats(conn: sqlite3.Connection = Depends(db_module.get_db)):
    # --- totals ---
    status_counts = {
        row["status"]: row["c"]
        for row in conn.execute("SELECT status, COUNT(*) c FROM terms GROUP BY status")
    }
    words_learning = status_counts.get("learning", 0)
    words_known = status_counts.get("known", 0)
    books_finished = conn.execute(
        "SELECT COUNT(*) c FROM books WHERE read = 1 AND status = 'library'"
    ).fetchone()["c"]

    # --- daily activity (word-saves + first-page-reads), local-time buckets ---
    words_by_day: dict[str, int] = {
        row["d"]: row["c"]
        for row in conn.execute(
            "SELECT date(created, 'localtime') d, COUNT(*) c FROM terms GROUP BY d"
        )
    }
    # Epic 24: one row per book per day read, replacing the per-page log. The count
    # is therefore "books read that day", not "pages" — page counts stopped being
    # comparable once each device paginates for its own screen.
    read_by_day: dict[str, int] = {
        row["d"]: row["c"]
        for row in conn.execute("SELECT day d, COUNT(*) c FROM read_days GROUP BY d")
    }

    today = date.today()
    cutoff = today - timedelta(days=ACTIVITY_WINDOW_DAYS)
    all_day_keys = set(words_by_day) | set(read_by_day)
    activity = [
        {"date": d, "words": words_by_day.get(d, 0), "read": read_by_day.get(d, 0)}
        for d in sorted(all_day_keys)
        if d and date.fromisoformat(d) >= cutoff
    ]

    # The streak counts a day active if a word was saved *or* something was read.
    active_days = {date.fromisoformat(d) for d in all_day_keys if d}
    streak = _streak(active_days, today)

    week_start = (today - timedelta(days=6)).isoformat()
    words_week = sum(a["words"] for a in activity if a["date"] >= week_start)
    days_read_week = sum(1 for a in activity if a["date"] >= week_start and a["read"])

    # --- new words per book (needs term provenance), in reading order ---
    new_words_per_book = [
        {
            "book_id": row["id"],
            "title": row["title"],
            "new_words": row["new_words"],
            "days_read": row["days_read"],
        }
        for row in conn.execute(
            "SELECT b.id, b.title, COUNT(t.id) new_words, "
            "  (SELECT COUNT(*) FROM read_days rd WHERE rd.book_id = b.id) days_read "
            "FROM books b JOIN terms t ON t.source_book_id = b.id "
            "GROUP BY b.id ORDER BY b.created, b.id"
        )
    ]

    # --- vocabulary depth: known lemmas (learning+known) by NIKL grade ---
    buckets = {"A": 0, "B": 0, "C": 0, "unlisted": 0}
    for row in conn.execute(
        "SELECT COALESCE(v.grade, 'unlisted') g, COUNT(*) c "
        "FROM terms t LEFT JOIN vocab_levels v ON v.lemma = t.lemma "
        "WHERE t.status IN ('learning', 'known') GROUP BY g"
    ):
        buckets[row["g"]] = row["c"]
    total_a = conn.execute(
        "SELECT COUNT(*) c FROM vocab_levels WHERE grade = 'A'"
    ).fetchone()["c"]
    beginner_pct = round(buckets["A"] / total_a, 4) if total_a else None

    return {
        "totals": {
            "words_learning": words_learning,
            "words_known": words_known,
            "words_total": words_learning + words_known,
            "books_finished": books_finished,
            "words_week": words_week,
            "days_read_week": days_read_week,
        },
        "streak": streak,
        "activity": activity,
        "new_words_per_book": new_words_per_book,
        "vocab_depth": {
            "buckets": buckets,
            "beginner_pct": beginner_pct,
            "total_a": total_a,
        },
        "curation": _curation_breakdown(conn),
    }
