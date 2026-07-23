"""Lookup in the National Institute of Korean Language's Learners' Dictionary.

Free API key: https://krdict.korean.go.kr/openApi/openApiInfo
"""

import xml.etree.ElementTree as ET

import httpx

from .config import KRDICT_API_KEY

API_URL = "https://krdict.korean.go.kr/api/search"
VIEW_URL = "https://krdict.korean.go.kr/api/view"


def lookup(word: str, max_entries: int = 5, with_examples: bool = True) -> list[dict]:
    """Returns [{word, pos, target_code, definitions: [{ko, en_word, en_def}],
    examples: [str]}] or [].

    Epic 21: `max_entries` raised from 3 → 5 so more derived headwords (승인하다,
    승인서 alongside 승인) surface for click-to-add. `examples` comes from a second
    `view` call per entry — the search API's `<sense>` carries no example sentences.
    """
    if not KRDICT_API_KEY:
        return []
    try:
        r = httpx.get(
            API_URL,
            params={
                "key": KRDICT_API_KEY,
                "q": word,
                "translated": "y",
                "trans_lang": "1",  # English
                "advanced": "n",
            },
            timeout=10,
        )
        root = ET.fromstring(r.text)
    except Exception:
        return []

    entries = []
    for item in root.findall(".//item")[:max_entries]:
        entry = {
            "word": item.findtext("word", ""),
            "pos": item.findtext("pos", ""),
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
        r = httpx.get(
            VIEW_URL,
            params={
                "key": KRDICT_API_KEY,
                "method": "target_code",
                "target_code": target_code,
                "translated": "y",
                "trans_lang": "1",
            },
            timeout=10,
        )
        root = ET.fromstring(r.text)
    except Exception:
        return []

    examples: list[str] = []
    for ex in root.findall(".//example_info/example"):
        text = (ex.text or "").strip()
        if text and text not in examples:
            examples.append(text)
        if len(examples) >= max_examples:
            break
    return examples
