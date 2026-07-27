"""Split imported book text into pages, never breaking mid-sentence.

Per SPEC section 4: pages hold at most ~1500 chars, and the only valid break points
are right after sentence-ending punctuation (. ? ! …) or a newline.
"""
import re

MAX_PAGE_CHARS = 1500

_BREAK_RE = re.compile(r"[.?!…]+[\"'\)\]”’]*|\n")


def split_pages(text: str, max_chars: int = MAX_PAGE_CHARS) -> list[str]:
    if not text:
        return [""]

    breakpoints = {m.end() for m in _BREAK_RE.finditer(text)}
    breakpoints.add(len(text))
    breakpoints = sorted(breakpoints)

    pages = []
    start = 0
    while start < len(text):
        limit = start + max_chars
        candidates = [bp for bp in breakpoints if start < bp <= limit]
        if candidates:
            end = candidates[-1]
        else:
            # No break point within max_chars (one very long sentence) — take the
            # next available break point rather than splitting mid-sentence.
            later = [bp for bp in breakpoints if bp > start]
            end = later[0] if later else len(text)
        pages.append(text[start:end])
        start = end

    return pages


def snap_back(text: str, i: int) -> int:
    """Largest sentence/newline boundary at or before `i` (0 if there is none) — used
    to start a served text window at the top of a sentence rather than mid-clause.
    Epic 24."""
    i = max(0, min(i, len(text)))
    best = 0
    for m in _BREAK_RE.finditer(text, 0, i):
        best = m.end()
    return best if best <= i else 0


def snap_forward(text: str, i: int) -> int:
    """Smallest sentence/newline boundary at or after `i` (len(text) if there is none)
    — the closing counterpart to snap_back. Epic 24."""
    if i >= len(text):
        return len(text)
    m = _BREAK_RE.search(text, max(0, i))
    return m.end() if m else len(text)
