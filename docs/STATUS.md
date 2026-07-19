# Project status — read this first, update it last

Executors: pick the first epic below that isn't `[x]`, do it per `docs/SPEC.md`, run the
full test suite, commit (`Epic N: <summary>`), then update this file (and ARCHITECTURE.md /
DECISIONS.md if reality diverged from the spec) in that same commit.

## Epic checklist

- [ ] **Epic 0 — Repo, scaffolding, docs** — *partially done by the planning session
  (2026-07-19): git repo initialized, `.gitignore`, `docs/` (SPEC/STATUS/DECISIONS),
  `CLAUDE.md`, initial commit. Remaining: `requirements.txt`, install kiwipiepy+pytest,
  `server/` skeleton with `/api/health` + `db.py` schema, `docs/ARCHITECTURE.md` (copy
  SPEC sections 3–8), smoke tests.*
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
