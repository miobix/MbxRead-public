"""Compare usage-search methods on hand-labeled sentences (server/data/usage_eval.tsv).

Builds a scratch database on the test Postgres server, indexes the sentences with the real
embedding service, queries each sentence for its own lemma and scores precision@k: the
share of hits that have the same sense. Usage:
    python scripts/eval_usage.py [--k 3] [--embed-url http://127.0.0.1:8081]
"""
import argparse
import csv
import os
import sys
from collections import defaultdict
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg.conninfo import make_conninfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from server import db, usage  # noqa: E402
from server.routes.books import insert_book  # noqa: E402
from server.tokenizer import tokenize  # noqa: E402
from translate_svc import config  # noqa: E402

TSV = Path(__file__).resolve().parent.parent / "server" / "data" / "usage_eval.tsv"
ADMIN_URL = os.getenv("TEST_DATABASE_URL", "postgresql://mbxread:mbxread@127.0.0.1:5433/postgres")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=3)
    ap.add_argument("--embed-url", default=config.EMBED_URL or "http://127.0.0.1:8081")
    args = ap.parse_args()
    config.EMBED_URL = args.embed_url.rstrip("/")

    rows = list(csv.DictReader(open(TSV, encoding="utf-8"), delimiter="\t"))
    skipped = [r for r in rows if r["lemma"] not in {t.lemma for t in tokenize(r["sentence"])}]
    rows = [r for r in rows if r not in skipped]
    sense_of = {r["sentence"]: r["sense"] for r in rows}

    name = f"mbxread_eval_{uuid4().hex[:8]}"
    admin = psycopg.connect(ADMIN_URL, autocommit=True)
    admin.execute(f"CREATE DATABASE {name}")
    url = make_conninfo(ADMIN_URL, dbname=name)
    config.DATABASE_URL = url  # cache/krdict helpers follow the scratch db
    try:
        db.init_db(url)
        with db.get_connection(url) as conn:
            by_lemma = defaultdict(list)
            for r in rows:
                by_lemma[r["lemma"]].append(r["sentence"])
            for lemma, sents in by_lemma.items():
                book = insert_book(conn, title=lemma, text="\n".join(sents), source="paste")
                usage.index_book(conn, book["id"])

            totals = {m: [] for m in usage.METHODS}
            per_lemma = {m: defaultdict(list) for m in usage.METHODS}
            chance = []
            failures = []
            for r in rows:
                # Only this lemma's book is searchable: 배를 타고 (labeled 배) also holds 타다.
                conn.execute(
                    "UPDATE books SET status = CASE WHEN title = %s "
                    "THEN 'library' ELSE 'candidate' END",
                    (r["lemma"],),
                )
                same =sum(1 for s in by_lemma[r["lemma"]] if sense_of[s] == r["sense"]) - 1
                chance.append(same / (len(by_lemma[r["lemma"]]) - 1))
                for m in usage.METHODS:
                    hits = usage.search(conn, r["lemma"], r["sentence"], k=args.k, method=m)
                    p = sum(sense_of[h["text"]] == r["sense"] for h in hits) / args.k
                    totals[m].append(p)
                    per_lemma[m][r["lemma"]].append(p)
                    if m == usage.DEFAULT_METHOD and p < 0.5:
                        failures.append((r, [sense_of[h["text"]] for h in hits]))
    finally:
        admin.execute(f"DROP DATABASE {name} WITH (FORCE)")
        admin.close()

    avg = lambda xs: sum(xs) / len(xs)  # noqa: E731
    print(f"{len(rows)} queries, {len(skipped)} skipped (tokenizer missed the lemma), k={args.k}")
    for r in skipped:
        print(f"  skipped: {r['lemma']} [{r['sense']}] {r['sentence']}")
    print(f"\nprecision@{args.k}   chance {avg(chance):.2f}")
    print("lemma      " + "  ".join(f"{m:>7}" for m in usage.METHODS))
    for lemma in by_lemma:
        print(f"{lemma:<8}" + "  ".join(f"{avg(per_lemma[m][lemma]):7.2f}" for m in usage.METHODS))
    print("ALL     " + "  ".join(f"{avg(totals[m]):7.2f}" for m in usage.METHODS))
    print(f"\n{usage.DEFAULT_METHOD} queries below 0.5:")
    for r, got in failures:
        print(f"  {r['lemma']} [{r['sense']}] {r['sentence']}  -> {got}")


if __name__ == "__main__":
    main()
