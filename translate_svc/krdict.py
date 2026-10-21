"""Lookup in the National Institute of Korean Language's Learners' Dictionary.

Free API key: https://krdict.korean.go.kr/openApi/openApiInfo
"""

import json
import sqlite3
import time
import xml.etree.ElementTree as ET
from contextlib import closing
from datetime import datetime

import httpx

from .config import CACHE_DB, KRDICT_API_KEY

API_URL = "https://krdict.korean.go.kr/api/search"
VIEW_URL = "https://krdict.korean.go.kr/api/view"
COOLDOWN_S = 30 * 60


class KrdictUnavailable(Exception):
    pass


def _conn():
    conn = sqlite3.connect(CACHE_DB)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS krdict_cache (key TEXT PRIMARY KEY, body TEXT NOT NULL,"
        " created TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
    )
    conn.execute("CREATE TABLE IF NOT EXISTS krdict_state (k TEXT PRIMARY KEY, v REAL NOT NULL)")
    return conn


def blocked_until() -> float | None:
    with closing(_conn()) as conn:
        row = conn.execute("SELECT v FROM krdict_state WHERE k = 'blocked_until'").fetchone()
    return row[0] if row and row[0] > time.time() else None


def _trip() -> None:
    with closing(_conn()) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO krdict_state (k, v) VALUES ('blocked_until', ?)",
            (time.time() + COOLDOWN_S,),
        )
        conn.commit()


def _get(url: str, params: dict) -> ET.Element:
    """Cached GET. The first failure opens a cooldown during which nothing is sent."""
    key = json.dumps([url, {k: v for k, v in params.items() if k != "key"}], sort_keys=True)
    with closing(_conn()) as conn:
        row = conn.execute("SELECT body FROM krdict_cache WHERE key = ?", (key,)).fetchone()
    if row:
        return ET.fromstring(row[0])
    until = blocked_until()
    if until:
        raise KrdictUnavailable(f"krdict paused after a failure, until {datetime.fromtimestamp(until):%H:%M}")
    try:
        r = httpx.get(url, params={"key": KRDICT_API_KEY, **params}, timeout=10)
        root = ET.fromstring(r.text)
        if getattr(r, "status_code", 200) != 200 or root.tag == "error":
            raise ValueError(root.findtext("message", "") or f"HTTP {r.status_code}")
    except Exception as e:
        _trip()
        raise KrdictUnavailable(f"krdict request failed ({e}); paused for {COOLDOWN_S // 60} min") from e
    with closing(_conn()) as conn:
        conn.execute("INSERT OR REPLACE INTO krdict_cache (key, body) VALUES (?, ?)", (key, r.text))
        conn.commit()
    return root


def lookup(word: str, max_entries: int = 5, with_examples: bool = True) -> list[dict]:
    """Returns [{word, pos, origin, target_code, definitions: [{ko, en_word, en_def}],
    examples: [str]}] or [].

    `examples` needs a second `view` call per entry: search results carry none.
    Raises KrdictUnavailable on a failed request or during the cooldown after one.
    """
    if not KRDICT_API_KEY:
        return []
    root = _get(
        API_URL,
        {"q": word, "translated": "y", "trans_lang": "1", "advanced": "n"},  # English
    )

    entries = []
    for item in root.findall(".//item")[:max_entries]:
        entry = {
            "word": item.findtext("word", ""),
            "pos": item.findtext("pos", ""),
            "origin": item.findtext("origin", ""),
            "target_code": item.findtext("target_code", ""),
            "definitions": [],
            "examples": [],
        }
        for sense in item.findall("sense")[:3]:
            tr = sense.find("translation")
            entry["definitions"].append(
                {
                    "ko": sense.findtext("definition", ""),
                    "en_word": tr.findtext("trans_word", "") if tr is not None else "",
                    "en_def": tr.findtext("trans_dfn", "") if tr is not None else "",
                }
            )
        entries.append(entry)

    if with_examples:
        for entry in entries:
            if entry["target_code"]:
                entry["examples"] = _view_examples(entry["target_code"])
    return entries


def _view_examples(target_code: str, max_examples: int = 5) -> list[str]:
    """Fetch example sentences for one dictionary entry via krdict's `view` API.

    Examples live under `word_info/sense_info/example_info/example`, which the
    `search` API omits — hence the separate call keyed by the item's target_code.
    Best-effort: returns [] on any failure (no key, network, unexpected XML)."""
    try:
        root = _get(
            VIEW_URL,
            {"method": "target_code", "q": target_code, "target_code": target_code, "translated": "y", "trans_lang": "1"},
        )
    except KrdictUnavailable:
        return []

    examples: list[str] = []
    for ex in root.findall(".//example_info/example"):
        text = (ex.text or "").strip()
        if text and text not in examples:
            examples.append(text)
        if len(examples) >= max_examples:
            break
    return examples

