# Project status — read this first, update it last

Executors: pick the first epic below that isn't `[x]`, do it per `docs/SPEC.md`, run the
full test suite, commit (`Epic N: <summary>`), then update this file (and ARCHITECTURE.md /
DECISIONS.md if reality diverged from the spec) in that same commit.

## Epic checklist

- [x] **Epic 0 — Repo, scaffolding, docs** — done (2026-07-21). `.venv` created with
  Python 3.10 (`py -3.10 -m venv .venv`, required for kiwipiepy). `requirements.txt`
  pinned (fastapi, uvicorn, httpx, python-dotenv, kiwipiepy, pytest). `server/`
  skeleton: `main.py` (app factory `create_app(db_path=None)`, lifespan-based DB init
  so tests never touch real `reader.db`, `/api/health`, inert `web/out` static mount),
  `db.py` (section-4 schema + `get_connection`/`init_db`), empty `routes/` package.
  `docs/ARCHITECTURE.md` created (copy of SPEC §3–8, annotated with per-epic status).
  Smoke tests in `server/tests/` (health 200, schema creation, idempotent init, FK
  pragma) — all green. Manual check: `uvicorn server.main:app --port 8000` boots,
  `/api/health` returns `{"ok":true,"version":"0.1.0"}`.
- [ ] Epic 1 — Tokenizer (kiwipiepy wrapper + table-driven tests)
- [ ] Epic 2 — Books & pages API
- [ ] Epic 3 — Terms & translate APIs
- [ ] Epic 4 — Frontend: scaffold, book list, reader rendering
- [ ] Epic 5 — Tooltip flow (tap → translate → edit → save)
- [ ] Epic 6 — Anki sync (AnkiConnect add/update)
- [ ] Epic 7 — Terms & settings pages, polish
- [ ] Epic 8 — Ops & Lute retirement

## Known issues / deviations

(none yet)

## Notes for the next session

- The old Lute setup (ports 5001/8001 via `start.ps1`) stays live and untouched until Epic 8.
- Tests must pass offline: mock DeepL/Claude/krdict/AnkiConnect; temp sqlite per test.
- Next up: Epic 1 — `server/tokenizer.py` (kiwipiepy wrapper) + table-driven tests per
  SPEC §6. Run tests with `.venv\Scripts\python.exe -m pytest server/tests -q`.
