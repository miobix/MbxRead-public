import httpx
import pytest

from server import db, usage
from translate_svc import config

# Fake sense axes: a sentence's vector points at whichever cue words it contains.
_AXES = {"버스": 0, "기차": 0, "자전거": 0, "불": 1, "냄새": 1, "월급": 2}


def fake_embed(texts):
    out = []
    for t in texts:
        v = [0.0] * 1024
        for cue, axis in _AXES.items():
            if cue in t:
                v[axis] += 1.0
        v[1023] = 0.1  # no cue: still a valid, non-zero vector
        out.append(v)
    return out


@pytest.fixture
def conn(db_url, monkeypatch):
    monkeypatch.setattr(usage, "embed", fake_embed)
    c = db.get_connection(db_url)
    yield c
    c.close()


def add_book(client, text, status="library", title="t"):
    return client.post("/api/books", json={"title": title, "text": text, "status": status}).json()["id"]


TEXT = (
    "아침마다 버스를 타요. 고기가 너무 타서 냄새가 나요. "
    "주말에는 자전거를 타요. 이번 달 월급을 탔어요. 날씨가 좋아요."
)


def test_split_sentences_keeps_offsets_and_skips_non_korean():
    text = "  첫 문장이에요. 123!\n둘째 문장."
    assert usage.split_sentences(text) == [(2, "첫 문장이에요."), (16, "둘째 문장.")]


def test_index_book_stores_sentences_with_lemmas(client, conn):
    book = add_book(client, TEXT)
    assert usage.index_book(conn, book) == 5
    rows = conn.execute("SELECT text, lemmas FROM sentences ORDER BY start").fetchall()
    assert "타다" in rows[0]["lemmas"] and "버스" in rows[0]["lemmas"]
    assert conn.execute("SELECT indexed_at FROM books WHERE id=%s", (book,)).fetchone()["indexed_at"]
    usage.index_book(conn, book)  # idempotent
    assert conn.execute("SELECT count(*) AS n FROM sentences").fetchone()["n"] == 5


def test_index_next_skips_candidates_and_deleting_a_book_cascades(client, conn, db_url):
    add_book(client, "후보 문장이에요.", status="candidate")
    book = add_book(client, TEXT)
    assert usage.index_next(db_url) is True
    assert usage.index_next(db_url) is False
    assert usage.pending_count(conn) == 0
    client.delete(f"/api/books/{book}")
    assert conn.execute("SELECT count(*) AS n FROM sentences").fetchone()["n"] == 0


@pytest.mark.parametrize("method", usage.METHODS)
def test_search_ranks_same_sense_first_and_excludes_query(client, conn, method):
    usage.index_book(conn, add_book(client, TEXT))
    query = "저는 기차를 타요."
    hits = usage.search(conn, "타다", query, k=3, method=method)
    texts = [h["text"] for h in hits]
    assert query not in texts
    assert "날씨가 좋아요." not in texts  # no 타다
    if method != "keyword":
        assert set(texts[:2]) == {"아침마다 버스를 타요.", "주말에는 자전거를 타요."}


def test_keyword_ranks_by_shared_context_lemmas(client, conn):
    usage.index_book(conn, add_book(client, TEXT))
    hits = usage.search(conn, "타다", "버스를 또 타요.", method="keyword")
    assert hits[0]["text"] == "아침마다 버스를 타요."


def test_search_only_sees_library_books(client, conn):
    book = add_book(client, TEXT)
    usage.index_book(conn, book)
    client.patch(f"/api/books/{book}", json={"status": "discarded"})
    assert usage.search(conn, "타다", "기차를 타요.") == []


def test_rrf_rewards_agreement():
    scores = usage.rrf([1, 2, 3], [3, 1, 4])
    assert max(scores, key=scores.get) == 1
    assert scores[3] > scores[2]


def test_usage_endpoint(client, conn):
    usage.index_book(conn, add_book(client, TEXT, title="일기"))
    add_book(client, "아직 색인 안 된 책이에요.")
    r = client.post("/api/usage", json={"lemma": "타다", "sentence": "기차를 타요.", "k": 2})
    assert r.status_code == 200
    body = r.json()
    assert body["pending_books"] == 1
    assert body["hits"][0]["title"] == "일기" and len(body["hits"]) == 2


def test_usage_endpoint_503_when_embeddings_off(client):
    r = client.post("/api/usage", json={"lemma": "타다", "sentence": "기차를 타요.", "method": "vector"})
    assert r.status_code == 503 and "EMBED_URL" in r.json()["error"]


def test_keyword_search_works_without_embeddings(client):
    r = client.post("/api/usage", json={"lemma": "타다", "sentence": "기차를 타요.", "method": "keyword"})
    assert r.status_code == 200 and r.json()["hits"] == []


class FakeOllama:
    def __init__(self, status=200, content="ride (vehicle); examples 1 and 2."):
        self.status, self.content, self.calls = status, content, []

    def __call__(self, url, json, timeout):
        self.calls.append(json)
        return httpx.Response(
            self.status, json={"message": {"content": self.content}},
            request=httpx.Request("POST", url),
        )


EXPLAIN = {"lemma": "타다", "sentence": "기차를 타요.", "examples": ["버스를 타요.", "자전거를 타요."]}


def test_explain_grounds_prompt_and_caches(client, monkeypatch):
    fake = FakeOllama()
    monkeypatch.setattr(usage.httpx, "post", fake)
    monkeypatch.setattr(usage.krdict, "lookup", lambda w, with_examples=False: [
        {"word": "타다", "definitions": [{"ko": "탈것에 몸을 얹다", "en_word": "ride", "en_def": ""}]}
    ])
    for _ in range(2):
        r = client.post("/api/usage/explain", json=EXPLAIN)
        assert r.json() == {"explanation": "ride (vehicle); examples 1 and 2."}
    assert len(fake.calls) == 1
    prompt = fake.calls[0]["messages"][1]["content"]
    assert "1. 버스를 타요." in prompt and "ride: 탈것에 몸을 얹다" in prompt
    assert fake.calls[0]["model"] == config.OLLAMA_MODEL


def test_explain_keeps_first_line_without_stray_quotes(client, monkeypatch):
    monkeypatch.setattr(usage.httpx, "post", FakeOllama(content="eye (sight). Same sense: 1.'\nmore"))
    monkeypatch.setattr(usage.krdict, "lookup", lambda w, with_examples=False: [])
    assert client.post("/api/usage/explain", json=EXPLAIN).json()["explanation"] == "eye (sight). Same sense: 1."


def test_explain_missing_model_is_a_readable_503(client, monkeypatch):
    monkeypatch.setattr(usage.httpx, "post", FakeOllama(status=404))
    monkeypatch.setattr(usage.krdict, "lookup", lambda w, with_examples=False: [])
    r = client.post("/api/usage/explain", json=EXPLAIN)
    assert r.status_code == 503 and "ollama pull" in r.json()["error"]


def test_explain_unreachable_is_503(client, monkeypatch):
    monkeypatch.setattr(usage.krdict, "lookup", lambda w, with_examples=False: [])
    r = client.post("/api/usage/explain", json=EXPLAIN)
    assert r.status_code == 503 and "unreachable" in r.json()["error"]
