"""Epic 9 — difficulty scorer (server/difficulty.py + score endpoints).
Epic 13 adds the cold-start frequency fallback — see the tests below that section."""
from server import db as db_module
from server.difficulty import (
    COLD_START_THRESHOLD,
    frequency_grades,
    known_lemmas,
    score_text,
)
from server.paging import split_pages
from server.tokenizer import tokenize

# Every lemma here is graded 'A' (beginner/common) in the bundled NIKL list, so with
# an empty known-set the Epic 13 cold-start fallback treats the whole story as
# familiar — see the "cold start" test section below for why this text was picked.
STORY = "그는 옷을 입고 나갔다. 날씨가 정말 좋았다! 학교에 가야 했다."
LONG_STORY = "문장입니다. " * 300  # spans many pages

# Mixes grade-A (그, 문제), grade-C (잠기다), and words absent from the list entirely
# (반추하다, 사색, 형이상학) — used to test partial cold-start coverage and to show a
# rare/advanced text scoring harder than STORY's all-common text.
RARE_STORY = "그는 형이상학적 문제를 반추하며 사색에 잠겼다."


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
    # No terms saved yet, but every STORY lemma is grade A — Epic 13's cold-start
    # fallback treats the whole thing as familiar (see the cold-start test section).
    assert body["coverage"] == 1.0


def test_score_endpoint_reflects_known_terms(client):
    # Unlike STORY, RARE_STORY isn't all grade-A, so saving one of its non-A lemmas
    # has room to move coverage up from a non-maxed cold-start baseline.
    lemma = "형이상학"  # not in the bundled list at all -> not assumed familiar
    before = client.post("/api/score", json={"text": RARE_STORY}).json()["coverage"]
    client.post("/api/terms", json={"lemma": lemma, "translation": "x", "status": "known"})
    after = client.post("/api/score", json={"text": RARE_STORY}).json()["coverage"]
    assert after > before


def test_book_score_caches_and_appears_in_list(client):
    book_id = client.post("/api/books", json={"title": "S", "text": STORY}).json()["id"]

    # Unscored: fields are null in the list payload.
    listed = client.get("/api/books").json()[0]
    assert listed["coverage"] is None
    assert listed["new_per_page"] is None
    assert listed["scored_at"] is None

    scored = client.post(f"/api/books/{book_id}/score").json()
    # No known terms, but STORY is all grade A -> cold-start fallback = full coverage.
    assert scored["coverage"] == 1.0
    assert scored["new_per_page"] == 0.0
    assert scored["scored_at"] is not None

    relisted = client.get("/api/books").json()[0]
    assert relisted["coverage"] == 1.0
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


# --- Epic 13: cold-start frequency fallback ---


def test_frequency_grades_reads_from_seeded_table(db_path):
    db_module.init_db(db_path)
    conn = db_module.get_connection(db_path)
    try:
        grades = frequency_grades(conn)
        assert len(grades) > 5000
        assert grades["가다"] == "A"
    finally:
        conn.close()


def test_score_text_without_frequency_arg_is_unchanged():
    # Pure Epic 9 behavior when frequency isn't passed at all (default None).
    result = score_text(STORY, set())
    assert result["coverage"] == 0.0


def test_cold_start_fallback_treats_grade_a_as_familiar():
    grades = {"그": "A", "옷": "A", "입다": "A"}
    result = score_text("그는 옷을 입고.", set(), grades)
    assert result["coverage"] == 1.0
    assert result["new_lemmas"] == 0


def test_cold_start_fallback_gives_partial_credit_for_mixed_text():
    grades = {"그": "A", "문제": "A", "잠기다": "C"}  # 반추하다/사색/형이상학 absent
    result = score_text(RARE_STORY, set(), grades)
    lemmas = _lemmas(RARE_STORY)
    assert result["total_lemmas"] == len(lemmas)
    assert result["new_lemmas"] == len(lemmas) - 2  # only 그/문제 assumed familiar
    assert 0 < result["coverage"] < 1.0


def test_frequency_fallback_ignored_once_known_set_passes_threshold():
    grades = {"그": "A"}
    known = {f"단어{i}" for i in range(COLD_START_THRESHOLD)}  # thick enough already
    result = score_text("그는 간다.", known, grades)
    # "그" isn't in `known`, and the fallback no longer applies -> not familiar.
    assert result["coverage"] < 1.0


def test_rare_text_scores_harder_than_common_text_with_empty_known_set(client):
    # Epic 13 acceptance criterion, exercised through the real endpoint (real
    # frequency_grades from the seeded table, not a hand-built dict).
    common = client.post("/api/score", json={"text": STORY}).json()
    rare = client.post("/api/score", json={"text": RARE_STORY}).json()
    assert rare["coverage"] < common["coverage"]
    assert common["coverage"] == 1.0
