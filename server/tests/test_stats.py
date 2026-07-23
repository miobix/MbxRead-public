import sqlite3
from datetime import date, timedelta

from server.db import get_connection
from server.routes.stats import _streak

STORY = "그는 옷을 입고 나갔다. 날씨가 정말 좋았다! 학교에 가야 했다."


# --- streak logic (pure, tz-independent) ---

def test_streak_empty():
    assert _streak(set(), date(2026, 7, 23)) == {"current": 0, "longest": 0}


def test_streak_single_today():
    today = date(2026, 7, 23)
    assert _streak({today}, today) == {"current": 1, "longest": 1}


def test_streak_consecutive_ending_today():
    today = date(2026, 7, 23)
    days = {today, today - timedelta(days=1), today - timedelta(days=2)}
    assert _streak(days, today) == {"current": 3, "longest": 3}


def test_streak_ending_yesterday_still_current():
    # A day that isn't over yet shouldn't break a run that includes yesterday.
    today = date(2026, 7, 23)
    days = {today - timedelta(days=1), today - timedelta(days=2)}
    assert _streak(days, today) == {"current": 2, "longest": 2}


def test_streak_broken_resets_current_keeps_longest():
    today = date(2026, 7, 23)
    # A 3-day run a while back, nothing recent.
    days = {date(2026, 7, 10), date(2026, 7, 11), date(2026, 7, 12)}
    assert _streak(days, today) == {"current": 0, "longest": 3}


# --- integration ---

def test_empty_stats_shape(client):
    body = client.get("/api/stats").json()
    assert body["totals"]["words_total"] == 0
    assert body["streak"] == {"current": 0, "longest": 0}
    assert body["activity"] == []
    assert body["new_words_per_book"] == []
    assert body["vocab_depth"]["buckets"] == {"A": 0, "B": 0, "C": 0, "unlisted": 0}


def test_totals_exclude_ignored(client):
    client.post("/api/terms", json={"lemma": "가다", "translation": "go", "status": "learning"})
    client.post("/api/terms", json={"lemma": "오다", "translation": "come", "status": "known"})
    client.post("/api/terms", json={"lemma": "그", "translation": "-", "status": "ignored"})
    totals = client.get("/api/stats").json()["totals"]
    assert totals["words_learning"] == 1
    assert totals["words_known"] == 1
    assert totals["words_total"] == 2  # ignored not counted


def test_books_finished_counts_read_library_books(client):
    b1 = client.post("/api/books", json={"title": "A", "text": STORY}).json()["id"]
    client.post("/api/books", json={"title": "B", "text": STORY})
    client.patch(f"/api/books/{b1}", json={"read": True})
    assert client.get("/api/stats").json()["totals"]["books_finished"] == 1


def test_activity_and_streak_from_today(client):
    book_id = client.post("/api/books", json={"title": "A", "text": STORY}).json()["id"]
    client.post("/api/terms", json={"lemma": "가다", "translation": "go"})
    client.post("/api/reads", json={"book_id": book_id, "page_no": 1})
    body = client.get("/api/stats").json()
    assert body["streak"]["current"] == 1
    assert len(body["activity"]) == 1
    assert body["activity"][0]["words"] == 1
    assert body["activity"][0]["pages"] == 1
    assert body["totals"]["words_week"] == 1
    assert body["totals"]["pages_week"] == 1


def test_new_words_per_book_uses_provenance(client):
    book_id = client.post("/api/books", json={"title": "Origin", "text": STORY}).json()["id"]
    client.post("/api/reads", json={"book_id": book_id, "page_no": 1})
    client.post(
        "/api/terms",
        json={"lemma": "가다", "translation": "go", "source_book_id": book_id, "source_page": 1},
    )
    client.post(
        "/api/terms",
        json={"lemma": "오다", "translation": "come", "source_book_id": book_id, "source_page": 1},
    )
    # A term without provenance shouldn't attach to any book.
    client.post("/api/terms", json={"lemma": "그", "translation": "-"})

    rows = client.get("/api/stats").json()["new_words_per_book"]
    assert len(rows) == 1
    assert rows[0]["book_id"] == book_id
    assert rows[0]["new_words"] == 2
    assert rows[0]["pages_read"] == 1


def test_vocab_depth_buckets_and_beginner_pct(client, db_path):
    conn = get_connection(db_path)
    grade_a_lemma = conn.execute(
        "SELECT lemma FROM vocab_levels WHERE grade = 'A' LIMIT 1"
    ).fetchone()["lemma"]
    total_a = conn.execute(
        "SELECT COUNT(*) c FROM vocab_levels WHERE grade = 'A'"
    ).fetchone()["c"]
    conn.close()

    client.post("/api/terms", json={"lemma": grade_a_lemma, "translation": "-"})
    client.post("/api/terms", json={"lemma": "존재하지않는단어zz", "translation": "-"})

    depth = client.get("/api/stats").json()["vocab_depth"]
    assert depth["buckets"]["A"] == 1
    assert depth["buckets"]["unlisted"] == 1
    assert depth["total_a"] == total_a
    assert depth["beginner_pct"] == round(1 / total_a, 4)


# --- curation breakdown (Epic 19) ---


def _insert_curation_book(db_path, topic, feed_id, status, discard_reason=None):
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO books (title, source, topic, feed_id, status, discard_reason) "
        "VALUES (?, 'article', ?, ?, ?, ?)",
        (f"book-{topic}-{status}-{discard_reason}", topic, feed_id, status, discard_reason),
    )
    conn.commit()
    conn.close()


def test_empty_curation_breakdown(client):
    curation = client.get("/api/stats").json()["curation"]
    assert curation == {"by_topic": [], "by_feed": []}


def test_curation_breakdown_by_topic_and_feed(client, db_path):
    feed_a = client.post(
        "/api/feeds",
        json={"name": "Feed A", "type": "rss", "url_or_channel_id": "https://a", "topic": "gaming"},
    ).json()
    feed_b = client.post(
        "/api/feeds",
        json={"name": "Feed B", "type": "rss", "url_or_channel_id": "https://b", "topic": "news"},
    ).json()

    _insert_curation_book(db_path, "gaming", feed_a["id"], "library")
    _insert_curation_book(db_path, "gaming", feed_a["id"], "discarded", "user")
    _insert_curation_book(db_path, "gaming", feed_a["id"], "discarded", "expired")
    _insert_curation_book(db_path, "gaming", feed_a["id"], "candidate")
    _insert_curation_book(db_path, "news", feed_b["id"], "library")
    # A manually-pasted book has no feed_id and must be excluded entirely.
    client.post("/api/books", json={"title": "manual", "text": STORY})

    curation = client.get("/api/stats").json()["curation"]

    by_topic = {row["topic"]: row for row in curation["by_topic"]}
    assert by_topic["gaming"] == {
        "topic": "gaming", "promoted": 1, "user_discarded": 1, "expired": 1, "pending": 1,
    }
    assert by_topic["news"] == {
        "topic": "news", "promoted": 1, "user_discarded": 0, "expired": 0, "pending": 0,
    }

    by_feed = {row["feed_id"]: row for row in curation["by_feed"]}
    assert by_feed[feed_a["id"]] == {
        "feed_id": feed_a["id"], "feed_name": "Feed A",
        "promoted": 1, "user_discarded": 1, "expired": 1, "pending": 1,
    }
    assert by_feed[feed_b["id"]] == {
        "feed_id": feed_b["id"], "feed_name": "Feed B",
        "promoted": 1, "user_discarded": 0, "expired": 0, "pending": 0,
    }


def test_curation_breakdown_handles_deleted_feed(client, db_path):
    feed = client.post(
        "/api/feeds",
        json={"name": "Gone", "type": "rss", "url_or_channel_id": "https://gone", "topic": "tech"},
    ).json()
    _insert_curation_book(db_path, "tech", feed["id"], "library")
    client.delete(f"/api/feeds/{feed['id']}")

    by_feed = client.get("/api/stats").json()["curation"]["by_feed"]
    row = next(r for r in by_feed if r["feed_id"] == feed["id"])
    assert row["feed_name"] == f"(deleted feed #{feed['id']})"
    assert row["promoted"] == 1
