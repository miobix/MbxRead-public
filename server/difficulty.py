"""Difficulty scoring: personal (against the user's saved terms) and general (NIKL grades).

- coverage: fraction of unique lemmas known. ~0.95+ comfortable, <0.85 a slog.
- new_per_page: unknown unique lemmas per 1500-char page; useful even with no saved terms.

Every saved term counts as known, whatever its status. Below COLD_START_THRESHOLD saved
terms, grade-A vocabulary also counts as known. Rationale for both: docs/DECISIONS.md.
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


# General difficulty (for a typical learner) is shown beside personal coverage, never
# blended into it: they answer different questions.
GENERAL_WEIGHTS = {"A": 1.0, "B": 0.5, "C": 0.15}  # unlisted lemmas = 0.0


def score_general_difficulty(text: str, frequency: dict[str, str]) -> dict:
    """Mean GENERAL_WEIGHTS over unique lemmas (unlisted = hard). Bands sit lower than
    score_text's because this rarely nears 0.95; both None for empty text."""
    unique = {t.lemma for t in tokenize(text)}
    if not unique:
        return {"general_coverage": None, "general_level": None}

    total_weight = sum(GENERAL_WEIGHTS.get(frequency.get(lemma, ""), 0.0) for lemma in unique)
    general_coverage = round(total_weight / len(unique), 4)

    if general_coverage >= 0.75:
        general_level = "easy"
    elif general_coverage >= 0.45:
        general_level = "medium"
    else:
        general_level = "hard"

    return {"general_coverage": general_coverage, "general_level": general_level}


def score_text(text: str, known: set[str], frequency: dict[str, str] | None = None) -> dict:
    """Score `text` against `known`; coverage is None (not 0) when no lemma resolves."""
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
