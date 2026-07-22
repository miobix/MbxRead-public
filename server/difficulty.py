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

**Epic 13 — cold-start fallback.** A brand-new user has an empty (or tiny) `terms`
table, so every text scores 0% coverage regardless of how easy it actually is —
uninformative. When `known` has fewer than `COLD_START_THRESHOLD` lemmas, `score_text`
also treats grade-A (beginner/common) lemmas from the bundled `vocab_levels` reference
table as familiar, even if never personally saved — see docs/DECISIONS.md for why
grade A specifically (not B/C, not a continuous weighting) and why the threshold is
50. Once the personal known-set passes that threshold, the frequency signal is
dropped entirely and scoring is pure personal coverage, same as pre-Epic-13.
"""
import sqlite3

from .paging import split_pages
from .tokenizer import tokenize

COLD_START_THRESHOLD = 50


def known_lemmas(conn: sqlite3.Connection) -> set[str]:
    """Every saved lemma counts as known for scoring (all statuses)."""
    rows = conn.execute("SELECT lemma FROM terms").fetchall()
    return {row["lemma"] for row in rows}


def frequency_grades(conn: sqlite3.Connection) -> dict[str, str]:
    """lemma -> NIKL grade ('A'..'C'), for score_text's cold-start fallback."""
    rows = conn.execute("SELECT lemma, grade FROM vocab_levels").fetchall()
    return {row["lemma"]: row["grade"] for row in rows}


def score_text(text: str, known: set[str], frequency: dict[str, str] | None = None) -> dict:
    """Score `text` against the `known` lemma set.

    coverage is None when the text has no resolvable lemmas (undefined, not 0).
    `frequency` (optional): lemma->grade map from `frequency_grades`, consulted only
    when `known` is thinner than COLD_START_THRESHOLD (see module docstring).
    """
    unique = {t.lemma for t in tokenize(text)}
    total = len(unique)
    page_count = len(split_pages(text))  # split_pages never returns an empty list

    if frequency and len(known) < COLD_START_THRESHOLD:
        familiar = known | {lemma for lemma in unique if frequency.get(lemma) == "A"}
    else:
        familiar = known
    new = unique - familiar

    coverage = (total - len(new)) / total if total else None
    return {
        "coverage": round(coverage, 4) if coverage is not None else None,
        "new_lemmas": len(new),
        "total_lemmas": total,
        "new_per_page": round(len(new) / page_count, 2),
    }
