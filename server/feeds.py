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
