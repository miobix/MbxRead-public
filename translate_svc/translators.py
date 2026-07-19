"""Korean→English translation backends. Pick one via TRANSLATOR in .env."""

import httpx

from . import cache
from .config import ANTHROPIC_API_KEY, DEEPL_API_KEY, TRANSLATOR

DEEPL_URL = "https://api-free.deepl.com/v2/translate"

CLAUDE_SYSTEM = (
    "You translate Korean into natural English for an intermediate Korean learner. "
    "Reply with the English translation on the first line. If the text is a single "
    "word or short phrase, add a second line starting with 'Note: ' giving the "
    "dictionary form and a one-sentence nuance/usage note. If it is a full sentence "
    "containing slang or idiom, add a 'Note: ' line explaining it briefly. "
    "No preamble, nothing else."
)


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


def _claude(text: str) -> str:
    if not ANTHROPIC_API_KEY:
        raise TranslationError("ANTHROPIC_API_KEY is not set — add it to .env")
    import anthropic

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    resp = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=300,
        system=CLAUDE_SYSTEM,
        messages=[{"role": "user", "content": text}],
    )
    return "".join(b.text for b in resp.content if b.type == "text").strip()


_BACKENDS = {"deepl": _deepl, "claude": _claude}


def translate(text: str, backend: str | None = None) -> tuple[str, str, bool]:
    """Returns (translation, backend_name, was_cached)."""
    name = (backend or TRANSLATOR).lower()
    if name not in _BACKENDS:
        raise TranslationError(f"Unknown backend '{name}' (use deepl or claude)")
    cached = cache.get(name, text)
    if cached is not None:
        return cached, name, True
    result = _BACKENDS[name](text)
    cache.put(name, text, result)
    return result, name, False
