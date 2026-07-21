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
