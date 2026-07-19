"""Lookup in the National Institute of Korean Language's Learners' Dictionary.

Free API key: https://krdict.korean.go.kr/openApi/openApiInfo
"""

import xml.etree.ElementTree as ET

import httpx

from .config import KRDICT_API_KEY

API_URL = "https://krdict.korean.go.kr/api/search"


def lookup(word: str, max_entries: int = 3) -> list[dict]:
    """Returns [{word, pos, definitions: [{ko, en_word, en_def}]}] or []."""
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
            "definitions": [],
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
    return entries
