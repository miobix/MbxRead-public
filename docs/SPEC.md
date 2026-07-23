# Korean Reader — full rebuild spec (handover plan)

**Audience:** this plan will be executed epic-by-epic by other models (Sonnet). Each epic is self-contained, has tests and acceptance criteria, and ends with a git commit plus a design-doc update. Read "Executor conventions" before starting any epic.

## 1. Context

The user reads Korean short stories/subtitles, taps unknown words, translates them, enriches the translation by hand, and studies them in Anki (AnkiDroid via AnkiWeb sync). A Lute-v3-based setup validated the concept but conflicts with three hard requirements:

1. **Lemma-based terms.** Lute keys terms by surface text (입고). The user wants to save the dictionary form (입다) while *all* inflections (입고, 입은, 입었어요…) highlight in every text. Requires Korean morphological analysis (kiwipiepy).
2. **Deliberate interaction.** No all-words-clickable-by-default. Flow: tap word → tooltip → explicitly press Translate → edit/enrich translation → save. Only saved *learning* words stay highlighted.
3. **Hand-correctable everything.** Both the translation and the detected lemma are editable at save time (the analyzer will sometimes guess wrong; the user wants final say).

Agreed decisions:
- **Hosting/remote access:** app runs on the user's Windows PC; phone access via **Tailscale** (user installs; no auth code in the app).
- **Anki:** pool model via **AnkiConnect**. Words accumulate in the app, each assigned a deck. A manual "Sync" (PC, Anki open) bulk-adds new notes and **updates** previously synced ones via stored `anki_note_id` — never duplicates.
- **Statuses:** `learning` (highlighted, synced), `known` (no highlight, not synced), `ignored`.
- **Frontend: Next.js** (App Router, TypeScript, Tailwind). Static export served by FastAPI in production — one uvicorn process. `next dev` during development.
- Lute stays installed and usable until the new app reaches parity (Epic 8 retires it).

## 2. Existing code (reuse, do not rewrite)

Repo root: `C:\Users\<user>\PycharmProjects\korean-reader` (venv at `.venv`, Python 3.10, Windows).

| Path | Role | Action |
|---|---|---|
| `translate_svc/translators.py` | DeepL/Claude translation with cache, `translate(text, backend) -> (result, backend, cached)` | import as library |
| `translate_svc/cache.py` | sqlite translation cache (`translate_cache.sqlite3`) | as-is |
| `translate_svc/krdict.py` | krdict dictionary lookup returning entry dicts | import as library |
| `translate_svc/config.py` | loads `.env` (TRANSLATOR, DEEPL_API_KEY, ANTHROPIC_API_KEY, KRDICT_API_KEY) | extend if needed |
| `translate_svc/main.py` | HTML tooltip page for Lute | keep until Epic 8, then delete |
| `import_tools/yt_subs.py`, `import_tools/pdf_text.py` | produce cleaned .txt from YouTube/PDF | keep as CLI |
| `start.ps1` | launches Lute (:5001) + translator (:8001) | replaced in Epic 8 |

## 3. Architecture

```
korean-reader/
  server/                  FastAPI app, port 8002
    __init__.py
    main.py                app factory; mounts /api routers; serves web/out statically at /
    db.py                  sqlite (reader.db): connection, schema init, query helpers
    tokenizer.py           kiwipiepy wrapper: text -> eojeol tokens with lemma
    anki.py                AnkiConnect client (http://localhost:8765)
    routes/
      books.py  terms.py  translate.py  anki_sync.py  settings.py
  server/tests/            pytest suite
  translate_svc/           existing, used as a library
  web/                     Next.js app (TypeScript, Tailwind, output: 'export')
  import_tools/            existing
  docs/                    living design docs (see Executor conventions)
  requirements.txt         direct Python deps
  start.ps1                (Epic 8) single-server launcher
  reader.db                app data — never commit
```

- New Python deps: `kiwipiepy` (no system deps, works on Windows), plus existing `fastapi`, `uvicorn`, `httpx` already in `.venv`.
- Port **8002** (Lute keeps 5001 and translate_svc 8001 during the transition; 8000 is
  reserved on this machine by an unrelated Android app's Docker sync service — no clashes).
- Node.js required for the `web/` build. If Node is missing on the machine, tell the user to install Node LTS and stop (`needs input`), don't work around it.

## 4. Data model (`reader.db`, created by `server/db.py` on startup)

```sql
CREATE TABLE IF NOT EXISTS books (
  id INTEGER PRIMARY KEY,
  title TEXT NOT NULL,
  source TEXT NOT NULL DEFAULT 'paste',          -- paste | txt | yt | pdf
  current_page INTEGER NOT NULL DEFAULT 1,
  created TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS pages (
  book_id INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
  page_no INTEGER NOT NULL,                      -- 1-based
  content TEXT NOT NULL,
  PRIMARY KEY (book_id, page_no)
);
CREATE TABLE IF NOT EXISTS terms (
  id INTEGER PRIMARY KEY,
  lemma TEXT NOT NULL UNIQUE,                    -- dictionary form; may be a multi-word phrase
  translation TEXT NOT NULL DEFAULT '',
  notes TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'learning'
    CHECK (status IN ('learning','known','ignored')),
  deck TEXT NOT NULL DEFAULT '',
  sentence TEXT NOT NULL DEFAULT '',             -- example sentence captured at save time
  anki_note_id INTEGER,                          -- NULL until first sync
  anki_dirty INTEGER NOT NULL DEFAULT 0,         -- 1 = edited since last sync
  created TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
```

Foreign keys ON (`PRAGMA foreign_keys=ON` per connection). Page splitting at import: split text into pages of ≤ ~1500 chars, breaking only at sentence ends (`.` `?` `!` `…` `다.` patterns / newlines); never split mid-sentence. Settings keys used: `decks` (JSON array of deck names, default `["Korean"]`), `default_deck`, `translator_backend`.

## 5. API contract (all under `/api`, JSON)

| Method & path | Request | Response |
|---|---|---|
| GET `/api/health` | – | `{ok, version}` |
| GET `/api/books` | – | `[{id,title,source,current_page,page_count,created}]` |
| POST `/api/books` | `{title, text, source?}` | created book (splits pages) |
| GET `/api/books/{id}` | – | `{id,title,current_page,page_count}` |
| PATCH `/api/books/{id}` | `{current_page?, title?}` | updated book |
| DELETE `/api/books/{id}` | – | 204 |
| GET `/api/books/{id}/pages/{n}` | – | `{page_no, page_count, content, tokens, terms}` (see below) |
| GET `/api/terms` | `?status=&deck=&q=` | `[term]` |
| POST `/api/terms` | `{lemma, translation, notes?, status?, deck?, sentence?}` | created term (409 if lemma exists) |
| PATCH `/api/terms/{id}` | any editable fields | updated term; sets `anki_dirty=1` if `translation/notes/deck/sentence` changed and `anki_note_id` is set; bumps `updated` |
| DELETE `/api/terms/{id}` | – | 204 |
| POST `/api/translate` | `{text, backend?}` | `{translation, backend, cached}` (502 + `{error}` on TranslationError) |
| GET `/api/dict?word=…` | – | krdict entries as JSON list |
| POST `/api/anki/sync` | – | `{added, updated, failed:[{lemma, error}]}` |
| GET/PUT `/api/settings` | PUT: `{key: value, …}` | full settings dict |

**Page payload** (the core endpoint):
```json
{
  "page_no": 3, "page_count": 12,
  "content": "그는 옷을 입고 나갔다. …",
  "tokens": [ {"s": 7, "e": 9, "surface": "입고", "lemma": "입다", "pos": "VV"}, … ],
  "terms":  { "입다": {"id": 5, "translation": "to wear", "status": "learning", "deck": "Korean"}, … }
}
```
`tokens` covers every eojeol with a resolvable lemma (`s`/`e` are char offsets into `content`). `terms` contains only saved terms whose lemma appears in this page's tokens. The frontend renders spans from offsets and applies the highlight class when `token.lemma in terms && status === 'learning'`.

## 6. Tokenizer spec (`server/tokenizer.py`)

Use `kiwipiepy.Kiwi()` (module-level singleton — model load is slow). `kiwi.tokenize(text)` returns morphemes with `form`, `tag`, `start`, `len`.

Algorithm — group morphemes into **eojeols** (runs of non-whitespace in the original text), then pick the eojeol's *primary* morpheme:

1. **하다-derivations first:** noun (`NNG/NNP/XR`) immediately followed by `XSV`/`XSA` → lemma = noun-form + `하다` (공부했어요 → 공부하다), pos = `VV`/`VA`.
2. Else first morpheme tagged `VV`, `VA`, or `VX` → lemma = form + `다` (입고 → 입다, 갔다 → 가다, 예뻐요 → 예쁘다).
3. Else first morpheme tagged `NNG NNP NNB NR NP MAG MAJ IC` → lemma = form (학교에 → 학교, 사람들이 → 사람).
4. Else (eojeol is only particles/endings/symbols/numbers) → emit no token for it.

Return `list[Token]` with `surface` (full eojeol text), `s`, `e`, `lemma`, `pos` (tag of chosen morpheme). Wrong guesses are acceptable — the UI lets the user edit the lemma before saving.

**Table-driven tests (Epic 1):** 입고→입다, 입었어요→입다, 했어요→하다, 공부했어요→공부하다, 학교에→학교, 갔다→가다, 예뻐요→예쁘다, 사람들이→사람, 학생이에요→학생, plus: offsets reconstruct surfaces exactly (`text[s:e] == surface`), multi-sentence text, text with latin/digits/punctuation mixed in.

## 7. Frontend spec (`web/`)

Next.js (latest stable), App Router, TypeScript, Tailwind CSS. **Mobile-first** — primary device is a phone. Clean, modern, uncluttered (the user found Jinja UIs "ugly and clunky"; visual quality matters). Config: `output: 'export'`; dev uses `next.config` rewrites `/api/* → http://localhost:8002/api/*`.

Routes:
- `/` — book list (title, progress `current_page/page_count`), "Add book" modal: title + paste-textarea or `.txt` upload.
- `/read/[bookId]` — the reader:
  - Renders `content` as spans using `tokens` offsets. Base text plain; **only** tokens whose lemma is in `terms` with status `learning` get a subtle highlight. No other visual affordance.
  - **Tap a token** → popover anchored to the word: surface, lemma in an **editable input**, buttons **Translate**, **Dictionary**, **Translate sentence**. Translate → `POST /api/translate` → result fills an **editable textarea**; user enriches freely; deck `<select>` (from settings, default `default_deck`); **Save** → `POST /api/terms` with the (possibly edited) lemma, textarea content, current sentence (extracted around the tap point). On save, every span on the page with that lemma updates instantly (client-side term map).
  - **Tap a highlighted token** → same popover pre-filled from the saved term; Save → `PATCH`; extra actions: mark known / ignore / delete.
  - **Text selection** (long-press drag) of a phrase → same popover with the raw selection as lemma.
  - Page prev/next; on page change `PATCH` `current_page`. Sentence extraction: from previous sentence-end to next sentence-end around the token.
- `/terms` — table (filter: status, deck, search), inline edit, delete, "**Sync to Anki**" button showing `{added, updated, failed}` toast.
- `/settings` — deck list editor, default deck, translator backend (deepl/claude).

Keep dependencies minimal: Next + Tailwind only; no state library (React context/props suffice), no component kit. Small shared `lib/api.ts` fetch wrapper.

## 8. Anki sync spec (`server/anki.py` + `routes/anki_sync.py`)

AnkiConnect at `http://localhost:8765` (POST JSON `{action, version: 6, params}`); Anki desktop with the AnkiConnect add-on (code 2055492159) is already installed from the Lute setup.

Sync algorithm:
1. `version` ping — if unreachable, return 503 `{error: "Anki is not running (or AnkiConnect missing)"}`.
2. For each deck referenced by pending terms: `createDeck` (idempotent).
3. New: terms `status='learning' AND anki_note_id IS NULL` → `addNote` (`modelName: "Basic"`, Front = lemma, Back = translation + `<br><br><i>sentence</i>` when present, tags `["korean-reader"]`, `options.allowDuplicate: false`). Store returned id, clear dirty. On per-note error (e.g. duplicate) record in `failed`, continue.
4. Dirty: terms `anki_dirty=1 AND anki_note_id NOT NULL` → `updateNoteFields` with the same field rendering; on success clear `anki_dirty`.
5. Return counts. Never delete Anki notes; `known`/`ignored` terms are simply not synced (existing notes left alone).

Tests: mock the AnkiConnect HTTP layer (monkeypatch `httpx.post`); cover add-new, update-dirty, per-note failure isolation, Anki-down 503.

## 9. Executor conventions (apply to EVERY epic)

- **Environment:** Windows, PowerShell. Python: `.venv\Scripts\python.exe` (never system python). Install deps with `.venv\Scripts\pip install <pkg>` **and** add them to `requirements.txt`.
- **Git:** repo is initialized in Epic 0. Work directly on `main` (single-user project, no remote initially). At minimum **one commit at the end of each epic**, message `Epic N: <what shipped>`. Commit only when the epic's tests pass. Never commit `.env`, `*.sqlite3`, `reader.db`, `.venv/`, `web/node_modules|.next|out`.
- **Design docs (update in the same end-of-epic commit):**
  - `docs/ARCHITECTURE.md` — created in Epic 0 from sections 3–8 of this plan; **amend whenever reality diverges from the spec** (changed endpoint shape, extra table column, different heuristic…). It must always describe the code as it is.
  - `docs/STATUS.md` — epic checklist with one line per epic: done/in-progress + any deviations or known issues. This is the handover state between models: **read it first, update it last.**
  - `docs/DECISIONS.md` — append-only log: date, decision, why (e.g. "chose X because kiwi tag Y behaves…").
- **Tests:** pytest in `server/tests/`, run with `.venv\Scripts\python.exe -m pytest server/tests -q`. Every epic's acceptance criteria include its tests passing plus the whole existing suite. Use a temp-file sqlite DB per test (fixture overriding the DB path); never touch the real `reader.db` or `translate_cache.sqlite3` from tests. Mock all external HTTP (DeepL/Claude/krdict/AnkiConnect) — tests must pass offline with no API keys.
- **Frontend checks:** from Epic 4 on, `npm run build` in `web/` must succeed before the epic commit (this covers type-checking).
- **Don't touch:** the Lute install, `%LOCALAPPDATA%\Lute3`, `translate_cache.sqlite3` contents, `.env`. Do not modify `translate_svc/` behavior before Epic 8 (Lute still uses it live on :8001).
- If genuinely blocked (missing Node, missing API key needed to verify something manual), state exactly what's needed and stop rather than guessing around it.

## 10. Epics

### Epic 0 — Repo, scaffolding, docs
Init git in `korean-reader` (no repo exists); `.gitignore` (`.venv/`, `.env`, `*.sqlite3`, `reader.db`, `__pycache__/`, `web/node_modules/`, `web/.next/`, `web/out/`); initial commit of existing files. Create `requirements.txt` (direct deps: fastapi, uvicorn, httpx, python-dotenv if used by config, kiwipiepy — check `translate_svc/config.py` for what it actually imports). Install `kiwipiepy` + `pytest`. Create `server/` package skeleton with `main.py` exposing `GET /api/health`, `db.py` creating the section-4 schema, empty `routes/`. Create `docs/ARCHITECTURE.md` (copy of sections 3–8), `docs/STATUS.md` (epic checklist), `docs/DECISIONS.md`. Smoke test: health endpoint 200 via TestClient; schema creates on a temp DB.
**Accept:** `pytest` green; `git log` shows init + epic commits; app boots with `uvicorn server.main:app --port 8002`.

### Epic 1 — Tokenizer
`server/tokenizer.py` per section 6, plus the full table-driven test set (section 6) in `server/tests/test_tokenizer.py`.
**Accept:** all listed conjugation cases pass; offsets round-trip (`text[s:e]==surface`); a wrong-but-present lemma is acceptable, a crash or missing offsets is not.

### Epic 2 — Books & pages API
`routes/books.py`: CRUD per section 5; page-splitting util (section 4 rules) in `db.py` or `server/paging.py`; page endpoint returning `content + tokens + terms` (tokens via Epic 1; terms join per section 5). Tests: create book from multi-page text, page boundaries never split sentences, page payload shape, current_page patch, cascade delete.
**Accept:** tests green; manual: POST a Korean short story, GET page 1 shows tokens with sensible lemmas.

### Epic 3 — Terms & translate APIs
`routes/terms.py` (CRUD, unique-lemma 409, dirty-flag rule on PATCH) and `routes/translate.py` (`/api/translate` wrapping `translate_svc.translators.translate`, `/api/dict` wrapping `translate_svc.krdict.lookup`). Tests: terms CRUD + dirty-flag transitions (edit before first sync → stays clean; after note_id set → dirty=1); translate route with monkeypatched backends incl. TranslationError → 502.
**Accept:** tests green; with real `.env` keys, `POST /api/translate {"text":"사랑"}` returns a translation (manual check).

### Epic 4 — Frontend: scaffold, book list, reader rendering
Scaffold `web/` (`create-next-app` — TypeScript, Tailwind, App Router, no src-dir preference left to executor; `output:'export'`; dev rewrite `/api`→8002). Build `/` (book list + add-book modal with paste/.txt upload) and `/read/[bookId]` rendering pages from token offsets with learning-term highlights and pagination + current_page persistence. Wire FastAPI to serve `web/out` at `/` when the directory exists. No tooltip yet.
**Accept:** `npm run build` clean; served at :8002 the story renders, saved learning lemmas (insert one via API by hand) highlight all their inflections; usable on a phone-width viewport.

### Epic 5 — Tooltip flow (the heart of the app)
Popover per section 7: tap → lemma (editable) → Translate/Dictionary/Translate-sentence → editable textarea → deck select → Save; tap-highlighted → edit/mark-known/ignore/delete; phrase selection; sentence extraction. Instant client-side highlight refresh on save.
**Accept:** `npm run build` clean; manual E2E on the test story: tap 입고 → 입다 offered → translate → enrich text → save → every 입다-inflection highlights; hand-correct a wrong lemma before save; edit an existing term.

### Epic 6 — Anki sync
`server/anki.py` + `routes/anki_sync.py` + Sync button on `/terms` per section 8. Tests per section 8 (mocked AnkiConnect).
**Accept:** tests green; manual with Anki open: sync creates notes in the assigned deck; edit a synced term → sync updates the same note (verify in Anki browser, no duplicate); Anki closed → clean 503 message in UI.

### Epic 7 — Terms & settings pages, polish
`/terms` (filters, inline edit, delete, sync button+toast) and `/settings` (deck list, default deck, backend). Backend `routes/settings.py`. Empty states, loading states, error toasts throughout. Tests for settings API.
**Accept:** build + tests green; decks created in settings appear in the save-popover select.

### Epic 8 — Ops & Lute retirement
Rewrite `start.ps1`: build `web/` if stale, launch single uvicorn `server.main:app --host 0.0.0.0 --port 8002`, open browser. Add Windows-Firewall note + Tailscale steps to README (install Tailscale on PC & phone, access `http://<magicdns-name>:8002`). Rewrite `README.md` for the new app (keep import_tools usage docs). Delete `translate_svc/main.py`'s Lute-HTML role only after confirming the user has stopped using Lute — leave a note in STATUS.md and keep it if unconfirmed. Final docs pass.
**Accept:** fresh `start.ps1` run serves the full app on :8002 from a cold start; README accurate; STATUS.md marks all epics done.

### Epic 9 — Difficulty scorer (Cycle 2)
Personal-coverage difficulty: score any text against the user's own vocabulary before committing to it. `server/difficulty.py` — `score_text(text, known)` → `{coverage, new_lemmas, total_lemmas, new_per_page}` (coverage is `None` when no lemmas resolve; `new_per_page` normalizes by the reader's own `paging.split_pages` count) and `known_lemmas(conn)` (every saved term, all statuses). `routes/difficulty.py` — `POST /api/score` for ad-hoc candidate text. `routes/books.py` — `POST /api/books/{id}/score` caches `coverage`/`new_per_page`/`scored_at` onto the book row. `db.py` — idempotent additive-migration path (`_apply_migrations`) adds those three `books` columns so an existing `reader.db` upgrades in place. Frontend: "Check difficulty" in the add-book modal, a per-book score line + Score/re-score button, and an "Easiest unread" sort on `/`. Tests in `test_difficulty.py`.
**Accept:** `pytest` + `npm run build`/`lint` green; `POST /api/score {"text":…}` returns coverage + new-per-page; scoring a stored book caches onto its row and it sorts under "Easiest unread". *(The rest of Cycle 2 — Epics 10–16 — is tracked in `docs/STATUS.md`; per-epic specs get fleshed out when each is started.)*

**Backlog (explicitly out of scope, do not build):** Lute term migration script, auth for public deployment, always-on hosting off the PC, audio/TTS, spaced-repetition inside the app. *(Stats/reading-time tracking was here too, but was deliberately un-backlogged and built in Epic 16 — see docs/DECISIONS.md 2026-07-23 and the Epic 16 entry below.)*

### Epic 16 — Stats screen + UI makeover (Cycle 2)
Reading stats for accountability + sharing, plus a UI polish pass. **Term provenance:**
`terms.source_book_id`/`source_page` (nullable, forward-only) capture where a word was first
saved (reader passes both to `POST /api/terms`). **Reading log:** `page_reads` table
(`PRIMARY KEY(book_id,page_no)`, `INSERT OR IGNORE`) via `POST /api/reads`, pinged by the
reader only after a 5s visible-dwell gate so revisits/flick-throughs don't count. **Stats:**
`GET /api/stats` aggregates totals (words learning/known/total, books finished, this-week),
streak (union of word-save days + first-read-page days, local-time buckets), a 365-day
activity list, new-words-per-book (provenance join, reading order), and vocab depth by NIKL
grade + beginner %. **Page size:** `settings.page_size` (default 650) drives `split_pages` at
import; changing it re-paginates the library (position preserved by char offset, `page_reads`
cleared). Difficulty's `new_per_page` stays pinned to `split_pages`'s 1500 default so scores
don't drift. Frontend: `/stats` (hero tiles, activity heatmap, new-words-per-book line, vocab
depth bar, milestone badges — all hand-rolled SVG/CSS, no new deps), a page-size control in
`/settings`, a Stats nav link. Tests: `test_stats.py`, `test_reads.py`, plus `test_db.py`/
`test_settings.py` additions.
**Accept:** `pytest` + `npm run build`/`lint` green; saving a word from the reader records
its book/page; a page counts once after 5s and never on revisit; `GET /api/stats` returns
sane totals/streak/per-book; changing page size re-paginates and preserves position. *(Cold-
start + Tailscale go-live moves to a later epic.)*

### Epic 17 — Fetch automation, candidate retention, terminology pass (Cycle 2)

Planned 2026-07-23 (see `docs/DECISIONS.md`); not yet started. Scope, in order:

1. **Task Scheduler wiring.** New `scripts/fetch_feeds.ps1`: minimal script, `Invoke-RestMethod -Uri http://localhost:8002/api/feeds/fetch -Method Post`, appends the JSON response + a timestamp to `scripts/fetch_feeds.log` (plain append, no rotation — personal-app scale), exits non-zero on any exception so Task Scheduler's own run history shows failures. No new Python code — reuses the existing endpoint exactly as the Queue's manual "Fetch new candidates" button does. README gets a new section with the exact Task Scheduler steps (daily trigger, 24h interval per the user's choice, action = this script). **Assumption, confirmed by the user:** the server is expected to be up continuously (Tailscale-hosted), so hitting the API directly is sufficient — no standalone DB-only fetch path needed.
2. **Retention setting.** `server/routes/settings.py`: `DEFAULTS` gains `"candidate_retention_days": 7`; `SettingsPut` gains `candidate_retention_days: int | None = Field(default=None, ge=1, le=90)`. `/settings` page gets a numeric input for it, same one-PUT-per-edit pattern as every other settings field.
3. **Auto-expiry.** `server/routes/feeds.py`'s `fetch_feeds()`: before iterating feeds, run `UPDATE books SET status='discarded' WHERE status='candidate' AND created <= datetime('now', '-' || ? || ' days')` with the current `candidate_retention_days` (read via `routes/settings._read(conn)`), and report the affected row count as a new `"expired"` key in the response body. Runs unconditionally on every call — scheduled, manual whole-roster, or a single-`feed_id` retry — since it's cheap and idempotent; no reason to special-case any trigger path. Reuses the existing `status='discarded'` value exactly as-is (permanent — `idx_books_source_ref` stays blocked, matches the user's confirmed choice, **no new status enum value in this epic**). Age is measured off `books.created` (set by the schema default at insert time for every candidate), not `fetched` (currently NULL for feed-sourced candidates — `_insert_and_score`/`insert_book` calls from `routes/feeds.py` don't pass it; fixing that gap is optional cleanup, not required for this epic).
4. **Global last-fetch-attempt.** `DEFAULTS` gains `"last_fetch_attempt": None`. This key is **system-managed, not user-editable** — deliberately absent from `SettingsPut` (so a `PUT /api/settings` body can never overwrite it, extra/unknown fields are dropped by pydantic by default) — instead `fetch_feeds()` stamps it directly via `INSERT INTO settings ... ON CONFLICT DO UPDATE` at the very start of the call, before touching any feed, so even a run that errors out partway still records that an attempt happened. Frontend reads it from `GET /api/settings`; Epic 18 is where it actually gets displayed (on `/queue`), so this epic just needs it to round-trip correctly.
5. **Terminology pass.** Sweep `web/app/*.tsx` copy: replace "book(s)" as the umbrella/collection word with **"Library"** ("Your Library" on `/`, nav link text, "Library stats" heading on `/stats`, etc.) per the user's choice. The word **"Book" is reserved** for entries where `source` is `pdf` or `epub` specifically (e.g. a small "Book" label/badge on those rows — distinct from the source-type chips Epic 18 adds for the rest). **No schema/column/table renaming** — the `books` table, the `source` column values, and every API shape stay exactly as-is; this is copy-layer only, zero migration risk, and shouldn't touch any existing test (none currently assert on UI copy strings).

Tests: `test_feeds.py` gains expiry cases (a candidate seeded with an old `created` timestamp is discarded on the next fetch call; a recent one isn't; a custom `candidate_retention_days` value is respected; `last_fetch_attempt` is stamped even when every feed in the roster errors out). `test_settings.py` gains `candidate_retention_days` round-trip + its `ge=1,le=90` bounds, plus a case confirming a `PUT` body containing `last_fetch_attempt` is silently ignored rather than overwriting the system-stamped value.

**Accept:** `pytest` + `npm run build`/`lint` green. `PUT /api/settings {"candidate_retention_days": 3}` then a candidate whose `created` is seeded 4 days back gets discarded by the next `POST /api/feeds/fetch`; `GET /api/settings` reflects a fresh `last_fetch_attempt` after any fetch call, scheduled or manual. Manual: register the Task Scheduler entry per the new README section, confirm a triggered run updates `last_fetch_attempt`; skim the built UI for any remaining bare "book" wording that should read "Library" instead.

### Epic 18 — Queue browsing UX: cards, chips, sort/filter, length, source link, back-to-top (Cycle 2)

Planned 2026-07-23; not yet started. Depends on Epic 17 for `last_fetch_attempt` (display only — this epic doesn't need Epic 17's other pieces). Scope:

1. **Card/list toggle.** `/queue` gets a view-mode toggle (Cards | List) at the top, persisted in `localStorage` (`queueViewMode`), defaulting to Cards. Card: no image, title, source-type chip, existing personal + general difficulty lines (visually tightened for card width), the new length line, topic/tags line, Promote/Discard/Translate actions, and an "↗ Open source" link in the card header. List mode keeps today's row layout, just reads from the same data/state.
2. **Source-type chips.** New small shared piece (e.g. `web/lib/chips.tsx`): maps `source` → `{label, colorClasses}` — `yt` → "YouTube", `article` → "Article" (extend later if `pdf`/`epub`/other sources ever reach the queue; today only these two do). Plain Tailwind color classes, no new dependency. Per the user's choice, **one chip per source type** — no short/long split; length is its own separate line (point 3).
3. **Length stat.** `import_tools/yt_subs.fetch_subs()` extends its return to `(title, text, video_id, duration)`, reading `info["duration"]` (seconds) off the yt-dlp info dict already being read — real video length, not a transcript-based estimate. Every call site updates for the new 4-tuple: `routes/imports.py`'s `POST /api/import/youtube`, `routes/feeds.py`'s `_process_youtube`, and the `import_tools/yt_subs.py` CLI `__main__`. `books` gains two additive columns: `duration_seconds INTEGER` (NULL except for `yt`-sourced books) and `word_count INTEGER` (NULL until computed — set at insert time for every source by splitting the full joined text on whitespace, same "cache it once" pattern Epic 9 established for `coverage`/`new_per_page`). `GET /api/books` response includes both. Frontend shows "~1,200 words" for text sources or a formatted duration ("18 min") for `yt` — whichever field is non-NULL.
4. **Source link.** Card/list row header: "↗" link using the existing `source_url` column (already populated for every feed-sourced candidate since Epic 14/15), `target="_blank" rel="noopener noreferrer"`.
5. **Sort-by picker.** `/queue` gets a `<select>`: "Newest fetched" (default, `created` desc), "Easiest first" (by `coverage`/`general_coverage` desc, mirroring `/`'s existing "Easiest unread" comparator), "Shortest first" (ascending over a single derived "minutes to consume" number — `word_count/250` for text, `duration_seconds/60` for video; a standard reading-speed heuristic used only to make the *sort order* comparable across mixed source types, never shown to the user — displayed text always stays the exact word count or exact duration from point 3). All client-side over the already-fetched candidate list, no new query param, same pattern as the existing "Easiest unread" sort.
6. **Back-to-top button.** Small fixed floating button, appears once `window.scrollY` passes roughly two viewport heights, smooth-scrolls to top. Scoped to `/queue` only this epic (reusable later if wanted elsewhere).
7. **Last-fetch-attempt display.** One line at the top of `/queue`: "Last fetch attempt: <formatted last_fetch_attempt>" from `GET /api/settings` (Epic 17).

Tests: `test_imports.py` and `test_feeds.py` updated for `fetch_subs`'s new 4-tuple return, plus `duration_seconds`/`word_count` round-tripping through both the manual YouTube import route and the feed-fetch path; `test_db.py` gains migration-idempotency cases for the two new `books` columns.

**Accept:** `pytest` + `npm run build`/`lint` green. A real YouTube video pulled through `/api/feeds/fetch` shows its real (not estimated) duration; the card/list toggle survives a reload; "Shortest first" ranks a short article above a long video transcript; the back-to-top button appears and works after scrolling; a card's source link opens the original video/article in a new tab. **Not verified in a browser** until the owed manual pass this project has been carrying since Epic 4.

### Epic 19 — Promotion stats: what gets read vs. what doesn't (Cycle 2)

Planned 2026-07-23; not yet started. Depends on Epic 17 (touches the expiry `UPDATE` it adds) and reads more cleanly after Epic 18 (chips/labels this section's numbers refer back to), but has no hard code dependency on either beyond that one query edit. Scope:

1. **`feed_id` provenance.** `books` gains an additive `feed_id INTEGER` column (nullable, no FK — same soft-reference convention as `terms.source_book_id`). `routes/feeds.py`'s `_insert_and_score`/`insert_book` call sets it for every feed-sourced candidate; manual imports (`routes/imports.py`'s four importers) leave it NULL. This replaces relying on `tags=[feed["name"]]` as a join key back to a feed (fragile across feed renames) with a stable id.
2. **`discard_reason`.** Additive `discard_reason TEXT` column (nullable, `'user'` or `'expired'`, no CHECK — kept loose since it's informational, not a lifecycle gate like `status`). Two write sites: `routes/books.py`'s manual `PATCH status='discarded'` path sets `discard_reason='user'`; Epic 17's auto-expiry `UPDATE` (in `routes/feeds.py`) is **revisited by this epic** to also set `discard_reason='expired'` in the same statement. **Flagged judgment call for whoever implements this:** distinguishing "you actively rejected this" from "it aged out unread" is what makes the "what's NOT being promoted" stats meaningful (a pile of `expired` in one topic reads very differently from a pile of `user`-discarded), so this write-up recommends adding it — but if it's judged not worth the extra column, the epic can ship with everything lumped under plain `discarded` counts instead; note that call in `docs/DECISIONS.md` either way.
3. **Stats aggregation.** `GET /api/stats` (existing, Epic 16) gains a new top-level `curation` key: `{by_topic: [{topic, promoted, user_discarded, expired, pending}], by_feed: [{feed_id, feed_name, promoted, user_discarded, expired, pending}]}`, computed over `books` rows with `feed_id IS NOT NULL` — `promoted` = `status='library'`, `pending` = `status='candidate'`, the other two split `status='discarded'` by `discard_reason`.
4. **Frontend.** `/stats` gets a new section: two small breakdowns (by topic, by feed/channel name) of promoted vs. user-discarded vs. expired vs. still-pending counts. Hand-rolled SVG/CSS, no new npm dependency — same convention Epic 16 set.

Tests: `test_stats.py` gains curation-aggregation cases across multiple topics/feeds and all four buckets; `test_feeds.py`/`test_books.py` cover `feed_id` and `discard_reason` round-tripping at their respective write sites; `test_db.py` gains migration-idempotency cases for both new columns.

**Accept:** `pytest` + `npm run build`/`lint` green. Promoting, manually discarding, and letting a candidate expire across two different feeds/topics in a test produces the expected `by_topic`/`by_feed` counts in `GET /api/stats`; `/stats` renders the new section with no new dependency.

## 11. End-to-end verification (after Epic 8)

1. `start.ps1` → app on :8002. Import the user's test short story.
2. Tap 입고 → lemma 입다 → Translate → enrich the translation → Save → all inflections of 입다 highlighted; unknown words show no affordance until tapped.
3. Hand-correct a bad lemma guess during save; highlight follows the corrected lemma.
4. Anki open: Sync → notes in assigned decks; edit a term; Sync → same note updated, no duplicate; AnkiWeb sync carries them to AnkiDroid.
5. Phone via Tailscale (or LAN): full read-tap-translate-save flow works with touch.
