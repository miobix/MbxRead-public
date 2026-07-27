"""Split imported book text into pages, never breaking mid-sentence.

Per SPEC section 4: pages hold at most ~1500 chars, and the only valid break points
are right after sentence-ending punctuation (. ? ! …) or a newline.
"""
import bisect
import re

MAX_PAGE_CHARS = 1500

# Reader-facing pagination (settings.page_rows/chars_per_row) targets this many
# estimated visual rows per page; see estimate_rows/split_pages_by_rows below.
DEFAULT_MAX_ROWS = 22
DEFAULT_CHARS_PER_ROW = 32

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


def estimate_rows(s: str, chars_per_row: int) -> int:
    """Approximate how many visual rows `s` renders as under the reader's
    whitespace-preserving layout: every newline forces a row break, and each line
    between newlines separately wraps every `chars_per_row` characters. This is a
    heuristic (real wrapping depends on the device's font/width), not a DOM
    measurement — chars_per_row is a settings.py-editable estimate the user tunes
    to their own phone once they're actually looking at it."""
    chars_per_row = max(1, chars_per_row)
    rows = 0
    for line in s.split("\n"):
        rows += max(1, -(-len(line) // chars_per_row))  # ceil div; blank line = 1 row
    return rows


def split_pages_by_rows(
    text: str, max_rows: int = DEFAULT_MAX_ROWS, chars_per_row: int = DEFAULT_CHARS_PER_ROW
) -> list[str]:
    """Same break-point contract as split_pages (never split mid-sentence), but
    bounded by estimated visual rows instead of raw character count — so a page
    dense with short lines (subtitles, dialogue) and a page of one long paragraph
    end up feeling like similar amounts of on-screen content, rather than the
    newline-heavy one ballooning past what fits on screen.

    A single forward pass over the sorted breakpoints (each one visited at most
    once across the whole call, via the `idx` cursor) — not a per-page rescan of
    the full breakpoint list — so pagination time stays linear in text length even
    for very long books.
    """
    if not text:
        return [""]

    breakpoints = sorted({m.end() for m in _BREAK_RE.finditer(text)} | {len(text)})
    n = len(breakpoints)

    pages = []
    start = 0
    idx = 0
    while start < len(text):
        idx = bisect.bisect_right(breakpoints, start, idx)
        end = start
        j = idx
        while j < n and estimate_rows(text[start:breakpoints[j]], chars_per_row) <= max_rows:
            end = breakpoints[j]
            j += 1
        if end == start:
            # No break point fits within max_rows (one very long sentence/line) —
            # take the next available break point rather than splitting mid-sentence.
            end = breakpoints[idx] if idx < n else len(text)
            j = idx + 1
        pages.append(text[start:end])
        start = end
        idx = j

    return pages
