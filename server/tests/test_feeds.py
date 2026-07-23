"""Epic 15 — curation queue: server/feeds.py (RSS parsing) + POST /api/feeds/fetch.
Tests mock at the route-module boundary (feeds_route.fetch_feed_xml/fetch_article),
same convention as test_imports.py/test_translate.py.
"""
import sqlite3

from server import db as db_module
from server.article import ArticleError
from server.feeds import FeedFetchError, FeedItem, parse_rss, parse_youtube_feed
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


def test_fetch_feeds_skips_scraper_feed_type(client, db_path):
    # Epic 14: youtube is now processed; only 'scraper' still has no fetch logic.
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO feeds (name, type, url_or_channel_id, topic) VALUES (?, ?, ?, ?)",
        ("Some site", "scraper", "https://example.com", "gaming"),
    )
    conn.commit()
    feed_id = conn.execute(
        "SELECT id FROM feeds WHERE url_or_channel_id = 'https://example.com'"
    ).fetchone()[0]
    conn.close()

    resp = client.post("/api/feeds/fetch", params={"feed_id": feed_id})
    body = resp.json()
    assert body["checked_feeds"] == 0
    assert body["skipped_feed_types"] == 1
    assert body["feeds"][0]["skipped_type"] == "scraper"


def test_fetch_feeds_isolates_per_feed_failure(client, monkeypatch):
    def raise_error(url):
        raise FeedFetchError("boom")

    monkeypatch.setattr(feeds_route, "fetch_feed_xml", raise_error)

    resp = client.post("/api/feeds/fetch")
    assert resp.status_code == 200
    body = resp.json()
    # Every enabled non-scraper seeded feed is attempted; a bad fetch on each is
    # isolated (200, recorded as fetch_error) rather than crashing the request.
    expected = sum(1 for _n, t, _u, _tp in db_module._SEED_FEEDS if t in ("rss", "youtube"))
    assert body["checked_feeds"] == expected
    assert all(f.get("fetch_error") == "boom" for f in body["feeds"])
    assert body["candidates_created"] == 0


# --- YouTube feed processing (Epic 14) ---


def _seeded_youtube_feed_id(db_path) -> int:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT id FROM feeds WHERE url_or_channel_id = ?",
        ("UCZ0bi2aVJngKLwFTU5g_fLQ",),  # 김성회의 G식백과, a seeded youtube feed
    ).fetchone()
    conn.close()
    return row["id"]


def test_parse_youtube_feed_extracts_video_id_and_link():
    atom = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015"
      xmlns="http://www.w3.org/2005/Atom">
  <title>어느 채널</title>
  <entry>
    <yt:videoId>abc123</yt:videoId>
    <title>영상 제목</title>
    <link rel="alternate" href="https://www.youtube.com/watch?v=abc123"/>
  </entry>
</feed>""".encode("utf-8")
    items = parse_youtube_feed(atom)
    assert len(items) == 1
    assert items[0].guid == "abc123"
    assert items[0].link == "https://www.youtube.com/watch?v=abc123"
    assert items[0].title == "영상 제목"


def test_fetch_feeds_youtube_creates_candidate(client, db_path, monkeypatch):
    feed_id = _seeded_youtube_feed_id(db_path)
    monkeypatch.setattr(feeds_route, "fetch_feed_xml", lambda url: b"")
    monkeypatch.setattr(
        feeds_route,
        "parse_youtube_feed",
        lambda xml: [FeedItem(title="영상", link="https://youtu.be/vid1", guid="vid1")],
    )
    monkeypatch.setattr(
        feeds_route, "fetch_subs", lambda url: ("영상 제목", "자막 본문 내용입니다.", "vid1")
    )

    resp = client.post("/api/feeds/fetch", params={"feed_id": feed_id})
    assert resp.status_code == 200
    body = resp.json()
    assert body["candidates_created"] == 1
    assert body["checked_feeds"] == 1

    candidates = client.get("/api/books?status=candidate").json()
    assert len(candidates) == 1
    assert candidates[0]["source"] == "yt"
    assert candidates[0]["source_ref"] == "yt:vid1"
    assert candidates[0]["scored_at"] is not None


def test_fetch_feeds_youtube_skips_video_without_subs(client, db_path, monkeypatch):
    from import_tools.yt_subs import NoSubtitlesError

    feed_id = _seeded_youtube_feed_id(db_path)
    monkeypatch.setattr(feeds_route, "fetch_feed_xml", lambda url: b"")
    monkeypatch.setattr(
        feeds_route,
        "parse_youtube_feed",
        lambda xml: [FeedItem(title="무자막", link="https://youtu.be/nosub", guid="nosub")],
    )

    def no_subs(url):
        raise NoSubtitlesError("no korean subs")

    monkeypatch.setattr(feeds_route, "fetch_subs", no_subs)

    body = client.post("/api/feeds/fetch", params={"feed_id": feed_id}).json()
    assert body["candidates_created"] == 0
    assert body["feeds"][0]["skipped_no_subs"] == 1
    assert client.get("/api/books?status=candidate").json() == []


def test_fetch_feeds_youtube_dedupes_on_second_run(client, db_path, monkeypatch):
    feed_id = _seeded_youtube_feed_id(db_path)
    monkeypatch.setattr(feeds_route, "fetch_feed_xml", lambda url: b"")
    monkeypatch.setattr(
        feeds_route,
        "parse_youtube_feed",
        lambda xml: [FeedItem(title="영상", link="https://youtu.be/dup", guid="dup")],
    )
    monkeypatch.setattr(feeds_route, "fetch_subs", lambda url: ("제목", "본문 내용입니다.", "dup"))

    first = client.post("/api/feeds/fetch", params={"feed_id": feed_id}).json()
    assert first["candidates_created"] == 1
    second = client.post("/api/feeds/fetch", params={"feed_id": feed_id}).json()
    assert second["candidates_created"] == 0
    assert second["feeds"][0]["skipped_duplicate"] == 1


# --- Feeds CRUD (Epic 14) ---


def test_feeds_crud_roundtrip(client):
    created = client.post(
        "/api/feeds",
        json={"name": "테스트 채널", "type": "youtube", "url_or_channel_id": "UCnew", "topic": "tech"},
    )
    assert created.status_code == 201
    feed = created.json()
    assert feed["enabled"] is True
    fid = feed["id"]

    listed = client.get("/api/feeds").json()
    assert any(f["id"] == fid for f in listed)

    patched = client.patch(f"/api/feeds/{fid}", json={"enabled": False, "topic": "ideas"})
    assert patched.status_code == 200
    assert patched.json()["enabled"] is False
    assert patched.json()["topic"] == "ideas"

    assert client.delete(f"/api/feeds/{fid}").status_code == 204
    assert all(f["id"] != fid for f in client.get("/api/feeds").json())


def test_patch_feed_404(client):
    assert client.patch("/api/feeds/999999", json={"enabled": False}).status_code == 404


def test_disabled_feed_not_fetched(client, db_path, monkeypatch):
    feed_id = _seeded_feed_id(db_path)
    client.patch(f"/api/feeds/{feed_id}", json={"enabled": False})
    monkeypatch.setattr(feeds_route, "fetch_feed_xml", lambda url: b"")
    monkeypatch.setattr(
        feeds_route, "parse_rss", lambda xml: [FeedItem("t", "https://x/1", "1")]
    )
    monkeypatch.setattr(feeds_route, "fetch_article", lambda url: ("t", "본문."))

    body = client.post("/api/feeds/fetch", params={"feed_id": feed_id}).json()
    assert body["checked_feeds"] == 0  # disabled feed is filtered out
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
