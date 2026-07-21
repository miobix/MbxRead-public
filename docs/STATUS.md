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
- [x] Epic 4 — Frontend: scaffold, book list, reader rendering — done (2026-07-21).
  `web/` scaffolded with `create-next-app` (Next 16.2.10, React 19, TypeScript,
  Tailwind v4, App Router, `--no-src-dir`). Removed the default `next/font/google`
  usage (Geist) from `app/layout.tsx` to avoid an external-network dependency at
  build time — system font stack instead. `lib/api.ts` is a small typed fetch
  wrapper (`/api` same-origin). `app/page.tsx`: book list + inline add-book modal
  (paste-textarea or `.txt` upload) → `POST /api/books`. `app/read/page.tsx`:
  renders `content` as spans from `tokens` offsets, highlights tokens whose lemma is
  a saved `learning` term, prev/next pagination that `PATCH`es `current_page`.
  `server/main.py`'s `web/out` static mount (wired since Epic 0) now actually serves
  something. `npm run build` and `npm run lint` both clean; `pytest` 62/62 still
  green (no server code changed).
  **Two deviations from SPEC §7, logged in DECISIONS.md:** (1) the reader route is
  `/read/?id=<bookId>` (query string), not `/read/[bookId]` — `output: 'export'`
  requires dynamic segments to be enumerable via `generateStaticParams()` at build
  time, which is impossible for book IDs created at runtime. (2) `next.config.ts`
  sets `trailingSlash: true` so static export emits `out/read/index.html` (which
  Starlette's `StaticFiles(html=True)` can actually resolve for `GET /read/`)
  instead of a flat `out/read.html` (which it can't).
  **Not verified — no browser tooling available in this environment:** the actual
  rendered page, the highlight CSS, and phone-width usability were not visually
  checked. What *was* verified: the page-payload → highlight-condition data
  contract end-to-end (created a book via the API, hand-inserted a `learning` term
  for 입다, confirmed `GET .../pages/1` marks the correct token — same condition
  `read/page.tsx` checks client-side), and that FastAPI serves the static export
  and `/api/*` routes correctly side by side (`GET /`, `GET /read/`, `GET
  /api/books` all returned correctly through one running server). The user should
  do a real visual/touch pass before relying on this epic being fully done.
- [x] Epic 5 — Tooltip flow (tap → translate → edit → save) — done (2026-07-21).
  `web/app/read/TokenPopover.tsx` (new) + `web/lib/sentence.ts` (new) +
  `web/app/read/page.tsx` (tap/selection delegation wired in). Full flow: tap an
  unlearned token or drag-select a phrase → popover with editable lemma, Translate
  / Dictionary / Translate-sentence, editable translation textarea, deck select →
  Save (`POST` new or `PATCH` existing, fixed at popover-open time); tap an
  already-saved token → same popover pre-filled, plus Mark known / Ignore /
  Delete. Client-side `page.terms` map updates from the API response on save —
  no refetch — so highlights refresh instantly.
  `npm run build` and `npm run lint` both clean.
  **Interim simplification:** deck `<select>` is hardcoded to `["Korean"]`
  (matches SPEC §4's own default) since `GET /api/settings` doesn't exist until
  Epic 7 — `TODO(Epic 7)` comment left in `TokenPopover.tsx`.
  **Verified without a browser** (still none available in this environment): every
  request/response shape the popover depends on, against a live server with real
  `.env` keys — created a term via the exact payload `Save` sends, confirmed the
  saved lemma's token highlights on the next page fetch; renamed the term's lemma
  (simulating a hand-correction) and confirmed *no* token highlights afterward,
  since no token's own tokenizer-lemma matches the new string — this is correct
  per SPEC's literal `token.lemma in terms` rule, not a bug (see DECISIONS.md);
  exercised mark-known/mark-ignored/delete; hit a real 409 on a duplicate lemma and
  confirmed the exact error string the popover would display. Also independently
  verified `lib/sentence.ts`'s extraction logic against the live page content in
  Python (mirroring the same regex) — correct sentence boundaries. **Not verified:
  actual popover rendering/positioning, touch drag-selection, and general
  usability** — needs a real visual/touch pass.
- [x] Epic 6 — Anki sync (AnkiConnect add/update) — done (2026-07-21).
  `server/anki.py` (single `_invoke()` choke point for every AnkiConnect call —
  `ping`, `create_deck`, `add_note`, `update_note_fields` — raising `AnkiError` on
  transport failure or a non-null `error` in the response body) + `server/routes/
  anki_sync.py` (`POST /api/anki/sync`: 503 if Anki unreachable; creates any decks
  referenced by pending terms; adds `status='learning' AND anki_note_id IS NULL`
  terms via `addNote`; pushes `anki_dirty=1` terms via `updateNoteFields`; per-note
  failures land in `failed` and don't block the rest; returns
  `{added, updated, failed}`), wired into `main.py`. 68/68 tests green (6 new,
  mocking at the `anki` module boundary per existing convention, plus one patching
  `httpx.post` directly to cover `_invoke`'s transport-error branch).
  `web/app/terms/page.tsx` (new, bare-bones stub — just the Sync button + result
  toast, linked from the home page header) + `lib/api.ts`'s `syncAnki()`.
  `npm run build`/`lint` both clean.
  **Deviation:** the full `/terms` table (filter/inline-edit/delete) stayed
  Epic 7 scope rather than being pulled forward, per the interim-call pattern from
  Epic 5's deck-select decision — see `docs/DECISIONS.md`. Also: empty `deck`
  values (schema default `''`) fall back to Anki's literal `"Default"` deck since
  AnkiConnect requires a real deck name.
  **Manual accept check closed (2026-07-21):** user tested against a live Anki
  desktop with AnkiConnect (no CORS config changes needed, as expected — that
  allowlist only applies to browser-originated requests). Confirmed: new notes
  land in the assigned deck on Sync; editing a synced term and re-syncing
  updates the same note in place, no duplicate; all Anki functionalities user
  tested came back working. `ANKI.md` (repo root) written as the user-facing
  how-to (setup, daily workflow, field mapping, troubleshooting).
- [x] Epic 7 — Terms & settings pages, polish — done (2026-07-21).
  `server/routes/settings.py` (new): `GET/PUT /api/settings` — `{decks,
  default_deck, translator_backend}`, each stored as its own JSON-encoded row in
  the `settings` table, merged over hardcoded defaults so a fresh DB still
  returns a complete dict; `PUT` accepts any subset and never clobbers keys it
  didn't mention. `web/app/settings/page.tsx` (new): deck list editor (add/
  remove), default-deck select, translator-backend select — each edit `PUT`s
  immediately. `web/app/terms/page.tsx` replaced Epic 6's Sync-only stub with
  the real page: status/deck/search filters (debounced against
  `GET /api/terms?status=&deck=&q=`), tap-a-row-to-edit (translation/notes/
  deck/status inline, Save/Delete), Sync button + toast carried over unchanged.
  `web/app/read/TokenPopover.tsx`'s hardcoded `DECKS = ["Korean"]` (the Epic 5
  interim call) is gone — decks/default deck/translator backend now come from
  `GET /api/settings`, fetched once by `read/page.tsx` and passed down as props.
  72/72 tests green (10 new: settings defaults, partial/full `PUT`, persistence
  across `GET`). `npm run build`/`lint` both clean.
  **Not verified in a browser** (still no browser tooling in this environment):
  the acceptance criterion "decks created in settings appear in the
  save-popover select" was verified at the code/data-contract level (props
  wiring traced end-to-end) and via the passing test suite, not by actually
  watching it happen on a phone. Given Epics 4-6 all had real bugs surface only
  once the user tried them by hand, **do a real pass on this epic too**: add a
  deck in `/settings`, confirm it shows up in the reader's Save popover deck
  `<select>` and in `/terms`'s filter dropdown; change the default deck and
  confirm a *new* term saved via the popover defaults to it; flip the
  translator backend and confirm Translate in the popover actually uses the
  new one (compare output against the old backend, or check DeepL vs Claude's
  differing response shape/style); try `/terms`'s filters and inline edit
  (lemma/translation/notes/deck/status, including a lemma rename that should
  409 against an existing lemma — confirm the term list updates and Anki
  dirty-flag rules still hold) and delete a term.
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
- Next up: Epic 7 — Terms & settings pages, polish. `web/app/terms/page.tsx`
  currently exists only as Epic 6's bare-bones Sync-button stub; replace its
  contents with the real filterable/editable table (the Sync button/logic can
  move in as-is). Also build `GET/PUT /api/settings` (`server/routes/settings.py`,
  not yet created) and swap `TokenPopover.tsx`'s hardcoded `DECKS = ["Korean"]`
  for real settings-backed deck list + default deck (see the Epic 5 deck-select
  and Epic 6 `/terms`-stub entries in `docs/DECISIONS.md`).
- **Epic 6's Anki sync is verified against a live Anki desktop** (2026-07-21,
  by the user) — new-note add, in-place update on re-sync, deck assignment all
  confirmed working. `ANKI.md` at the repo root is the user-facing how-to.
- **Visual/touch pass over Epics 4-5 done (2026-07-21), by the user on a real
  phone/browser** (no browser automation tool has been available in this
  environment). Result: book list, reader rendering, pagination (incl. returning
  to `current_page`), tap-to-translate-and-save, per-token highlighting, and
  mark-known/ignore/delete all confirmed working. Three bugs found and fixed
  same-day — see the "Bugs found during the Epic 4/5 manual visual/touch pass"
  entry in `docs/DECISIONS.md` (sqlite cross-thread `check_same_thread` crash on
  first request; saved phrase/sentence terms not recoverable on reselect; redundant
  non-functional-looking "Translate sentence" button removed). Phrase/sentence
  *highlighting* still intentionally doesn't light up — that's the pre-existing,
  correct-per-spec per-token-lemma rule, not a bug.
- When manually smoke-testing with a live `uvicorn` process on Windows, background
  `&` jobs can outlive the Bash tool call that started them and squat on the port;
  check `netstat -ano | grep :8002` and `taskkill //PID <pid> //F` if a fresh
  `uvicorn` run fails to bind. (Port 8000 belongs to an unrelated Docker service on
  this machine — don't use it, don't kill things listening there without checking
  what they are first.)
