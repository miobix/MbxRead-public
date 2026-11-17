"""Record the GitHub Pages demo's data from the real app (unit 11).

Imports the texts in scripts/demo_samples/ into a scratch database, indexes them with the
real embedding service, then calls the app's own API in-process and saves the responses
to web/lib/demo-data.json: books, text windows, settings, stats, a DeepL translation and
krdict entries for every lemma, and Similar usage + Explain for a few two-sense words.
Needs DEEPL_API_KEY / KRDICT_API_KEY in .env and the compose db, embed and ollama up.

    .venv\\Scripts\\python.exe -m scripts.build_demo_data
"""
import json
import os
import re
import sys
import time
from datetime import date
from pathlib import Path
from uuid import uuid4

import psycopg
from fastapi.testclient import TestClient
from psycopg.conninfo import make_conninfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from server import db, usage  # noqa: E402
from server.main import create_app  # noqa: E402
from server.routes.books import _score_and_cache, insert_book  # noqa: E402
from translate_svc import config  # noqa: E402

SAMPLES_DIR = ROOT / "scripts" / "demo_samples"
OUT = ROOT / "web" / "lib" / "demo-data.json"
ADMIN_URL = os.getenv("TEST_DATABASE_URL", "postgresql://mbxread:mbxread@127.0.0.1:5433/postgres")
EMBED_URL = os.getenv("DEMO_EMBED_URL", "http://127.0.0.1:8081")
OLLAMA_URL = os.getenv("DEMO_OLLAMA_URL", "http://127.0.0.1:11434")

KIMCHI_URL = "https://ko.wikipedia.org/w/index.php?title=%EA%B9%80%EC%B9%98&oldid=42547847"
SAMPLES = [
    {"file": "01-spring-mountain.txt", "topic": "travel", "credit": None},
    {"file": "02-neighborhood-bakery.txt", "topic": "food", "credit": None},
    {
        "file": "03-kimchi-wikipedia.txt", "topic": "culture", "source": "article",
        "source_url": KIMCHI_URL,
        "credit": "Excerpt (introduction and 근·현대 section) of \"김치\", Korean Wikipedia, "
                  "revision 42547847 (2026-09-24), CC BY-SA 4.0.",
    },
]
# Two senses each across the samples, so the seeded results show the sense split.
SEEDED_USAGE = ["풀리다", "다리", "눈"]

_SENTENCE_END = re.compile(r"[.?!…]+|\n")


def extract_sentence(content: str, center: int) -> str:
    """Port of web/lib/sentence.ts extractSentence, so the keys match what the reader sends."""
    start, end = 0, len(content)
    for m in _SENTENCE_END.finditer(content):
        if m.end() <= center:
            start = m.end()
        else:
            end = m.end()
            break
    return content[start:end].strip()


def _ok(resp):
    if resp.status_code >= 400:
        raise SystemExit(f"{resp.request.method} {resp.request.url}: {resp.status_code} {resp.text}")
    return resp.json()


# krdict blocks an IP that sends requests in a burst (DECISIONS, 2026-10-02 "krdict flood").
KRDICT_PACE_SECONDS = 3
_krdict_down = False


def _dict_lookup(client, lemma: str, recorded: dict) -> list | None:
    """Reuse an entry an earlier run recorded; else one paced request, never a retry.
    The first failure stops krdict for the rest of the run. None = not recorded."""
    global _krdict_down
    if lemma in recorded:
        return recorded[lemma]
    if _krdict_down:
        return None
    time.sleep(KRDICT_PACE_SECONDS)
    resp = client.get("/api/dict", params={"word": lemma})
    if resp.status_code == 503:
        print(f"  krdict failed ({resp.json()['error']}); no more krdict calls this run")
        _krdict_down = True
        return None
    return _ok(resp)


def build(url: str) -> dict:
    db.init_db(url)
    # The translate/krdict caches connect via config.DATABASE_URL; keep them off the live db.
    config.DATABASE_URL = url
    config.EMBED_URL, config.OLLAMA_URL = EMBED_URL, OLLAMA_URL
    with db.get_connection(url) as conn:
        credits = {}
        for sample in SAMPLES:
            title, _, text = (SAMPLES_DIR / sample["file"]).read_text(encoding="utf-8").partition("\n")
            book = insert_book(
                conn, title=title.strip(), text=text.strip(), source=sample.get("source", "paste"),
                topic=sample["topic"], source_url=sample.get("source_url", ""),
            )
            _score_and_cache(conn, book["id"], text.strip())
            usage.index_book(conn, book["id"])
            conn.commit()
            if sample["credit"]:
                credits[book["id"]] = sample["credit"]

    config.EMBED_URL = ""  # the app's background indexer has nothing left to do
    with TestClient(create_app(url)) as client:
        books = _ok(client.get("/api/books"))
        details, texts = {}, {}
        for b in books:
            details[b["id"]] = _ok(client.get(f"/api/books/{b['id']}"))
            window = _ok(client.get(f"/api/books/{b['id']}/text?offset=0"))
            window.pop("terms")  # rebuilt in the browser from the visitor's own terms
            texts[b["id"]] = window

        lemmas = sorted({t["lemma"] for w in texts.values() for t in w["tokens"]})
        recorded_dict = json.loads(OUT.read_text(encoding="utf-8"))["dictionary"] if OUT.exists() else {}
        translations, dictionary = {}, {}
        for i, lemma in enumerate(lemmas, 1):
            print(f"[{i}/{len(lemmas)}] {lemma}")
            translations[lemma] = _ok(client.post("/api/translate", json={"text": lemma}))
            dictionary[lemma] = _dict_lookup(client, lemma, recorded_dict)

        config.EMBED_URL = EMBED_URL
        seeded = {}
        for w in texts.values():
            for t in w["tokens"]:
                if t["lemma"] not in SEEDED_USAGE:
                    continue
                sentence = extract_sentence(w["content"], t["s"])
                found = _ok(client.post("/api/usage", json={"lemma": t["lemma"], "sentence": sentence}))
                examples = [h["text"] for h in found["hits"]]
                explained = _ok(client.post("/api/usage/explain", json={
                    "lemma": t["lemma"], "sentence": sentence, "examples": examples,
                }))
                seeded[f"{t['lemma']}|{sentence}"] = {"usage": found, "explain": explained}
                print(f"usage {t['lemma']}: {explained['explanation']}")

        return {
            "generated": date.today().isoformat(),
            "credits": credits,
            "seeded_usage_lemmas": SEEDED_USAGE,
            "books": books,
            "details": details,
            "texts": texts,
            "settings": _ok(client.get("/api/settings")),
            "stats": _ok(client.get("/api/stats")),
            "translations": translations,
            "dictionary": {k: v for k, v in dictionary.items() if v is not None},
            "usage": seeded,
        }


def main() -> None:
    name = f"mbxread_demo_{uuid4().hex[:8]}"
    admin = psycopg.connect(ADMIN_URL, autocommit=True)
    admin.execute(f"CREATE DATABASE {name}")
    try:
        data = build(make_conninfo(ADMIN_URL, dbname=name))
    finally:
        admin.execute(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)")
        admin.close()
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
