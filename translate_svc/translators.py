"""Korean→English translation backends. Pick one via TRANSLATOR in .env."""

import httpx

from . import cache
from .config import DEEPL_API_KEY, TRANSLATOR

DEEPL_URL = "https://api-free.deepl.com/v2/translate"


class TranslationError(Exception):
    pass


def _deepl(text: str) -> str:
    if not DEEPL_API_KEY:
        raise TranslationError("DEEPL_API_KEY is not set — add it to .env")
    r = httpx.post(
        DEEPL_URL,
        headers={"Authorization": f"DeepL-Auth-Key {DEEPL_API_KEY}"},
        data={"text": text, "source_lang": "KO", "target_lang": "EN"},
        timeout=15,
    )
    if r.status_code != 200:
        raise TranslationError(f"DeepL error {r.status_code}: {r.text[:200]}")
    return r.json()["translations"][0]["text"]


_BACKENDS = {"deepl": _deepl}


def translate(text: str, backend: str | None = None) -> tuple[str, str, bool]:
    """Returns (translation, backend_name, was_cached)."""
    name = (backend or TRANSLATOR).lower()
    if name not in _BACKENDS:
        raise TranslationError(f"Unknown backend '{name}' (use deepl)")
    cached = cache.get(name, text)
    if cached is not None:
        return cached, name, True
    result = _BACKENDS[name](text)
    cache.put(name, text, result)
    return result, name, False
