"""Personal difficulty scoring: how hard is a text *for this user*.

Difficulty is the relationship between a text and what the user already knows, not a
fixed property of the text (see docs/NEXT_STAGE_OPTIONS.md). Two numbers:

- **coverage** — fraction of the text's unique lemmas the user already knows (0..1).
  ~0.95+ comfortable, ~0.90-0.95 productive study zone, <0.85 a slog.
- **new_per_page** — unknown unique lemmas divided by page count (pages split exactly as
  the reader splits them, so "per page" matches reading units). Meaningful even from an
  empty known-set, so it's the headline metric during cold-start.

Known set = every saved term regardless of status: `learning`/`known` are words the user
has met, and `ignored` words won't be studied so they shouldn't inflate difficulty either
(see docs/DECISIONS.md). In practice that's all rows in `terms`.
"""
import sqlite3

from .paging import split_pages
from .tokenizer import tokenize


def known_lemmas(conn: sqlite3.Connection) -> set[str]:
    """Every saved lemma counts as known for scoring (all statuses)."""
    rows = conn.execute("SELECT lemma FROM terms").fetchall()
    return {row["lemma"] for row in rows}


def score_text(text: str, known: set[str]) -> dict:
    """Score `text` against the `known` lemma set.

    coverage is None when the text has no resolvable lemmas (undefined, not 0).
    """
    unique = {t.lemma for t in tokenize(text)}
    total = len(unique)
    new = unique - known
    page_count = len(split_pages(text))  # split_pages never returns an empty list

    coverage = (total - len(new)) / total if total else None
    return {
        "coverage": round(coverage, 4) if coverage is not None else None,
        "new_lemmas": len(new),
        "total_lemmas": total,
        "new_per_page": round(len(new) / page_count, 2),
    }
