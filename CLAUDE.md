# MbxRead — Korean reading app (custom rebuild, replaces Lute)

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
4. Do **one epic per session** unless the user says otherwise. End every epic with: full
   test suite green (`.venv\Scripts\python.exe -m pytest server/tests -q`), `npm run build`
   **and** `npm run lint` in `web/` green (Epic ≥ 4 — `tsc` alone missed a real
   react-hooks bug in Epic 4), one commit `Epic N: <summary>` that includes the docs
   updates.
5. **Hanja study: run `/hanja [字]`** (`.claude/skills/hanja/SKILL.md`, scope in SPEC
   Epic 27) to analyse one character from the user's Anki deck and save picked words. It
   reads the user's `Hanja::*` Anki decks and **never writes to them**; use `save --dry-run`
   to test, a real `save` changes the live DB.
6. **Daily hanja word list: run `/hanja-today`** (`.claude/skills/hanja-today/SKILL.md`,
   SPEC Epic 29). One call, no krdict, writes `hanja_output/<date>.md` for today's
   characters of the study deck (`STUDY_DECK`, never Pending). Read-only on Anki.

## Hard rules

- Python is `.venv\Scripts\python.exe` (Windows). New deps: pip install **and** add to
  `requirements.txt`.
- Never commit or modify: `.env`, `*.sqlite3`, `reader.db`, `.venv/`.
- **Lute is retired (Epic 8, 2026-07-21).** The user has fully switched to
  MbxRead. `translate_svc/main.py` (the old Lute-HTML tooltip page) is
  deleted; `start.ps1` now launches only MbxRead. `%LOCALAPPDATA%\Lute3`
  (the user's old Lute reading history/database) was deliberately left
  untouched — it's their data, not ours to delete, and nothing in this repo
  depends on it.
- Tests must pass offline with no API keys: mock DeepL/Claude/krdict/AnkiConnect HTTP,
  temp sqlite per test.
- The new server runs on port **8002** (5001/8001 belong to the legacy setup; 8000 is
  taken on this machine by an unrelated Android app's Docker-based sync service).
