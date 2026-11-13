# MbxRead — Korean reading app

Personal app: read Korean texts, tap words, translate (DeepL/Claude), hand-enrich the
translation, save terms by **dictionary form (lemma)** so all inflections highlight, and
bulk-sync terms to Anki via AnkiConnect. FastAPI + SQLite + kiwipiepy backend, Next.js
frontend (static export), phone access via Tailscale.

## How to work in this repo

1. **Read `docs/STATUS.md` first** — current state + the epic checklist + live ops facts.
   It's **living state**: rewrite it in place, prune finished-work detail as you go (the
   history is in `git log` + `docs/DECISIONS.md`). Don't append to it like a log.
2. **`docs/SPEC.md` is the contract**: architecture, DB schema, API shapes, tokenizer
   heuristic, UX spec, per-epic scope/tests/acceptance criteria, executor conventions
   (section 9). Follow it; log any necessary deviation in `docs/DECISIONS.md` (append-only,
   never rewrite) and amend `docs/ARCHITECTURE.md`.
3. **`docs/README.md` names the doc taxonomy** — which files are living-state vs. contract
   vs. append-only log vs. ephemeral, and the maintenance rule for each. Read it before
   adding or reorganizing any doc.
4. Do **one unit per session** unless the user says otherwise. A unit is one roadmap item
   (`docs/STATUS.md`, "Next: grow the app"); work before the public repo is numbered as
   epics 0–32 (see `docs/README.md`). End every unit with: full test suite green
   (`.venv\Scripts\python.exe -m pytest server/tests -q`), `npm run build` **and**
   `npm run lint` in `web/` green (`tsc` alone once missed a real react-hooks bug), and
   one branch + PR titled `<summary> (unit N)` that includes the docs updates.

## Hard rules

- Python is `.venv\Scripts\python.exe` (Windows). New deps: pip install **and** add to
  `requirements.txt`.
- Never commit or modify: `.env`, `*.sqlite3`, `reader.db`, `.venv/`.
- Tests must pass offline with no API keys: mock DeepL/Claude/krdict/AnkiConnect HTTP,
  temp sqlite per test.
- The server runs on port **8002** (8000 is taken on this machine by an unrelated
  Android app's Docker-based sync service).
