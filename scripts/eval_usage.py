"""Compare usage-search methods on hand-labeled sentences (server/data/usage_eval.tsv).

Builds a scratch database on the test Postgres server, indexes the sentences with the real
embedding service, queries each sentence for its own lemma and scores precision@k: the
share of hits that have the same sense. With --explain it instead scores the LLM's
Explain line on the default method's top 5 (needs Ollama). Usage:
    python scripts/eval_usage.py [--k 3] [--explain] [--embed-url http://127.0.0.1:8081]
"""
import argparse
import csv
import os
import re
import sys
import time
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

# Fixed sense lists stand in for krdict: reproducible, no key. Names match the labels.
SENSES = {
    "타다": ["ride: get on a vehicle or animal", "burn: be burned by fire or heat, or tanned",
             "receive: be given money or a prize"],
    "쓰다": ["write: put words on paper", "use: make use of a thing, money or time",
             "wear: put on a hat, glasses or mask, or hold an umbrella", "bitter: taste bitter"],
    "차다": ["kick: strike with the foot", "full: become filled", "cold: be cold to the touch",
             "wear: carry on the body, such as a watch or a belt"],
    "걸리다": ["hang: be hung or caught on something", "take time: require an amount of time",
              "catch ill: come down with an illness"],
    "풀다": ["untie: undo a knot or wrapping", "solve: find an answer to a problem",
             "relieve: ease stress, anger or tiredness"],
    "눈": ["eye: the organ of sight", "snow: frozen flakes that fall in winter"],
    "배": ["belly: the stomach area", "ship: a boat", "pear: the fruit"],
    "다리": ["leg: the limb", "bridge: a structure crossing water or a road"],
}

_LINE = re.compile(
    r"^\s*(?P<sense>[^()]+?)\s*\(.*\)\.?\s*Same sense:\s*(?P<nums>none|[\d,\s]+?)\s*\.?\s*$", re.I | re.S
)


def _norm(s: str) -> str:
    return " ".join(s.lower().replace("_", " ").split())


def parse_explanation(line: str) -> tuple[str, set[int]] | None:
    """(sense, picked example numbers) from '<sense> (<gloss>). Same sense: 1, 3.'"""
    m = _LINE.match(line)
    if not m:
        return None
    nums = m["nums"].strip().lower()
    return _norm(m["sense"]), set() if nums == "none" else {int(n) for n in re.findall(r"\d+", nums)}


def sense_matches(named: str, label: str) -> bool:
    label = _norm(label)
    return named == label or named.startswith(label + " ")


def score_picks(picks: set[int], truth: list[bool]) -> tuple[int, int, int, int]:
    """(tp, fp, fn, tn) of the model's 'same sense' picks; truth[i] is example i+1."""
    tp = sum(1 for i, t in enumerate(truth, 1) if t and i in picks)
    fp = sum(1 for i, t in enumerate(truth, 1) if not t and i in picks)
    fn = sum(1 for i, t in enumerate(truth, 1) if t and i not in picks)
    return tp, fp, fn, len(truth) - tp - fp - fn


def explain_eval(conn, rows, by_lemma, sense_of) -> None:
    usage._senses = lambda lemma: SENSES[lemma]
    stats = defaultdict(lambda: {"n": 0, "fmt": 0, "sense": 0, "tp": 0, "fp": 0, "fn": 0, "tn": 0})
    misses, secs = [], []
    for r in rows:
        conn.execute(
            "UPDATE books SET status = CASE WHEN title = %s THEN 'library' ELSE 'candidate' END",
            (r["lemma"],),
        )
        hits = usage.search(conn, r["lemma"], r["sentence"], k=5)
        examples = [h["text"] for h in hits]
        truth = [sense_of[e] == r["sense"] for e in examples]
        t = time.time()
        line = usage.explain(r["lemma"], r["sentence"], examples)
        secs.append(time.time() - t)
        s = stats[r["lemma"]]
        s["n"] += 1
        parsed = parse_explanation(line)
        ok = False
        if parsed:
            s["fmt"] += 1
            named, picks = parsed
            ok = sense_matches(named, r["sense"])
            s["sense"] += ok
            for key, v in zip(("tp", "fp", "fn", "tn"), score_picks(picks, truth)):
                s[key] += v
        if not parsed or not ok or score_picks(parsed[1], truth)[1:3] != (0, 0):
            misses.append((r, truth, line))

    ratio = lambda a, b: a / b if b else float("nan")  # noqa: E731
    print(f"{len(rows)} explanations, model {config.OLLAMA_MODEL}, "
          f"median {sorted(secs)[len(secs) // 2]:.1f}s, max {max(secs):.1f}s")
    print("lemma     format  sense  pick-prec  pick-recall  rejects-wrong")
    total = defaultdict(int)
    for lemma, s in list(stats.items()) + [("ALL", None)]:
        if s is None:
            s = total
        else:
            for key, v in s.items():
                total[key] += v
        print(f"{lemma:<8}{ratio(s['fmt'], s['n']):7.2f}{ratio(s['sense'], s['n']):7.2f}"
              f"{ratio(s['tp'], s['tp'] + s['fp']):11.2f}{ratio(s['tp'], s['tp'] + s['fn']):13.2f}"
              f"{ratio(s['tn'], s['tn'] + s['fp']):15.2f}")
    print(f"\nmisses (wrong sense, bad format, or any wrong pick): {len(misses)}")
    for r, truth, line in misses:
        marks = "".join("+" if t else "-" for t in truth)
        print(f"  {r['lemma']} [{r['sense']}] {r['sentence']}  examples {marks}\n      -> {line}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=3)
    ap.add_argument("--explain", action="store_true")
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

            if args.explain:
                explain_eval(conn, rows, by_lemma, sense_of)
                return

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
