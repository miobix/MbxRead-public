"""Epic 9 — difficulty scorer (server/difficulty.py + score endpoints)."""
from server import db as db_module
from server.difficulty import known_lemmas, score_text
from server.paging import split_pages
from server.tokenizer import tokenize

STORY = "그는 옷을 입고 나갔다. 날씨가 정말 좋았다! 학교에 가야 했다."
LONG_STORY = "문장입니다. " * 300  # spans many pages


def _lemmas(text: str) -> set[str]:
    return {t.lemma for t in tokenize(text)}


# --- score_text unit tests (deterministic: known-set derived from the text itself) ---


def test_coverage_all_known_is_one():
    result = score_text(STORY, _lemmas(STORY))
    assert result["coverage"] == 1.0
    assert result["new_lemmas"] == 0
    assert result["new_per_page"] == 0.0


def test_coverage_none_known_is_zero():
    result = score_text(STORY, set())
    assert result["coverage"] == 0.0
    assert result["new_lemmas"] == result["total_lemmas"] == len(_lemmas(STORY))


def test_coverage_mixed():
    lemmas = sorted(_lemmas(STORY))
    known = set(lemmas[: len(lemmas) // 2])
    result = score_text(STORY, known)
    expected = round(len(known) / len(lemmas), 4)
    assert result["coverage"] == expected
    assert result["new_lemmas"] == len(lemmas) - len(known)


def test_empty_text_coverage_is_none():
    result = score_text("", set())
    assert result["coverage"] is None
    assert result["total_lemmas"] == 0
    assert result["new_lemmas"] == 0
    assert result["new_per_page"] == 0.0


def test_new_per_page_normalizes_by_reader_page_count():
    result = score_text(LONG_STORY, set())  # nothing known -> every lemma is new
    page_count = len(split_pages(LONG_STORY))
    assert page_count > 1
    assert result["new_per_page"] == round(result["new_lemmas"] / page_count, 2)


# --- known_lemmas: every status counts as known ---


def test_known_lemmas_includes_all_statuses(client, db_path):
    for lemma, status in [("가", "learning"), ("나", "known"), ("다", "ignored")]:
        resp = client.post(
            "/api/terms", json={"lemma": lemma, "translation": "x", "status": status}
        )
        assert resp.status_code == 201
    conn = db_module.get_connection(db_path)
    try:
        assert known_lemmas(conn) == {"가", "나", "다"}
    finally:
        conn.close()


# --- endpoints ---


def test_score_endpoint_shape(client):
    resp = client.post("/api/score", json={"text": STORY})
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"coverage", "new_lemmas", "total_lemmas", "new_per_page"}
    assert body["coverage"] == 0.0  # no terms saved yet


def test_score_endpoint_reflects_known_terms(client):
    lemma = sorted(_lemmas(STORY))[0]
    before = client.post("/api/score", json={"text": STORY}).json()["coverage"]
    client.post("/api/terms", json={"lemma": lemma, "translation": "x", "status": "known"})
    after = client.post("/api/score", json={"text": STORY}).json()["coverage"]
    assert after > before


def test_book_score_caches_and_appears_in_list(client):
    book_id = client.post("/api/books", json={"title": "S", "text": STORY}).json()["id"]

    # Unscored: fields are null in the list payload.
    listed = client.get("/api/books").json()[0]
    assert listed["coverage"] is None
    assert listed["new_per_page"] is None
    assert listed["scored_at"] is None

    scored = client.post(f"/api/books/{book_id}/score").json()
    assert scored["coverage"] == 0.0  # no known terms
    assert scored["new_per_page"] == len(_lemmas(STORY))  # single page
    assert scored["scored_at"] is not None

    relisted = client.get("/api/books").json()[0]
    assert relisted["coverage"] == 0.0
    assert relisted["scored_at"] is not None


def test_score_missing_book_404(client):
    assert client.post("/api/books/999/score").status_code == 404


def test_migration_is_idempotent(client, db_path):
    # init once via the app fixture already; run again and confirm no duplicate column.
    db_module.init_db(db_path)
    db_module.init_db(db_path)
    conn = db_module.get_connection(db_path)
    try:
        cols = [row["name"] for row in conn.execute("PRAGMA table_info(books)")]
        assert cols.count("coverage") == 1
        assert cols.count("new_per_page") == 1
        assert cols.count("scored_at") == 1
    finally:
        conn.close()
