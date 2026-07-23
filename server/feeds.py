"""RSS feed fetching/parsing for the Epic 15 curation queue. Stdlib only — both
seeded feeds (Inven, Ruliweb) are plain RSS 2.0: no namespaces, no <guid> (falls
back to <link>), CDATA-wrapped title/description. Verified live against both
feeds' real XML this session.
"""
import xml.etree.ElementTree as ET
from dataclasses import dataclass

import httpx


class FeedFetchError(Exception):
    """Raised on an unreachable feed URL or unparsable RSS XML."""


@dataclass
class FeedItem:
    title: str
    link: str
    guid: str  # falls back to `link` when the feed has no <guid>


def fetch_feed_xml(url: str) -> bytes:
    """Inven's feed URL 301-redirects http->https, so follow_redirects=True."""
    try:
        resp = httpx.get(url, follow_redirects=True, timeout=10.0)
        resp.raise_for_status()
    except httpx.HTTPError as e:
        raise FeedFetchError(f"Could not fetch feed {url}: {e}")
    return resp.content


def parse_rss(xml_bytes: bytes) -> list[FeedItem]:
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        raise FeedFetchError(f"Malformed RSS XML: {e}")

    items = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        guid = (item.findtext("guid") or "").strip() or link
        if link:
            items.append(FeedItem(title=title, link=link, guid=guid))
    return items


# Epic 14: YouTube channel feeds. A channel's uploads are exposed as an Atom feed at
# youtube.com/feeds/videos.xml?channel_id=UC… (the ~15 latest videos, namespaced XML,
# each <entry> carrying a <yt:videoId>). We store the bare channel_id (UC…) in the
# feed's url_or_channel_id and build the URL here — matching the Epic 15 test that
# seeded a youtube feed with url_or_channel_id='UCabc'. guid = the video id, so the
# fetch route dedupes on `yt:<video_id>`, the same source_ref shape Epic 12's manual
# YouTube import uses (a video imported by hand and by feed collapse to one book).
_ATOM_NS = "http://www.w3.org/2005/Atom"
_YT_NS = "http://www.youtube.com/xml/schemas/2015"


def youtube_feed_url(channel_id: str) -> str:
    return f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"


def parse_youtube_feed(xml_bytes: bytes) -> list[FeedItem]:
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        raise FeedFetchError(f"Malformed YouTube feed XML: {e}")

    items = []
    for entry in root.findall(f"{{{_ATOM_NS}}}entry"):
        vid = (entry.findtext(f"{{{_YT_NS}}}videoId") or "").strip()
        if not vid:
            continue
        title = (entry.findtext(f"{{{_ATOM_NS}}}title") or "").strip()
        link_el = entry.find(f"{{{_ATOM_NS}}}link")
        link = (link_el.get("href") if link_el is not None else "") or (
            f"https://www.youtube.com/watch?v={vid}"
        )
        items.append(FeedItem(title=title, link=link, guid=vid))
    return items
