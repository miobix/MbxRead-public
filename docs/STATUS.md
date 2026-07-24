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
- [x] Epic 8 — Ops & Lute retirement — done (2026-07-21), docs/launcher only, not
  gone live yet (see below). User confirmed they've fully switched off Lute, so
  `translate_svc/main.py` (Lute's HTML tooltip page) is deleted; nothing else
  imported it. `start.ps1` rewritten: rebuilds `web/` only if its source is
  newer than the last build (plain `LastWriteTime` comparison, no hash
  tracking), then launches `uvicorn server.main:app --host 0.0.0.0 --port 8002`
  and opens the browser — `--host 0.0.0.0` (not the implicit loopback) is what
  makes the Tailscale/phone access actually reachable. `README.md` fully
  rewritten for korean-reader: daily use, `.env` setup, a pointer to `ANKI.md`,
  and full Tailscale phone-access steps (install on PC + phone, find the
  MagicDNS name, the Windows Firewall prompt for `--host 0.0.0.0`, the actual
  phone URL) — written as full from-scratch install steps since the user
  hasn't set up Tailscale yet. `%LOCALAPPDATA%\Lute3` (Lute's own data)
  deliberately untouched — the user's data, not this repo's to manage.
  `CLAUDE.md`'s "don't touch Lute stuff" hard rule updated to reflect that
  Lute is now retired.
  **User explicitly asked NOT to go live yet** (wants to keep developing —
  this isn't the project's final epic in spirit, just its ops chapter), so
  SPEC §10's Epic 8 accept criterion ("fresh `start.ps1` run serves the full
  app on :8002 from a cold start") was **not executed** this session. The
  script's logic was reasoned through against already-verified pieces from
  prior epics (`npm run build`, `uvicorn server.main:app --port 8002`), but
  nobody has actually double-clicked `start.ps1` from a cold start, hit the
  Windows Firewall prompt, installed Tailscale, or connected from a phone yet.
  **Do that whenever ready to actually rely on this day-to-day**; until then,
  treat the ops setup as written-but-unexercised.

## Cycle 2 — content sourcing

Epics 0–8 built the reading *machine*; its value now hinges on **content**: sourcing
Korean texts the user cares about and knowing a text's difficulty *before* committing to
it. The vision, tradeoffs, and open questions live in `docs/NEXT_STAGE_OPTIONS.md` — read
it before starting Epic 10. Guiding caution from that doc: **build the interest list
before the automation**, or the queue fills with lukewarm content and the app becomes a
chore. Automation (RSS/YouTube feeds + a daily fetch job) is deliberately deferred to a
later epic until the real sources are known.

- [x] **Epic 9 — Difficulty scorer** — done (2026-07-21). Difficulty = the relationship
  between a text and what the user already knows, not a fixed property of the text.
  `server/difficulty.py` (`score_text` → coverage %, new-lemmas, total-lemmas,
  new-per-page; `known_lemmas` treats every saved term as known regardless of status —
  `learning`/`known` are met, `ignored` won't be studied; see DECISIONS.md);
  `server/routes/difficulty.py` (`POST /api/score` for ad-hoc candidate text);
  `books.py` `POST /api/books/{id}/score` (caches `coverage`/`new_per_page`/`scored_at`
  onto the book row); `db.py` idempotent `_apply_migrations` adding those three columns
  so an existing `reader.db` upgrades in place (the additive-migration path Epics 11+
  reuse); frontend "Check difficulty" in the add-book modal, per-book score line +
  Score/re-score button, and an "Easiest unread" sort on the home page. 83/83 tests
  green (11 new in `test_difficulty.py`); `npm run build`/`npm run lint` clean. SPEC §10
  Epic 9 entry + two DECISIONS.md notes (additive migration; "all statuses count as
  known") added. **Not verified in a browser** (no browser tooling in this environment):
  the score line / "Check difficulty" / "Easiest unread" sort were verified at the
  data-contract level and via the passing suite, not watched on a phone — do a quick real
  pass when convenient.
- [x] **Epic 10 — Content catalog** — done (2026-07-21), non-code. `docs/
  CONTENT_CATALOG.md` (new) answers `NEXT_STAGE_OPTIONS.md`'s open questions (level:
  solid; register: both equally; games: PS5/free-monthly-title-driven, so no fixed game
  list — news/community + guides + YouTubers + reviews all wanted; fitness: YouTubers
  only; news: Reddit/HN in English, Yonhap tech only if genuinely interesting, not
  forced) and adds a category the original doc didn't have: **literature** — modern-only
  thrillers/sci-fi/short-fiction (Da Vinci Code, pessimistic sci-fi in the vein of
  *Citizen Sleeper*, Cortázar/García-Márquez-style short stories), explicitly no
  archaic/classical Korean. Source catalog table per topic (name/URL · type · feed
  verified? · topic · notes): **verified live** — Inven game news RSS, Ruliweb PS/game
  news RSS; **candidates needing channel-ID lookup** — 대도서관/감스트/우왁굳 (gaming
  YouTube), 피지컬갤러리/박승현 (fitness YouTube); **needs scraper or unverified** —
  Gamemeca (no RSS found), Yonhap tech (feed URL blocked by anti-bot fetch, untested via
  plain browser); **one-time imports, not feeds** — 5 literature candidates (다빈치 코드
  incl. a YA/simplified Korean edition; 정유정, 김영하, 김초엽, 정보라) and TOPIK
  passages. Both explicit sub-tasks done: (a) TOPIK past-exam reading passages identified
  as a content source (NIIED-published PDFs, fits the existing `pdf_text.py` path
  directly); (b) TOPIK/frequency word-list candidates identified for Epic 13 (NIIED
  graded vocab lists or 국립국어원 frequency lists) — not yet downloaded, just located.
  **Caveat:** all of this is 2026-07-21 web-search-derived and only spot-verified (2 RSS
  URLs fetched live), not personally vetted by the user — treat YouTube channel picks and
  author picks as a shortlist to react to before Epic 12 wires anything to them. Re-think the sources later. 
  For reviews and guides, prioritize well written articles over user unstructured short comments.
  For youtube, lets explore gaming podcasts, reviews and essays, and left leaning video essayinsts like Contrapoints, HBomberGuy or PhilosophyTube on the next iteration. Focus on exposition of ideas on fields i enjoy.
- [x] **Epic 11 — DB expansion + library UX** — done (2026-07-22). `server/db.py`:
  `_ADDED_COLUMNS["books"]` grew seven columns (`topic` TEXT, `tags` JSON-encoded TEXT,
  `source_url`, `source_ref` nullable, `fetched`, `archived`, `read`) via the same
  additive-migration path Epic 9 introduced, plus a partial `CREATE UNIQUE INDEX
  idx_books_source_ref ... WHERE source_ref IS NOT NULL` (created idempotently every
  `init_db` call) so paste/txt books (`source_ref IS NULL`) never collide but two
  imports of the same video id / feed guid do. New `feeds` table (id, name, type
  rss|youtube|scraper, url_or_channel_id, topic, enabled, difficulty_min,
  difficulty_max, last_fetched) landed as a plain `CREATE TABLE IF NOT EXISTS` —
  no CRUD routes yet, per the epic's own scope note (table now, fetch job later).
  `server/routes/books.py`: `POST` accepts `topic/tags/source_url/source_ref/fetched`
  (409 on duplicate `source_ref`); `PATCH` accepts `topic/tags/archived/read` and now
  returns the full book row (was the reduced `{id,title,current_page,page_count}`
  shape) so the frontend can update from the response; `GET /api/books` takes
  `?topic=` and `?archived=` filters. 91/91 tests green (8 new: topic/tag
  round-trip, topic/archived filtering, archived+read patch, duplicate-`source_ref`
  409, NULL-`source_ref` non-collision, migration idempotency for all seven columns
  and the `feeds` table). `npm run build`/`lint` clean. Frontend (`web/app/page.tsx`):
  topic `<select>` + "Show archived" checkbox (both re-query the server rather than
  filtering client-side — composes with the existing client-side Recent/Easiest-unread
  sort); per-book topic/tags line; "Mark read"/"Archive" toggle buttons (re-fetch after
  `PATCH` rather than patch local state, since toggling can move a book out of the
  current filter); add-book modal gained a topic `<select>` and comma-separated tags
  `<input>`. Five `docs/DECISIONS.md` entries added (tags-as-JSON/topic-as-string
  split, partial-index dedup rationale, feeds-table-without-routes rationale, the
  `PATCH` response-shape widening and why it's safe). `docs/ARCHITECTURE.md`'s schema
  block and API table updated — and backfilled with Epic 9's `coverage`/
  `new_per_page`/`scored_at` columns, which had been missed there.
  **Not verified in a browser** (no browser tooling in this environment; also
  deliberately not run against the user's real `reader.db`, to avoid seeding it with
  test books) — do a real pass together with Epic 9's still-pending one: tag a book,
  filter by topic, toggle archived/read and confirm the list updates, add a book with
  tags and confirm they round-trip.
- [x] **Epic 12 — Import wiring** — done (2026-07-22). `server/routes/imports.py`
  (new): `POST /api/import/youtube` (`{url, topic?, tags?}`), `POST /api/import/article`
  (`{url, topic?, tags?}`), `POST /api/import/pdf` (multipart `file` + `title?/topic?/
  tags?/pages?`). `server/routes/books.py` gained a shared `insert_book()` helper
  (raises `DuplicateSourceRef`) extracted out of `create_book`, reused by all three
  importers so the page-split + dedup-insert logic lives in one place. `import_tools/
  yt_subs.py`'s `fetch_subs()` now returns `(title, text, video_id)` (was `(title,
  text)`) and raises `NoSubtitlesError` instead of `SystemExit` (CLI `__main__`
  converts it back, so the standalone script's behavior is unchanged);
  `import_tools/pdf_text.py`'s `extract()` now accepts raw bytes as well as a `Path`
  (`fitz.open(stream=..., filetype="pdf")`, no temp file needed for the upload path),
  and its CLI page-range parsing was pulled out into a reusable `parse_page_range()`.
  `server/article.py` (new): thin `trafilatura` wrapper, `fetch_article(url) ->
  (title, text)`, raising `ArticleError` on an unfetchable URL or a page with no
  extractable text. Dedup keys (all in the Epic 11 `source_ref` column, prefixed to
  keep the three namespaces apart): `yt:<video_id>`, `article:<url>` (exact string),
  `pdf:<sha256 of uploaded bytes>` — see DECISIONS.md for why each shape was chosen.
  New deps: `yt-dlp`, `pymupdf`, `trafilatura`, `python-multipart` (all added to
  `requirements.txt`). 100/100 tests green (9 new in `test_imports.py`, mocking
  `imports.fetch_subs`/`imports.fetch_article`/`imports.extract_pdf` at the
  route-module boundary per the existing `test_translate.py` convention; PDF tests
  drive real multipart `files=`/`data=` through `TestClient`). `npm run build`/`lint`
  clean. `web/app/page.tsx`'s add-book modal gained a 4-way mode switch (Paste/.txt,
  YouTube, PDF, Article URL); `lib/api.ts` gained `importYoutube`/`importArticle`/
  `importPdf` + a `requestForm` helper for multipart uploads.
  **Real (non-mocked) sanity checks run manually, network-only, no DB writes:**
  `server.article.fetch_article` against a live URL (`https://www.yna.co.kr/`) —
  correct title + clean Korean body text; `import_tools.yt_subs.fetch_subs` against a
  real public YouTube video (PSY - Gangnam Style, `9bZkp7q19f0`) — correct title,
  video id, and Korean subtitle text extracted end-to-end through real `yt-dlp`.
  Deliberately **not** run through the API/DB layer against the user's real
  `reader.db`, per the same convention Epics 9/11 followed (avoid seeding it with
  test books from this environment).
  **Not verified in a browser** (no browser tooling in this environment) — do a real
  pass: paste a YouTube URL with Korean captions, upload a PDF, paste an article URL
  in the add-book modal; confirm each becomes a scored-ready book, and that
  re-submitting the same one 409s instead of duplicating.

- [x] **Epic 13 — Cold-start difficulty signal** — done (2026-07-22). Downloaded the
  official 국립국어원 (NIKL) 2003 "한국어 학습용 어휘 목록" (graded A/beginner,
  B/intermediate, C/advanced, ~5,965 entries) directly from korean.go.kr (needed a
  session-cookie'd request, not a plain URL — see DECISIONS.md), deduped homograph
  suffixes (가다01/가다02 → 가다, keeping the easiest grade where the same lemma had
  multiple senses/grades) down to 5,543 lemmas, and committed the clean result as
  `server/data/vocab_levels.tsv` (lemma/grade/rank, UTF-8). `server/db.py`: new
  `vocab_levels` table (`CREATE TABLE IF NOT EXISTS`, like Epic 11's `feeds`) +
  `_seed_vocab_levels()` (bulk-inserts from the TSV once, guarded by a `COUNT(*)`
  check, called from `init_db` after `_apply_migrations`). `server/difficulty.py`:
  `COLD_START_THRESHOLD = 50`, `frequency_grades(conn)` (loads the whole table into
  a `{lemma: grade}` dict), and `score_text` gained an optional third `frequency`
  param — when the personal known-set has fewer than 50 lemmas *and* a frequency map
  was passed, grade-A lemmas count as familiar too (both `coverage` and
  `new_per_page` reflect this); past that threshold, or when `frequency` isn't
  passed at all, behavior is byte-for-byte identical to Epic 9. Both `POST
  /api/score` and `POST /api/books/{id}/score` now pass `frequency_grades(conn)`
  through — the threshold check inside `score_text` is what actually gates it, so
  passing it unconditionally is safe. 107/107 tests green (7 new: seeding +
  idempotency in `test_db.py`; fallback unit tests, a threshold-crossing test, and
  the acceptance-criterion demonstration — a real rare/advanced sentence scoring
  harder than an all-common one through the live endpoint — in `test_difficulty.py`).
  `npm run build`/`lint` clean (no frontend changes needed — the add-book "Check
  difficulty" preview and per-book score line already render whatever the API
  returns). See DECISIONS.md for why NIKL over the actual TOPIK exam vocab list, why
  grade-A-only/binary (not a continuous A/B/C weighting), and why threshold 50 —
  all three are easy to revisit later if real usage shows over/under-shooting.
  **Not verified in a browser** (no browser tooling in this environment) — carry
  forward with the other pending browser passes (Epics 4–12).
- [x] **Epic 14 — Curated content list + feeds management + YouTube fetch** — done
  (2026-07-23). Re-scoped from the old "Daily fetch job": Epic 15 already built
  fetch→clean→score→dedup behind `POST /api/feeds/fetch`, so the user redirected this epic
  to what actually mattered — **curating the real multi-topic source roster** (the part
  they "dreaded") and being able to **retouch it later**. Three deliverables:
  **(1) Curated roster.** 15 verified feeds seeded via `db._SEED_FEEDS`, selected by the
  assistant to the user's tastes (male-presenter, idea-exposition/science over
  variety/lifestyle) across gaming/ideas/science/tech/fitness/news — full list + channel
  IDs + drop reasons in `docs/CONTENT_CATALOG.md`. Every feed verified live (RSS via the
  app's no-UA `fetch_feed_xml`; YouTube channel IDs resolved via yt-dlp and confirmed
  against each Atom feed). **(2) YouTube fetch support.** `server/feeds.py`
  `parse_youtube_feed`/`youtube_feed_url` + `routes/feeds._process_youtube`: a channel's
  Atom feed → new videos (dedup on `source_ref="yt:<video_id>"`, the same shape as Epic
  12's manual import, *before* fetching) → Korean transcript via `import_tools.yt_subs`
  (yt-dlp) → scored `candidate`; no-subs videos are `skipped_no_subs` (not failed);
  `YOUTUBE_MAX_PER_FETCH=5` bounds per-channel work per run. **(3) Feeds CRUD + `/feeds`
  page.** GET/POST/PATCH/DELETE `/api/feeds` + a management page (add / inline-edit /
  enable-disable / delete) so the roster is user-editable at runtime. Also: a per-row
  **"Translate" button on the Queue** (judge unfamiliar titles fast); shared
  `web/lib/topics.ts` taxonomy (added ideas/science/tech); a **Feeds** nav link.
  157/157 tests green (7 new in `test_feeds.py`: youtube parse/create/dedup/no-subs, feeds
  CRUD, disabled-feed-skip; `test_db.py` seed test generalized to the full roster).
  `npm run build`/`lint` clean. Docs: CONTENT_CATALOG.md roster, 4 DECISIONS.md entries,
  ARCHITECTURE.md feeds CRUD + youtube-fetch API rows and feeds-table comment.
  **Real (non-mocked) sanity check, network-only, no DB writes:** 조코딩's channel feed →
  real 37k-char transcript, and ㅍㅍㅅㅅ RSS → cleaned article, both end-to-end through the
  live pipeline. **Not verified in a browser** (no browser tooling here) — the `/feeds`
  page, the Queue translate button, and a real feed-fetch-into-queue run join the owed
  Epics 4–16 browser pass.
  **Still deferred to a later session (user's call):** the Windows **Task Scheduler**
  timer that pings `POST /api/feeds/fetch` on a schedule, plus the new-content
  cadence / stale-candidate retention policy. The manual "Fetch new candidates" button
  covers it until then.
- [x] **Epic 15 — Curation queue + general difficulty tag + source-type filter** —
  done (2026-07-23). Two gaps from Epics 12/13: no difficulty signal independent of the
  user's personal vocabulary, and no automation path that doesn't risk silently
  cluttering the library with content nobody asked to read.
  `server/difficulty.py` gained `GENERAL_WEIGHTS = {"A": 1.0, "B": 0.5, "C": 0.15}`
  (unlisted = 0.0) and `score_general_difficulty(text, frequency)` — a standalone
  weighted-average-over-grade score with **no personal `known` set at all**, shown
  *alongside* `score_text`'s personal coverage, never blended into it. Labels
  (`easy`/`medium`/`hard` at `>=0.75`/`>=0.45`/else) are recalibrated lower than
  `score_text`'s 0.95/0.85 bands since a weighted A/B/C/unlisted average rarely reaches
  the high-90s even for genuinely easy text — see DECISIONS.md, flagged as tunable.
  `server/db.py`: `books` gained `status` (`'library'|'candidate'|'discarded'`, `NOT
  NULL DEFAULT 'library'` **with a CHECK constraint** — a deliberate deviation from
  every prior additive column, justified because this one is a central enum the whole
  epic's correctness depends on) plus `general_coverage`/`general_level` (cached
  alongside `coverage`/`new_per_page` under one `scored_at`). **Candidate lifecycle is
  a `books.status` value, not a separate table** — a candidate already needs full page
  content + a score before the user decides, so it's structurally a book; promote/
  discard is one `PATCH`, never a copy across tables. **Discard is a soft delete**
  (`status='discarded'`, never a real `DELETE`) so the `source_ref` unique index stays
  permanent and a discarded item is never re-fetched. New seeded (not migrated) `feeds`
  rows: the two RSS feeds verified live back in Epic 10 (Inven, Ruliweb game news) —
  proves the infrastructure end-to-end; curating the full multi-topic source list
  (YouTube channel IDs, fitness, news, literature feeds) stays a separate future
  planning session. `server/feeds.py` (new, stdlib-only `xml.etree.ElementTree`):
  `fetch_feed_xml`/`parse_rss`, verified live against both feeds' real XML this
  session (plain RSS 2.0, no namespaces, CDATA titles, one feed has no `<guid>` at
  all — falls back to `<link>`). `server/routes/feeds.py` (new): `POST
  /api/feeds/fetch` (optional `?feed_id=`) iterates enabled feeds, skips non-`rss`
  types gracefully (youtube/scraper have no fetch logic yet), dedupes on `source_ref`
  *before* calling `fetch_article` (avoids wasted trafilatura calls), scores each new
  item via a shared `_score_and_cache()` helper extracted out of `routes/books.py`
  (computes both personal + general difficulty under one `scored_at` — the existing
  `POST /api/books/{id}/score` is now a thin wrapper over it), and isolates
  per-feed/per-item failures so one bad feed or article never blocks the rest — same
  isolation pattern as `anki_sync`'s per-note failures. `GET /api/books` gained
  `?source=` (exact match, mirrors `?topic=`) and now defaults `?status=` to
  `"library"` when omitted (the one behavior change to an existing endpoint — every
  pre-Epic-15 book already defaults to `status='library'`, so nothing previously
  visible becomes hidden; verified against every existing `test_books.py`/
  `test_difficulty.py` book-creation path). `BookPatch` gained `status`, so promote/
  discard reuse the existing `PATCH /api/books/{id}` — no new endpoints. 129/129 tests
  green (22 new: `test_feeds.py` for RSS parsing + the fetch route's dedup/isolation/
  skip behavior; `test_db.py` for column/seed idempotency and the default-status
  backfill; `test_difficulty.py` for `score_general_difficulty`'s bands and its
  independence from the personal known-set; `test_books.py` for the status filter,
  promote/discard, and the discarded-still-blocks-reimport guarantee). `npm run
  build`/`lint` clean. Frontend: `web/lib/score-display.tsx` (new) hoists
  `ScoreLine`/`coverageClass` out of `page.tsx` and adds `GeneralScoreLine`/
  `generalLevelClass`, shared by both the home list and the new `/queue` page;
  `web/app/page.tsx` gained a source-type filter `<select>` alongside the existing
  topic filter, a general-difficulty line per book row, the general %+label in the
  add-book "Check difficulty" preview, and a **Queue** nav link with a
  candidate-count badge; new `web/app/queue/page.tsx` (modeled on `/terms`) lists
  candidates with both score lines, a "Fetch new candidates" button
  (`POST /api/feeds/fetch`, shows the returned per-feed summary), and Promote/Discard
  buttons per row.
  **Real (non-mocked) sanity checks run manually, network-only, no DB writes:**
  `server.feeds.fetch_feed_xml` + `parse_rss` against both live seeded feed URLs —
  25 items from Inven, 15 from Ruliweb, titles/links parsed correctly;
  `score_general_difficulty` against the same STORY/RARE_STORY sentences Epic 13
  used, against the real seeded `vocab_levels` table — STORY (all grade-A) scored
  1.0/"easy", RARE_STORY (mixed/mostly-unlisted) scored 0.358/"hard", matching the
  same "rare text harder than common text" shape Epic 13 established. Deliberately
  **not** run through `POST /api/feeds/fetch` against the user's real `reader.db`,
  same caution as every prior epic.
  **Not verified in a browser** (no browser tooling in this environment) — the new
  Queue page and source-type filter join the already-owed Epics 4–13 browser/touch
  pass.
- [x] **Epic 16 — Stats screen + UI makeover** — done (2026-07-23). Re-scoped from the
  old "UI makeover + go-live": the user wanted a reading **stats screen** for
  accountability + sharing ("instagrammable"), with two specific asks — new words per
  book (watch the curve flatten) and new words per page. Go-live splits to **Epic 17**.
  SPEC §227's backlog had explicitly excluded "stats/reading-time tracking" — this epic
  **deliberately reverses that** at the user's request (logged in DECISIONS.md; §227
  amended). Backend: `terms` gained nullable `source_book_id`/`source_page` (forward-only
  provenance, via the same `_ADDED_COLUMNS` path); new `page_reads` table
  (`PRIMARY KEY(book_id,page_no)` + `INSERT OR IGNORE` so revisits never double-count) +
  `POST /api/reads`; `GET /api/stats` aggregates totals/streak (union of word-save days +
  first-read-page days, local-time buckets)/365-day activity/new-words-per-book
  (provenance join)/vocab depth by NIKL grade + beginner %; `settings.page_size`
  (default 650) drives `split_pages` at import and re-paginates the whole library on
  change (position preserved by char offset, `page_reads` cleared) while difficulty's
  `new_per_page` stays pinned to the 1500 reference so scores don't drift. Reader pings
  `/api/reads` only after a **5s visible-dwell** gate (`READ_DWELL_MS`), and passes
  book/page provenance to `POST /api/terms` on new-term save. Frontend: new `/stats`
  (hero tiles, GitHub-style activity heatmap, new-words-per-book SVG line, vocab-depth
  bar, milestone badges — all hand-rolled SVG/CSS, **no new npm deps**), a page-size
  control in `/settings`, a Stats nav link. 150/150 tests green (21 new: `test_stats.py`
  streak-logic + aggregation, `test_reads.py` dedup/cascade/404, `test_settings.py`
  page_size + repaginate/position-preserve/clears-reads, `test_db.py` provenance +
  page_reads migration idempotency). `npm run build`/`lint` clean. Five DECISIONS.md
  entries (backlog reversal, provenance shape, read-log dedup+dwell, page-size-as-setting
  + difficulty decoupling), SPEC §227 + Epic 16 entry, ARCHITECTURE.md schema + API table.
  **Not verified in a browser** (no browser tooling in this environment) — the `/stats`
  screen, the dwell-gated read logging, and the page-size re-pagination join the already-
  owed Epics 4–15 browser/touch pass. The makeover this epic did is the stats screen
  itself as the visual anchor + a Stats nav link; a fuller per-screen polish pass can
  still ride along with Epic 17 if wanted.
- **EPUB import (2026-07-23, not a numbered epic — user request between Epics 16 and 17).**
  Added a fifth importer alongside Epic 12's four. `import_tools/epub_text.py` (new): `ebooklib`
  walks the OPF spine in reading order, a small stdlib `HTMLParser` subclass strips each XHTML
  document to text (no BeautifulSoup). `server/routes/imports.py`: `POST /api/import/epub`
  (multipart `file` + `title?/topic?/tags?`), source `epub`, dedup `epub:<sha256 of bytes>`
  (same byte-hash shape as PDF), plus a 502 when the EPUB has no extractable text (DRM'd /
  image-only). New dep `ebooklib==0.20` (only `lxml`, already transitively present, added).
  Frontend: add-book modal gained an "EPUB" mode; `lib/api.ts` `importEpub`. 163/163 tests
  green (6 new in `test_imports.py`: route create/dedup/extract-failure/empty-text, plus two
  **real non-mocked** tests that build a tiny EPUB in memory with `ebooklib` and run the actual
  extractor + full import through `TestClient`). `npm run build`/`lint` clean. See DECISIONS.md
  (ebooklib + stdlib-strip, spine-order, empty-text 502, filename-title) and ARCHITECTURE.md
  (import API row + dedup-key note). **Browser-unverified** — joins the owed Epics 4–16 pass:
  open the add-book modal, pick EPUB, upload a real Korean `.epub`, confirm it becomes a
  scored-ready book and that re-uploading the same file 409s.
- [x] **Epic 17 — Fetch automation, candidate retention, terminology pass** — done
  (2026-07-23). Full scope was written up in `docs/SPEC.md` §10 in a prior planning
  session; this session implemented it as planned, with no deviations. `scripts/
  fetch_feeds.ps1` (new) is the Task Scheduler action — POSTs to the existing `POST
  /api/feeds/fetch`, logs the result/error to `scripts/fetch_feeds.log`; no new
  server code needed for automation itself since it reuses the manual button's exact
  endpoint (server assumed always-up on Tailscale, per the user). `routes/
  settings.py` gained `candidate_retention_days` (default 7, editable, `ge=1,le=90`)
  and a system-stamped-only `last_fetch_attempt` (deliberately excluded from
  `SettingsPut`). `routes/feeds.py`'s `fetch_feeds()` now stamps
  `last_fetch_attempt` and auto-discards (`status='discarded'`, no new status enum)
  any candidate past the retention window on **every** call — scheduled, manual, or
  a single-feed retry — reporting the count as a new `expired` field; no separate
  cron, see `docs/DECISIONS.md`. 171/171 tests green (8 new). `npm run build`/`lint`
  clean. Frontend: `/settings` gained a retention-days input; UI copy swept
  "book(s)" → **"Library"** (nav links, add-content modal, `/stats` headings/
  milestones), with **"Book"** now a small badge reserved for `pdf`/`epub`-sourced
  rows on `/` — copy-layer only, no schema renaming. README gained a Task Scheduler
  registration walkthrough. `last_fetch_attempt`'s on-page display and the rest of
  the Queue visual overhaul are Epic 18 scope, not touched here.
  **Not verified in a browser** (no browser tooling in this environment) — do a
  real pass together with the other owed epics: change the retention setting in
  `/settings` and confirm it round-trips; skim the built UI for the new
  "Library"/"+ Add"/"Book"-badge copy. **Registering `scripts/fetch_feeds.ps1` in
  Task Scheduler is deliberately NOT part of this pass** — the user confirmed
  (2026-07-23) the script itself is fine as written, but actually wiring it into
  Task Scheduler on their machine is Epic 20 (go-live) work, not now.
- [x] **Epic 18 — Queue browsing UX: cards, chips, sort/filter, length, source
  link, back-to-top** — done (2026-07-23), as planned in `docs/SPEC.md` §10 with
  no deviations. `import_tools/yt_subs.fetch_subs()` now returns a 4-tuple
  (added real `duration_seconds` from yt-dlp's own metadata — not a transcript
  estimate); every call site (`routes/imports.py`, `routes/feeds.py`, the CLI)
  updated. `books` gained `word_count` (every source, computed in
  `insert_book()`) and `duration_seconds` (yt only) as additive columns.
  Frontend: `web/lib/chips.tsx` (`SourceChip`, palette-token colors, no new
  hues), `web/lib/length.ts` (`formatLength` for display, `estimatedMinutes`
  — a 250-wpm heuristic used only to rank the "Shortest first" sort, never
  shown). `web/app/queue/page.tsx` rewritten: Cards/List toggle
  (`localStorage`-persisted, cards default), a sort-by picker (newest fetched
  / easiest / shortest), the Epic 17 `last_fetch_attempt` line, an "↗"
  source link per item, a back-to-top floating button, and the fetch-result
  panel now also shows Epic 17's `expired` count. 172/172 tests green (1 new
  in `test_db.py`; existing YouTube-import tests extended with
  `duration_seconds`/`word_count` assertions). `npm run build`/`lint` clean.
  **Not verified in a browser** (no browser tooling in this environment) — the
  card/list toggle, chips, sort, length stat, source link, and back-to-top all
  join the already-owed browser/touch pass; also worth a real feed-fetch of an
  actual YouTube video to confirm `duration_seconds` matches its real runtime.
- [x] **Epic 19 — Promotion stats: what gets read vs. what doesn't** — done
  (2026-07-23), as planned in `docs/SPEC.md` §10. Kept the SPEC's flagged judgment
  call rather than dropping it: `discard_reason` (`'user'`/`'expired'`/NULL, no
  `CHECK`) ships alongside `feed_id`, since collapsing the two into plain
  `discarded` would make the new stats section unable to tell "actively rejected"
  apart from "aged out unread" — the entire point of the feature (see
  DECISIONS.md). `books` gained two additive columns: `feed_id` (soft reference, no
  FK, same convention as `terms.source_book_id` — set only by `routes/feeds.py`'s
  `_insert_and_score` for feed-sourced candidates; manual imports/paste leave it
  NULL, which doubles as the curation query's "is this feed-sourced" filter) and
  `discard_reason`, written at its two call sites (`routes/books.py`'s manual
  `PATCH status='discarded'` → `'user'`; Epic 17's auto-expiry `UPDATE` in
  `routes/feeds.py` → `'expired'`, in the same statement). `GET /api/stats` gained
  `curation: {by_topic, by_feed}` — one grouped query over `feed_id IS NOT NULL`
  rows, folded into `{promoted, user_discarded, expired, pending}` counts per
  topic and per feed (`by_feed` falls back to `"(deleted feed #<id>)"` if the feed
  was since deleted — deleting a feed never touches the books it produced). 176/176
  tests green (7 new: `test_db.py` migration idempotency; `test_feeds.py` `feed_id`/
  `discard_reason` round-tripping at both write sites; `test_books.py` the manual-
  discard reason plus the book-shape key-set update; `test_stats.py`'s new
  aggregation cases — empty, multi-topic/multi-feed across all four buckets, and
  the deleted-feed fallback name). `npm run build`/`lint` clean. Frontend: `/stats`
  gained a "What gets promoted" section (two stacked-bar breakdowns, hand-rolled
  SVG/CSS, no new npm dependency — same convention as every other `/stats` chart).
  Two DECISIONS.md entries (keeping `discard_reason`; `feed_id` as a soft
  reference), ARCHITECTURE.md schema block + API table + a full Epic 19 write-up.
  **Not verified in a browser** (no browser tooling in this environment) — joins
  the already-owed pass; also worth a real look once there's been enough feed
  activity (some promotions, some expiries, some manual discards) for the by-topic/
  by-feed bars to show something meaningful, not just small test-sized counts.
- [x] **Epic 20 — Term forms (aliases) + highlighting fix** — done (2026-07-23).
  Fixes a real bug: the user hand-edited a term's **lemma** into `승인 / 승인서` to remind
  themselves on the Anki card that the derived word 승인서 exists — which broke
  highlighting, since matching is exact lemma-equality and `승인 / 승인서` is no tokenizer
  lemma. Introduced a **`forms` list per term** (the aliases) that does double duty:
  each form both highlights in the reader (tapping it opens the parent term) **and**
  renders on the Korean face of the Anki card, while `lemma` stays the one clean
  dictionary form. New `term_forms(term_id, form)` table (`CREATE TABLE IF NOT EXISTS`
  with `ON DELETE CASCADE`, like `pages`/`page_reads` — not a JSON column, so
  `books.get_page` matching stays an efficient `WHERE form IN (...)`). `routes/terms.py`:
  `TermCreate`/`TermPatch` accept `forms: list[str]`; `_normalize_forms` (trim, drop
  blanks + the lemma itself, dedupe keeping order); `_term_dict` returns `forms`; a forms
  change is a dirty trigger (re-syncs the card front). `books.get_page`: second query
  joins `term_forms` and keys the returned map by the **form** string (direct-lemma match
  wins on collision); the map now also carries `lemma` + `forms` per entry so a tapped
  form token shows the real dictionary form in the popover. `anki_sync._render_front`:
  Front = `lemma / form1 / form2`. Frontend: `TokenPopover` gained a chip-style "Also
  highlight" forms editor (splits on space/comma/slash — the shape the user was typing);
  `read/page.tsx` re-keys the highlight map by term id on save/delete so form highlights
  refresh without a refetch. 184 tests green (8 new: forms round-trip/normalize on
  create+patch, forms-change dirty rule, cascade delete, `get_page` highlights a form,
  Anki front with forms). `npm run build`/`lint` clean. Immediate cleanup for the user:
  edit the broken term — set lemma back to `승인`, add `승인서` in "Also highlight".
  **Not verified in a browser** (no browser tooling here) — joins the owed pass: save a
  word with an extra form, confirm the form highlights and tapping it opens the parent
  entry, then sync and confirm the card Front shows `lemma / form`. The `/terms`
  management page does **not** yet edit forms (reader popover only) — a small Phase-B/
  follow-up gap if wanted.
- [x] **Epic 21 — Dictionary click-to-add + krdict examples + reversed Anki card type** —
  done (2026-07-23), Phase B of the term-forms plan (`hey-babes-i-need-temporal-beacon`),
  as scoped in `docs/SPEC.md` §10 with no deviations. **No Claude API** (user constraint)
  — krdict + DeepL + manual only. Backend: `translate_svc/krdict.py` `lookup()` now returns
  `target_code` + `examples` per entry (a per-entry `view` call — the search API's `<sense>`
  carries no examples — best-effort, deduped, capped at 5; `max_entries` raised 3→5);
  `terms` gained a JSON `examples` column (display-only, folded into the same
  UPDATE/dirty path as the text columns) and an `anki_model` column so sync branches
  legacy `Basic` vs the new model. `server/anki.py`: `ensure_model()` (idempotent
  `createModel` of `"Korean Reader 2-way"` — fields Korean/English/Examples, two
  templates KO→EN and EN→KO with `{{Examples}}` on the **back of both, front of
  neither**) + `add_note_model`/`update_note_model`. `routes/anki_sync.py`: new terms →
  the two-way model (Korean = lemma+forms, English = translation, Examples = clicked-in
  examples + reading sentence); dirty terms branch on `anki_model` so pre-Epic-21 `Basic`
  notes keep their Front/Back path and SRS history. Frontend `TokenPopover`: interactive
  dictionary (tap a headword → `forms`; tap a sense → append its gloss to the translation;
  tap an example chip → card examples) + an examples editor; phrase selections
  (`isPhrase`, whitespace in the selection) get a translate-only popover (dictionary/
  forms/examples hidden). 198 tests green (14 new: `test_krdict.py` example
  parsing/view-fallback/dedup-cap/no-key; `test_terms.py` examples round-trip/normalize/
  dirty; `test_anki_sync.py` two-way add + Examples rendering, anti-spoiler template
  assertion, `ensure_model` idempotency, new-model update, legacy-`Basic` back-compat;
  `test_db.py` migration idempotency). `npm run build`/`lint` clean.
  **Not verified against live Anki / in a browser** (no Anki desktop or browser tooling in
  this environment) — joins the owed pass, and this one specifically needs a **real Anki
  check**: sync a new term, confirm it creates a two-way note (two cards KO→EN and EN→KO)
  with the example on the back of both and the front of neither, and confirm a term
  synced before this epic still updates in place as a `Basic` note without losing its
  review history. Also confirm krdict `view` examples actually come back for a real word
  (the `view`-API shape was implemented per krdict's documented structure but not hit
  live here, since no `KRDICT_API_KEY` is set in this environment). The `/terms`
  management page still doesn't edit forms/examples (reader popover only) — same
  Phase-B/follow-up gap noted in Epic 20.
- **Row-based reader pagination + Library source link + Queue filters (2026-07-24, not a
  numbered epic — three small user requests done between Epic 21 and Epic 22).**
  `server/paging.py` gained `estimate_rows`/`split_pages_by_rows` alongside the existing
  char-based `split_pages` (kept untouched — `difficulty.py` still pins its 1500-char
  reference to it, so scores don't drift with reader page size). `settings.page_size`
  replaced by `page_rows` (default 22) + `chars_per_row` (default 32, user-tunable to their
  own device); `routes/books.insert_book` and `routes/settings.repaginate_all` both switched
  to the row-based splitter. `split_pages_by_rows` walks the breakpoint list with a single
  forward cursor across the whole call (not a per-page rescan like `split_pages`) —
  addresses the user's stated concern about repagination lag on a very long (1000+ page)
  book when the page-size setting changes. 206 tests green (8 new: 6 in `test_paging.py` for
  `estimate_rows`/`split_pages_by_rows`, 2 in `test_settings.py` for `chars_per_row`; existing
  `test_settings.py`/`test_books.py` cases updated for the renamed setting). `npm run build`/`lint`
  clean. Frontend: `/settings`'s page-size control is now rows-per-page presets + a
  chars-per-row numeric input; `/` (Library) gained the `↗` source link Queue already had
  (placed in the row's action strip, not nested inside the row's own `<Link>` — nesting an
  `<a>` inside a Next `Link` anchor is invalid HTML); `/queue` gained the topic/source
  `<select>` filters `/` already had (the API already supported `?topic=`/`?source=` on
  `GET /api/books`, just wasn't wired into the Queue UI). See DECISIONS.md.
  **Not verified in a browser** (no browser tooling in this environment) — joins the owed
  pass: open `/settings`, try the rows-per-page presets and chars-per-row input, confirm a
  book re-paginates and the row estimate roughly matches what's on screen (then tune
  chars-per-row to taste); confirm `/`'s new source link opens the right URL without
  triggering the reader-page navigation underneath it; confirm `/queue`'s new topic/source
  filters actually narrow the candidate list.
- [x] **Epic 22 — Structured Front/Back/Examples card builder** — done (2026-07-24),
  ad hoc user request (not planned ahead of time in `docs/SPEC.md`'s original epic
  list, written up retroactively there per the executor convention). The user was
  unhappy with how the popover shaped what actually lands on the Anki card: the
  translation textarea was disorganized (Translate overwrote it, Dictionary appended
  to it, unpredictably), krdict's Korean-language definitions were fetched but never
  shown, and nothing distinguished dictionary-derived content from hand-typed content.
  Full design discussion (chip model, numbering scheme, color provenance, what "Notes"
  in Anki actually referred to — a false alarm, the field really is called "Examples")
  worked out in conversation before any code; see `docs/DECISIONS.md` for the two
  structural calls (`group_key` as a stable id, the `examples` column superseded not
  dropped). Backend: `term_forms` gains `kind` (`'dict'`|`'manual'`, additive); new
  `term_back_items(id, term_id, group_key, kind, text, korean_def)` table — one row
  per Back chip, `group_key` `''` = the lemma's group or a form's text. `routes/
  terms.py`: `forms` becomes `[{text, kind}]`, new `back_items: [{group, kind, text,
  korean_def}]`, `translation` derived from `back_items` when non-empty (join order =
  group order), `back_items`-changed is a new dirty trigger. `routes/books.py`'s
  `get_page` prefill (which the reader's tap-to-edit popover actually reads, not
  `/api/terms`) gained `notes` (previously missing entirely) and `back_items`, reusing
  `terms.py`'s own read helpers instead of a third copy of the query. `routes/
  anki_sync.py` rewritten: Front is a numbered stack when 2+ entries (unchanged bare
  lemma otherwise); Back/Examples render from `term_back_items` when any exist — one
  line per item, lettered (`1a.`/`1b.`) when its front entry has 2+ items — labels
  shared between Back and Examples so they always correlate; a term with **zero**
  `term_back_items` (never touched by this system) renders Back/Examples exactly as
  before this epic (flat `translation`, the old `examples` column) — the "legacy
  stays as it is" guarantee extended to Anki, not just the popover. `server/anki.py`/
  `ensure_model()` untouched — confirmed with the user this was unnecessary. 218 tests
  green (12 new: `test_db.py` migration idempotency for both schema changes;
  `test_terms.py` forms-with-kind + back_items round-trip/dirty/derived-translation;
  `test_anki_sync.py` rewritten stacked/numbered assertions + new multi-form/
  multi-sense/legacy-fallback/notes-appended cases; `test_books.py` updated for the
  richer page-payload shape). `npm run build`/`lint` clean. Frontend: `TokenPopover`
  rewritten — removed the free-text "Also highlight" input; bigger centered
  Translate/Dictionary buttons; a live read-only Front/Back chip preview (lemma +
  manual entries orange, dictionary chips a blue family paling as more are added,
  Translate results green), each deletable (deleting a Front form cascades to its
  Back items); dictionary headword clicks add/attach a Front chip + first sense +
  Korean definition, every sense independently clickable for more Back items; an
  "Examples" preview (that exact label, matching the real Anki field) with auto
  lines + a free-typed `notes` textarea; a manual "Add entry" form (Front + Back
  text) that's always its own independent group, guarded by a duplicate-text check;
  a legacy term (no `back_items` yet) shows its old flat translation read-only,
  labeled "(legacy)" — no forced migration. New `--color-dict-1..4`/`--color-
  translate`/`--color-manual` tokens in `globals.css`'s `@theme` block (light+dark).
  **Not verified against live Anki / in a browser** (no Anki desktop or browser
  tooling in this environment) — joins the owed pass, and this one specifically needs
  a real Anki check: save a word with 2+ dictionary senses and confirm the popover's
  numbered/lettered chips match what actually lands on the synced card (Front stack,
  lettered Back, matching labels in Examples); add a manual entry and confirm it's
  independent (its own group, orange, not merged into the lemma); open a
  pre-existing (this session's test) term and confirm it still displays and syncs
  exactly as before, read-only, until touched by the new system.
- [ ] **Epic 23 — Go-live (final stage, renumbered from Epic 17→20→22→23 as content
  epics were inserted).** Execute Epic 8's still-pending cold-start + Tailscale
  verification and go live day-to-day, optionally with a fuller per-page UI polish
  pass. **Also register `scripts/fetch_feeds.ps1` in Windows Task Scheduler here**
  (per the README section Epic 17 added) — the user confirmed 2026-07-23 the script
  itself needs no changes, actually wiring it up on their machine is part of go-live,
  not before.
  **Acceptance:** a verified cold-start `start.ps1` run reachable from the phone over
  Tailscale, and the scheduled fetch task registered and firing.

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

- Tests must pass offline: mock DeepL/Claude/krdict/AnkiConnect; temp sqlite per test.
- **The original 9 epics (0-8) are done** and Lute is retired (Epic 8, see above).
  A second cycle — **content sourcing** — is now planned in the "Cycle 2" section
  above. Epics 9 (difficulty scorer), 10 (content catalog), 11 (DB expansion +
  library UX), 12 (import wiring), 13 (cold-start difficulty signal), 15 (curation
  queue + general difficulty + source filter), and **14 (curated content roster +
  feeds management + YouTube fetch, done 2026-07-23)** are done. **Epic 16 — Stats
  screen + UI makeover** is done (2026-07-23).
- **2026-07-23 planning session: Epics 17-19 added, Go-live renumbered to Epic 20**,
  full scope in `docs/SPEC.md` §10. **Epics 17, 18, and 19 are now all done** (see
  above).
- **2026-07-23 — Epics 20 and 21 (Term forms + card builder) both done.** The two-phase
  term-forms plan (`hey-babes-i-need-temporal-beacon`, approved by the user) is complete:
  **Epic 20** (forms/aliases + highlighting fix) and **Epic 21** (dictionary click-to-add
  + krdict examples + a custom two-way Anki note type) both shipped. Hard user constraint
  honored in Epic 21: **no Claude API** in the card-builder (krdict + DeepL + manual only).
- **2026-07-24 — Epic 22 (structured Front/Back/Examples card builder) done.** Ad hoc
  user request driven by dissatisfaction with how the popover shaped the Anki card —
  full write-up above. Not part of the original planned epic list; logged into
  `docs/SPEC.md` §10 retroactively per the executor convention.
  **Next up is Epic 23** (go-live: verified cold-start `start.ps1` reachable from the
  phone over Tailscale, plus registering `scripts/fetch_feeds.ps1` in the user's
  actual Windows Task Scheduler — the user confirmed 2026-07-23 the script itself is
  fine as-is). Epic 23 is the final planned epic.
- **The user deferred the browser/touch pass over Epics 4-12 until after Epic 13**
  specifically to see Epic 13's cold-start scoring results first (2026-07-22); Epic 15
  added two more unverified surfaces (the `/queue` page, the source-type filter) to
  the same still-owed pass; Epic 16 adds the `/stats` screen, the reader's dwell-gated
  read logging, and the page-size setting's re-pagination; Epic 14 adds the `/feeds`
  management page, the Queue's per-row Translate button, and a real feed-fetch run (hit
  "Fetch new candidates" and confirm YouTube channels produce transcript candidates and
  RSS feeds produce article candidates, all topic-tagged). That pass (paste a YouTube
  URL, upload a PDF, paste an article URL, try the Queue's Fetch/Promote/Discard flow,
  add/edit/disable a feed on `/feeds`, check the Stats screen after saving words + reading
  a few pages, change page size and confirm books re-paginate with reading position
  preserved, plus the older Epic 4-11 checklist items above) is still owed whenever the
  user is ready. Epics 17-19 add three more items to the same pass: the retention
  setting on `/settings`, the Queue's card/list/chip/sort/length/back-to-top UX, and
  Epic 19's new "What gets promoted" section on `/stats` (best checked after some real
  feed activity — promotions, expiries, manual discards — so the by-topic/by-feed bars
  show something meaningful). **Epics 20-21** add the reader popover's forms editor +
  interactive dictionary (tap headword/sense/example), the examples editor, the
  translate-only phrase popover, and — needing a **live Anki desktop**, not just a
  browser — the two-way card check: sync a new term and confirm two cards (KO→EN, EN→KO)
  with the example on the back of both and the front of neither, and that a term synced
  before Epic 21 still updates as a `Basic` note without losing SRS history. **Epic 22**
  adds the rewritten popover's chip preview (front/back colors and delete/cascade
  behavior), the manual "Add entry" form, the legacy-term read-only display, and —
  again needing a live Anki desktop — confirming a multi-sense word's numbered/lettered
  Front/Back/Examples actually match the popover's preview once synced.
- **Epic 8's live cold-start + Tailscale verification is still pending** — the
  user asked for docs/launcher only, not to go live yet. Before relying on this
  day-to-day: close everything, double-click `start.ps1` from a cold start,
  confirm it rebuilds `web/` correctly and opens `http://localhost:8002`; set up
  Tailscale on the PC and phone per the new `README.md`; confirm the Windows
  Firewall prompt appears and allowing it lets the phone actually connect.
- A Tailwind-based visual redesign (warm "paper" palette — see `web/app/
  globals.css`'s `@theme` block and the matching `docs/DECISIONS.md` entry)
  landed this session across all four pages; the user confirmed they're happy
  with the palette but said a **fuller per-page UI makeover is still wanted
  later** — treat the current styling as a baseline, not final.
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
