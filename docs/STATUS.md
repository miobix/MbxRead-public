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
- [x] Epic 1 — Tokenizer (kiwipiepy wrapper + table-driven tests) — done (2026-07-21).
  `server/tokenizer.py` implements the section-6 rule order exactly. One deviation
  found during implementation: kiwi tags irregular-verb stems with a suffixed subtag
  (`VV-R`, `VV-I`, `VA-I`, …) rather than the bare `VV`/`VA`/`VX` the spec examples
  show, so rule 2's match uses `tag.startswith(("VV","VA","VX"))`; `pos` is still
  reported as the literal kiwi tag (e.g. `VV-R`), which is a superset of what the
  spec's examples imply, not a behavior change. All 9 table-driven conjugation cases
  pass; offsets round-trip; multi-sentence and latin/digit/punctuation-mixed text
  handled without crashing.
- [x] Epic 2 — Books & pages API — done (2026-07-21). `server/paging.py`
  (`split_pages`, sentence/newline-aware, falls back to an oversized single page
  rather than ever cutting mid-sentence) and `server/routes/books.py` (full CRUD +
  `GET /api/books/{id}/pages/{n}` returning `content/tokens/terms`, wired into
  `main.py`). `db.get_db` added as a FastAPI request dependency yielding a
  per-request `sqlite3.Connection` from `app.state.db_path`. 43/43 tests green (16
  new: paging edge cases, multi-page splitting, page payload shape, terms join,
  current_page/title patch, cascade delete, 404s). Manual check: POSTed a Korean
  story via a live `uvicorn` instance, GET page 1 returned correct token lemmas
  (입다, 나가다, 좋다, 가다) with offsets round-tripping.
- [x] Epic 3 — Terms & translate APIs — done (2026-07-21). `server/routes/terms.py`
  (full CRUD, 409 on duplicate/renamed-into-duplicate lemma, dirty-flag rule exactly
  as spec'd: only `translation/notes/deck/sentence` changes mark `anki_dirty=1`, and
  only once `anki_note_id` is set — lemma/status edits never dirty). `server/routes/
  translate.py` wraps `translate_svc.translators.translate` (502 + `{"error": ...}`
  on `TranslationError`) and `translate_svc.krdict.lookup`. 62/62 tests green (19
  new). Tests mock at the `server.routes.translate` module boundary (not `httpx`),
  so the real `translate_cache.sqlite3` / `.env` are never touched — confirmed
  neither file exists after a full test run.
  **Manual accept check closed (2026-07-21):** user added a real `.env`
  (`TRANSLATOR=deepl`, `DEEPL_API_KEY` set, no `ANTHROPIC_API_KEY`/`KRDICT_API_KEY`).
  Verified against a live `uvicorn` instance: `POST /api/translate {"text":"사랑"}` →
  `{"translation":"Love","backend":"deepl","cached":false}`; `GET /api/dict?word=사랑`
  → `[]` (krdict.lookup degrades gracefully with no key, per translate_svc design —
  not a bug).
- [ ] Epic 4 — Frontend: scaffold, book list, reader rendering
- [ ] Epic 5 — Tooltip flow (tap → translate → edit → save)
- [ ] Epic 6 — Anki sync (AnkiConnect add/update)
- [ ] Epic 7 — Terms & settings pages, polish
- [ ] Epic 8 — Ops & Lute retirement

## Known issues / deviations

- **2026-07-21 — server port changed from 8000 to 8002.** The user's Android app
  syncs content via a Docker-based service already bound to `localhost:8000` on this
  machine. korean-reader now runs on **8002** instead (5001/8001 still reserved for
  the legacy Lute setup). `CLAUDE.md`, `docs/SPEC.md`, and `docs/ARCHITECTURE.md`
  updated throughout; see `docs/DECISIONS.md`. No app code hardcoded the port (it's
  only ever passed via `uvicorn --port` / will be in `next.config`'s dev rewrite), so
  this was a docs-only change as of Epic 3. Epic 0/2/3 entries below still say 8000
  in their manual-check notes because that's what was true when those epics shipped
  — historically accurate, not a live instruction.

## Notes for the next session

- The old Lute setup (ports 5001/8001 via `start.ps1`) stays live and untouched until Epic 8.
- Tests must pass offline: mock DeepL/Claude/krdict/AnkiConnect; temp sqlite per test.
- Next up: Epic 4 — scaffold `web/` (Next.js, TS, Tailwind, App Router,
  `output:'export'`), book list + add-book modal, `/read/[bookId]` rendering pages
  from token offsets with learning-term highlights + pagination. `npm run build`
  must be clean from this epic on. Needs Node.js — check it's installed before
  starting; if missing, stop and ask the user to install Node LTS per SPEC §3.
- When manually smoke-testing with a live `uvicorn` process on Windows, background
  `&` jobs can outlive the Bash tool call that started them and squat on the port;
  check `netstat -ano | grep :8002` and `taskkill //PID <pid> //F` if a fresh
  `uvicorn` run fails to bind. (Port 8000 belongs to an unrelated Docker service on
  this machine — don't use it, don't kill things listening there without checking
  what they are first.)
