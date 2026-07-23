"""Epic 15 — curation queue: server/feeds.py (RSS parsing) + POST /api/feeds/fetch.
Tests mock at the route-module boundary (feeds_route.fetch_feed_xml/fetch_article),
same convention as test_imports.py/test_translate.py.
"""
import sqlite3

from server.article import ArticleError
from server.feeds import FeedFetchError, FeedItem, parse_rss
from server.routes import feeds as feeds_route

# Real shape of Inven's / Ruliweb's live RSS 2.0 feeds: no namespaces, no <guid>
# on every item (falls back to <link>), CDATA-wrapped title.
SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
<title>Inven</title>
<item>
<title><![CDATA[게임 뉴스 1]]></title>
<link>https://webzine.inven.co.kr/news/1</link>
<description><![CDATA[내용 1]]></description>
</item>
<item>
<title><![CDATA[게임 뉴스 2]]></title>
<link>https://webzine.inven.co.kr/news/2</link>
<guid>inven-2</guid>
</item>
</channel>
</rss>
""".encode("utf-8")


# --- server/feeds.py unit tests ---


def test_parse_rss_extracts_title_and_link():
    items = parse_rss(SAMPLE_RSS)
    assert len(items) == 2
    assert items[0].link == "https://webzine.inven.co.kr/news/1"
    assert items[0].title == "게임 뉴스 1"


def test_parse_rss_falls_back_to_link_when_guid_missing():
    items = parse_rss(SAMPLE_RSS)
    assert items[0].guid == items[0].link  # no <guid> in item 1
    assert items[1].guid == "inven-2"  # item 2 has an explicit <guid>


def test_parse_rss_malformed_xml_raises():
    try:
        parse_rss(b"<rss><channel><item><title>broken")
        assert False, "expected FeedFetchError"
    except FeedFetchError:
        pass


def test_fetch_feed_xml_http_failure_raises(monkeypatch):
    import httpx

    def raise_error(*args, **kwargs):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx, "get", raise_error)
    try:
        feeds_route.fetch_feed_xml("https://example.com/rss")
        assert False, "expected FeedFetchError"
    except FeedFetchError:
        pass


# --- POST /api/feeds/fetch ---


def _seeded_feed_id(db_path) -> int:
    # feeds are seeded by init_db (Epic 15) — no CRUD route, read directly.
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT id FROM feeds WHERE url_or_channel_id = ?",
        ("https://webzine.inven.co.kr/news/rss.php",),
    ).fetchone()
    conn.close()
    return row["id"]


def test_fetch_feeds_creates_candidate_from_new_item(client, db_path, monkeypatch):
    feed_id = _seeded_feed_id(db_path)
    monkeypatch.setattr(feeds_route, "fetch_feed_xml", lambda url: b"")
    monkeypatch.setattr(
        feeds_route,
        "parse_rss",
        lambda xml: [FeedItem(title="기사", link="https://webzine.inven.co.kr/a", guid="a")],
    )
    monkeypatch.setattr(
        feeds_route, "fetch_article", lambda url: ("기사 제목", "기사 본문 내용입니다.")
    )

    resp = client.post("/api/feeds/fetch", params={"feed_id": feed_id})
    assert resp.status_code == 200
    body = resp.json()
    assert body["candidates_created"] == 1
    assert body["checked_feeds"] == 1

    candidates = client.get("/api/books?status=candidate").json()
    assert len(candidates) == 1
    assert candidates[0]["title"] == "기사 제목"
    assert candidates[0]["source"] == "article"
    assert candidates[0]["source_ref"] == "article:https://webzine.inven.co.kr/a"
    assert candidates[0]["scored_at"] is not None


def test_fetch_feeds_dedupes_on_second_run(client, db_path, monkeypatch):
    feed_id = _seeded_feed_id(db_path)
    monkeypatch.setattr(feeds_route, "fetch_feed_xml", lambda url: b"")
    monkeypatch.setattr(
        feeds_route,
        "parse_rss",
        lambda xml: [FeedItem(title="기사", link="https://webzine.inven.co.kr/dupe", guid="d")],
    )
    monkeypatch.setattr(feeds_route, "fetch_article", lambda url: ("제목", "본문 내용입니다."))

    first = client.post("/api/feeds/fetch", params={"feed_id": feed_id}).json()
    assert first["candidates_created"] == 1

    second = client.post("/api/feeds/fetch", params={"feed_id": feed_id}).json()
    assert second["candidates_created"] == 0
    assert second["feeds"][0]["skipped_duplicate"] == 1
    assert len(client.get("/api/books?status=candidate").json()) == 1


def test_fetch_feeds_skips_non_rss_feed_types(client, db_path):
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO feeds (name, type, url_or_channel_id, topic) VALUES (?, ?, ?, ?)",
        ("Some channel", "youtube", "UCabc", "gaming"),
    )
    conn.commit()
    feed_id = conn.execute("SELECT id FROM feeds WHERE url_or_channel_id = 'UCabc'").fetchone()[0]
    conn.close()

    resp = client.post("/api/feeds/fetch", params={"feed_id": feed_id})
    body = resp.json()
    assert body["checked_feeds"] == 0
    assert body["skipped_feed_types"] == 1
    assert body["feeds"][0]["skipped_type"] == "youtube"


def test_fetch_feeds_isolates_per_feed_failure(client, monkeypatch):
    def raise_error(url):
        raise FeedFetchError("boom")

    monkeypatch.setattr(feeds_route, "fetch_feed_xml", raise_error)

    resp = client.post("/api/feeds/fetch")
    assert resp.status_code == 200
    body = resp.json()
    assert body["checked_feeds"] == 2  # both seeded feeds attempted
    assert all(f.get("fetch_error") == "boom" for f in body["feeds"])
    assert body["candidates_created"] == 0


def test_fetch_feeds_isolates_per_item_extraction_failure(client, db_path, monkeypatch):
    feed_id = _seeded_feed_id(db_path)
    monkeypatch.setattr(feeds_route, "fetch_feed_xml", lambda url: b"")
    monkeypatch.setattr(
        feeds_route,
        "parse_rss",
        lambda xml: [
            FeedItem(title="ok", link="https://webzine.inven.co.kr/ok", guid="ok"),
            FeedItem(title="bad", link="https://webzine.inven.co.kr/bad", guid="bad"),
        ],
    )

    def fetch_article(url):
        if "bad" in url:
            raise ArticleError("could not extract")
        return "제목", "본문 내용입니다."

    monkeypatch.setattr(feeds_route, "fetch_article", fetch_article)

    resp = client.post("/api/feeds/fetch", params={"feed_id": feed_id})
    body = resp.json()
    assert body["candidates_created"] == 1
    assert body["feeds"][0]["failed"] == 1
    assert len(client.get("/api/books?status=candidate").json()) == 1
