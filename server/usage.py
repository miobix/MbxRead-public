"""Same-sense usage: index library sentences with embeddings, rank a lemma's sentences by
sense, and explain the sense with a local LLM grounded in what was retrieved."""
import json
import logging
import re
from bisect import bisect_right

import httpx
import psycopg

from translate_svc import cache, config, krdict

from . import db
from .paging import _BREAK_RE
from .tokenizer import tokenize

log = logging.getLogger(__name__)

METHODS = ("keyword", "vector", "hybrid")
DEFAULT_METHOD = "vector"  # won the eval (DECISIONS, unit 5)
RRF_K = 60
POOL = 50  # each method's top-N that hybrid fuses
EMBED_BATCH = 32  # TEI's default max client batch

_HANGUL = re.compile(r"[가-힯]")


class Unavailable(Exception):
    """A model service is unconfigured, unreachable, or missing its model."""


def embed(texts: list[str]) -> list[list[float]]:
    if not config.EMBED_URL:
        raise Unavailable("embedding service not configured (EMBED_URL)")
    vectors: list[list[float]] = []
    try:
        for i in range(0, len(texts), EMBED_BATCH):
            r = httpx.post(
                f"{config.EMBED_URL}/embed",
                json={"inputs": texts[i : i + EMBED_BATCH], "truncate": True},
                timeout=120,
            )
            r.raise_for_status()
            vectors += r.json()
    except httpx.HTTPError as e:
        raise Unavailable(f"embedding service failed: {e}") from e
    return vectors


def _vec(v: list[float]) -> str:
    return "[" + ",".join(map(str, v)) + "]"


def split_sentences(text: str) -> list[tuple[int, str]]:
    """(start offset, stripped sentence) for every sentence with Hangul in it."""
    out, start = [], 0
    for end in [m.end() for m in _BREAK_RE.finditer(text)] + [len(text)]:
        chunk = text[start:end]
        stripped = chunk.strip()
        if stripped and _HANGUL.search(stripped):
            out.append((start + len(chunk) - len(chunk.lstrip()), stripped))
        start = end
    return out


def index_book(conn: psycopg.Connection, book_id: int) -> int:
    """(Re)build one book's sentence rows; returns how many were stored."""
    text = "".join(
        r["content"] for r in conn.execute(
            "SELECT content FROM pages WHERE book_id = %s ORDER BY page_no", (book_id,)
        )
    )
    sentences = split_sentences(text)
    starts = [s for s, _ in sentences]
    lemmas: list[set[str]] = [set() for _ in sentences]
    for t in tokenize(text):
        i = bisect_right(starts, t.s) - 1
        if i >= 0:
            lemmas[i].add(t.lemma)
    vectors = embed([s for _, s in sentences]) if sentences else []

    conn.execute("DELETE FROM sentences WHERE book_id = %s", (book_id,))
    conn.cursor().executemany(
        "INSERT INTO sentences (book_id, start, text, lemmas, embedding) "
        "VALUES (%s, %s, %s, %s, %s::vector)",
        [
            (book_id, start, s, sorted(lem), _vec(v))
            for (start, s), lem, v in zip(sentences, lemmas, vectors)
        ],
    )
    conn.execute("UPDATE books SET indexed_at = now() WHERE id = %s", (book_id,))
    conn.commit()
    return len(sentences)


def pending_count(conn: psycopg.Connection) -> int:
    return conn.execute(
        "SELECT count(*) AS n FROM books WHERE status = 'library' AND indexed_at IS NULL"
    ).fetchone()["n"]


def index_next(database_url: str | None = None) -> bool:
    """Index one pending library book; False when there was none."""
    with db.get_connection(database_url) as conn:
        row = conn.execute(
            "SELECT id FROM books WHERE status = 'library' AND indexed_at IS NULL "
            "ORDER BY id LIMIT 1"
        ).fetchone()
        if not row:
            return False
        n = index_book(conn, row["id"])
        log.info("usage index: book %s, %s sentences", row["id"], n)
        return True


def rrf(*ranked: list[int], k: int = RRF_K) -> dict[int, float]:
    scores: dict[int, float] = {}
    for ids in ranked:
        for rank, id_ in enumerate(ids, 1):
            scores[id_] = scores.get(id_, 0.0) + 1 / (k + rank)
    return scores


_CANDIDATES = (
    "FROM sentences s JOIN books b ON b.id = s.book_id "
    "WHERE s.lemmas @> ARRAY[%(lemma)s] AND b.status = 'library' AND s.text <> %(sentence)s"
)


def search(
    conn: psycopg.Connection, lemma: str, sentence: str, k: int = 5, method: str = DEFAULT_METHOD
) -> list[dict]:
    sentence = sentence.strip()
    params: dict = {"lemma": lemma, "sentence": sentence, "pool": POOL}
    keyword = vector = []
    if method in ("keyword", "hybrid"):
        params["ctx"] = sorted({t.lemma for t in tokenize(sentence)} - {lemma})
        keyword = conn.execute(
            "SELECT s.id, (SELECT count(DISTINCT l) FROM unnest(s.lemmas) l "
            "WHERE l = ANY(%(ctx)s)) AS score " + _CANDIDATES
            + " ORDER BY score DESC, s.id LIMIT %(pool)s",
            params,
        ).fetchall()
    if method in ("vector", "hybrid"):
        params["q"] = _vec(embed([sentence])[0])
        vector = conn.execute(
            "SELECT s.id, 1 - (s.embedding <=> %(q)s::vector) AS score " + _CANDIDATES
            + " ORDER BY s.embedding <=> %(q)s::vector, s.id LIMIT %(pool)s",
            params,
        ).fetchall()

    if method == "hybrid":
        # Zero overlap is no evidence; letting those ties vote injects id-order noise.
        fused = rrf([r["id"] for r in keyword if r["score"] > 0], [r["id"] for r in vector])
        scored = sorted(fused.items(), key=lambda kv: (-kv[1], kv[0]))
    else:
        scored = [(r["id"], float(r["score"])) for r in (keyword or vector)]
    scored = scored[:k]
    if not scored:
        return []
    rows = {
        r["id"]: r for r in conn.execute(
            "SELECT s.id, s.book_id, b.title, s.text FROM sentences s "
            "JOIN books b ON b.id = s.book_id WHERE s.id = ANY(%s)",
            ([id_ for id_, _ in scored],),
        )
    }
    return [
        {"book_id": rows[i]["book_id"], "title": rows[i]["title"], "text": rows[i]["text"],
         "score": round(score, 4)}
        for i, score in scored
    ]


_SYSTEM = (
    "You help a learner of Korean. Given a Korean word, the sentence they are reading, "
    "dictionary senses and example sentences from their own library, answer in ONE English "
    "line of this form: '<sense> (<short gloss of the meaning here>). Same sense: <numbers "
    "of the examples that share it, or none>.' Use only the material given. No preamble."
)


def _senses(lemma: str) -> list[str]:
    try:
        entries = krdict.lookup(lemma, with_examples=False)
    except krdict.KrdictUnavailable:
        return []
    return [
        f"{d['en_word'] or d['en_def']}: {d['ko']}"
        for e in entries if e["word"] == lemma for d in e["definitions"]
    ]


def explain(lemma: str, sentence: str, examples: list[str]) -> str:
    backend = f"explain:{config.OLLAMA_MODEL}"
    key = json.dumps([lemma, sentence.strip(), examples], ensure_ascii=False)
    if (hit := cache.get(backend, key)) is not None:
        return hit

    senses = _senses(lemma)
    prompt = "\n".join(
        [f"Word: {lemma}", f"Sentence: {sentence.strip()}"]
        + (["Dictionary senses:"] + [f"- {s}" for s in senses] if senses else [])
        + ["Examples:"] + [f"{i}. {ex}" for i, ex in enumerate(examples, 1)]
    )
    try:
        r = httpx.post(
            f"{config.OLLAMA_URL}/api/chat",
            json={
                "model": config.OLLAMA_MODEL,
                "messages": [{"role": "system", "content": _SYSTEM},
                             {"role": "user", "content": prompt}],
                "stream": False,
                "think": False,
                "options": {"temperature": 0},
            },
            timeout=180,
        )
    except httpx.HTTPError as e:
        raise Unavailable(f"LLM service unreachable ({config.OLLAMA_URL}): {e}") from e
    if r.status_code == 404:
        raise Unavailable(
            f"model {config.OLLAMA_MODEL} not pulled: "
            f"docker compose exec ollama ollama pull {config.OLLAMA_MODEL}"
        )
    if r.status_code != 200:
        raise Unavailable(f"LLM service error {r.status_code}: {r.text[:200]}")
    # gemma sometimes trails a stray quote or a second line (unit 6 eval).
    answer = r.json()["message"]["content"].strip().splitlines()[0].strip().strip("'\"")
    cache.put(backend, key, answer)
    return answer
