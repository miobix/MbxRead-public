# Architecture

This document describes the app **as built**. It starts as a copy of `docs/SPEC.md`
sections 3–8 (the plan) and must be amended whenever an epic's implementation diverges
from the plan — this file always describes the code as it currently is, not the
original intent. See `docs/DECISIONS.md` for the reasoning behind divergences.

## Layout

```
korean-reader/
  server/                  FastAPI app, port 8002
    __init__.py
    main.py                app factory; mounts /api routers; serves web/out statically at /
    db.py                  sqlite (reader.db): connection, schema init, query helpers
    tokenizer.py           kiwipiepy wrapper: text -> eojeol tokens with lemma
    anki.py                AnkiConnect client (http://127.0.0.1:8765)
    article.py             trafilatura wrapper: url -> (title, cleaned_text) — Epic 12
    difficulty.py           coverage/new-per-page scoring; Epic 13's cold-start
                            frequency fallback
    data/
      vocab_levels.tsv      Epic 13: bundled NIKL word-grade reference data, seeded
                            into the `vocab_levels` table on first init_db
    routes/
      books.py  terms.py  translate.py  anki_sync.py  settings.py  difficulty.py
      imports.py           Epic 12: YouTube/PDF/article import endpoints
  server/tests/            pytest suite
  translate_svc/           used as a library (translators.py, cache.py, krdict.py,
                           config.py) — main.py (Lute's HTML tooltip page) deleted
                           in Epic 8, Lute is fully retired
  web/                     Next.js app (TypeScript, Tailwind, output: 'export')
  import_tools/            yt_subs.py / pdf_text.py — still runnable standalone CLIs,
                           now also imported as libraries by routes/imports.py (Epic 12)
  docs/                    living design docs (see Executor conventions)
  requirements.txt         direct Python deps
  scripts/fetch_feeds.ps1  Task Scheduler action: POSTs /api/feeds/fetch — Epic 17
  start.ps1                single-server launcher — rewritten in Epic 8
  reader.db                app data — never commit
```

- New Python deps: `kiwipiepy` (no system deps, works on Windows), plus existing
  `fastapi`, `uvicorn`, `httpx` already in `.venv`.
- Port **8002**, `--host 0.0.0.0` (Tailscale/LAN reachable). Lute used to keep 5001/8001
  during the transition; those are free now that Lute is retired (Epic 8).
- Node.js required for the `web/` build. If Node is missing on the machine, tell the
  user to install Node LTS and stop (`needs input`), don't work around it.

**Epic 0 status:** `server/main.py` exposes an app factory `create_app(db_path=None)`
returning a FastAPI app whose `lifespan` calls `db.init_db(path)` on startup (not at
import time) — this lets tests point at a temp DB via `create_app(tmp_path / "test.db")`
without ever touching the real `reader.db`. Module-level `app = create_app()` is the
uvicorn entrypoint (`uvicorn server.main:app --port 8002`) and uses the default path
(`reader.db` at repo root). `web/out` static mount is wired since Epic 0 and now
actually serves the Epic 4 frontend build. `.venv` was created with Python 3.10
(`py -3.10 -m venv .venv`) per kiwipiepy's Windows compatibility story.

**Epic 2 status:** `server/routes/books.py` implements full CRUD plus the page
payload endpoint, registered in `main.py` via `app.include_router(books.router)`.
`server/db.py` adds `get_db(request: Request)`, a FastAPI dependency that opens one
`sqlite3.Connection` per request from `request.app.state.db_path` and closes it after
— routes take `conn: sqlite3.Connection = Depends(db.get_db)`. `server/paging.py`
holds the page-splitting util (see below). `routes/terms.py`, `translate.py`,
`anki_sync.py` are now implemented (Epics 3, 3, 6); `settings.py` remains
unimplemented (Epic 7).

## Data model (`reader.db`, created by `server/db.py` on startup)

```sql
CREATE TABLE IF NOT EXISTS books (
  id INTEGER PRIMARY KEY,
  title TEXT NOT NULL,
  source TEXT NOT NULL DEFAULT 'paste',          -- paste | txt | yt | pdf | article
  created TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  -- Epic 24: reading position as a character offset into the book's text —
  -- device-independent, unlike a page number, now that each device paginates for
  -- its own screen. Replaced current_page, which was backfilled into it and then
  -- dropped (db._backfill_current_offset, then ALTER TABLE ... DROP COLUMN).
  current_offset INTEGER NOT NULL DEFAULT 0,
  -- Epic 9 (additive migration): cached difficulty score.
  coverage REAL,                                 -- fraction of lemmas already known; NULL if unscored
  new_per_page REAL,                             -- unknown-unique lemmas / page count
  scored_at TIMESTAMP,
  -- Epic 11 (additive migration): content-catalog metadata.
  topic TEXT NOT NULL DEFAULT '',                -- gaming | fitness | news | literature | other | ''
  tags TEXT NOT NULL DEFAULT '[]',               -- JSON array of free-form strings
  source_url TEXT NOT NULL DEFAULT '',
  source_ref TEXT,                               -- stable id (video id/feed guid); see partial UNIQUE index below
  fetched TIMESTAMP,                             -- set by automated imports (Epic 12+), NULL for manual paste/txt
  archived INTEGER NOT NULL DEFAULT 0,
  read INTEGER NOT NULL DEFAULT 0,
  -- Epic 15 (additive migration): candidate-queue lifecycle + general/public difficulty.
  status TEXT NOT NULL DEFAULT 'library'        -- library | candidate | discarded
    CHECK (status IN ('library','candidate','discarded')),
  general_coverage REAL,                        -- weighted-average NIKL-grade score; NULL if unscored
  general_level TEXT,                           -- easy | medium | hard; NULL if unscored
  -- Epic 18 (additive migration): length stat for the Queue.
  word_count INTEGER,                            -- every source, at insert time
  duration_seconds INTEGER,                      -- yt only, real yt-dlp video length
  -- Epic 19 (additive migration): promotion-stats provenance. feed_id is a soft
  -- reference (no FK, same convention as terms.source_book_id below) — set only for
  -- feed-sourced candidates (routes/feeds.py), NULL for manual imports/paste, which
  -- is also how the curation stats query tells them apart. discard_reason ('user' |
  -- 'expired') is set at the two places status flips to 'discarded'.
  feed_id INTEGER,
  discard_reason TEXT
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
  updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  source_book_id INTEGER,                        -- Epic 16: book this word was first saved from (nullable, no FK)
  source_page INTEGER,                           -- Epic 16: page it was first saved from
  examples TEXT NOT NULL DEFAULT '[]',           -- Epic 21: JSON list of krdict examples + reading sentence, shown on the Anki card back only
  anki_model TEXT,                               -- Epic 21: NULL/'Basic' = legacy note, else the custom two-way model name
  hanja TEXT NOT NULL DEFAULT '[]'               -- Epic 25, list since Epic 26: JSON list of hanja spellings, one per sense (시장 = 市場 + 市長); '[]' = a plain reading-flow term
);
-- Epic 20: extra surface forms (aliases) a term also covers — 승인서/승인하다 under 승인.
-- Highlights in the reader (matched alongside the lemma in get_page) and renders on the
-- Anki card's Korean face; lemma stays the single clean dictionary form. Epic 22: `kind`
-- ('dict'|'manual', additive, default 'manual') — dictionary-clicked vs hand-typed via
-- "Add entry"; drives popover chip color only, irrelevant to page-token matching.
CREATE TABLE IF NOT EXISTS term_forms (
  term_id INTEGER NOT NULL REFERENCES terms(id) ON DELETE CASCADE,
  form TEXT NOT NULL,
  kind TEXT NOT NULL DEFAULT 'manual',
  PRIMARY KEY (term_id, form)
);
-- Epic 22: the popover's structured Front/Back card builder — one row per Back chip.
-- `group_key` '' = the lemma's own group, else a term_forms.form value — a stable id,
-- not a live join on lemma text, so editing the lemma never orphans its back items.
-- Epic 26: on a hanja term the group is instead the hanja spelling of the sense the
-- chip belongs to, which is what pairs each meaning with its spelling on the card.
-- `korean_def` (kind='dict' only) is krdict's Korean definition with any example
-- glued directly onto the end (no separator); feeds the Anki `Examples` field only.
CREATE TABLE IF NOT EXISTS term_back_items (
  id INTEGER PRIMARY KEY,
  term_id INTEGER NOT NULL REFERENCES terms(id) ON DELETE CASCADE,
  group_key TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('dict','translate','manual')),
  text TEXT NOT NULL,
  korean_def TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
-- Epic 16 as page_reads, re-keyed by day in Epic 24: reading-activity log for
-- /stats. One row per book per local day read; PRIMARY KEY + INSERT OR IGNORE
-- dedup means every later page that day is a no-op. Page numbers became
-- per-device when pagination moved client-side, so a page key no longer
-- identified the same text across devices. The pages-read *counts* were dropped
-- as unhelpful; the table survives because /api/stats derives the streak from
-- days-with-a-word-saved UNION days-with-reading — without it, a day spent
-- reading but saving nothing would break the streak. Old history was folded in
-- (db._migrate_page_reads_to_read_days), not discarded.
CREATE TABLE IF NOT EXISTS read_days (
  book_id INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
  day TEXT NOT NULL,
  PRIMARY KEY (book_id, day)
);
-- Epic 11: the subscription roster the fetch job iterates. Epic 14 seeds the full
-- curated multi-topic roster (db._SEED_FEEDS; see docs/CONTENT_CATALOG.md) and adds
-- CRUD (GET/POST/PATCH/DELETE /api/feeds) edited by the /feeds page — the user can
-- swap/enable/disable sources by hand. youtube feeds store the bare UC channel id
-- in url_or_channel_id.
CREATE TABLE IF NOT EXISTS feeds (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  type TEXT NOT NULL CHECK (type IN ('rss','youtube','scraper')),
  url_or_channel_id TEXT NOT NULL,
  topic TEXT NOT NULL DEFAULT '',
  enabled INTEGER NOT NULL DEFAULT 1,
  difficulty_min REAL,
  difficulty_max REAL,
  last_fetched TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_books_source_ref
  ON books(source_ref) WHERE source_ref IS NOT NULL;
-- Epic 13: cold-start difficulty signal. grade A (beginner/common) .. C (advanced/
-- rare); rank is a frequency rank across the whole list (lower = more frequent),
-- nullable since ~1% of source rows have no rank recorded. Seeded once from
-- server/data/vocab_levels.tsv by db._seed_vocab_levels, not hand-maintained.
CREATE TABLE IF NOT EXISTS vocab_levels (
  lemma TEXT PRIMARY KEY,
  grade TEXT NOT NULL CHECK (grade IN ('A','B','C')),
  rank INTEGER
);
```

Foreign keys ON (`PRAGMA foreign_keys=ON` per connection, set in `db.get_connection`).
Settings keys used: `decks` (JSON array of deck names, default `["Korean"]`),
`default_deck`, `translator_backend`. All columns and tables marked "Epic 9"/"Epic 11"/
"Epic 15" above are applied via `db._apply_migrations()` (additive `ALTER TABLE`s + the
partial index, guarded by `PRAGMA table_info` so re-running `init_db` never double-adds)
rather than being in the base `CREATE TABLE`, so an existing `reader.db` upgrades in
place. `status` (Epic 15) is the one additive column with a `CHECK` constraint — see
DECISIONS.md for why, a deliberate deviation from every other additive column here.
`vocab_levels` (Epic 13) is a brand-new table (`CREATE TABLE IF NOT EXISTS` directly,
same as `feeds` in Epic 11 — no migration entry needed for a new table) but its *rows*
are seeded, not hand-written: `db._seed_vocab_levels()` runs after `_apply_migrations`
in `init_db`, reads `server/data/vocab_levels.tsv`, and bulk-inserts only if the table
is currently empty (`SELECT COUNT(*)` guard), so re-running `init_db` never duplicates
the ~5,543 rows. `feeds` (Epic 15) gets its own seeding, `db._seed_feeds()` — but keyed
per-`url_or_channel_id` rather than a blanket `COUNT(*)` guard, since (unlike
`vocab_levels`) it's a small, individually-meaningful roster expected to grow by hand
across future curation sessions; a hand-added row must survive re-seeding the two
built-in feeds after an upgrade, and re-running `init_db` must never duplicate those two.

### Page splitting (`server/paging.py`, Epic 2 — implemented; row-based reader split 2026-07-24)

`split_pages(text, max_chars=1500)`: candidate break points are every position right
after a run of `. ? ! …` (optionally followed by a closing quote/bracket) or right
after a `\n`, plus `len(text)` itself. Greedily walks the text, at each step taking
the furthest break point that still fits within `max_chars` of the current position;
if none fits (a single sentence longer than `max_chars`), takes the next break point
past the limit rather than ever cutting mid-sentence — so an oversized page is
possible but a split mid-sentence is not. `split_pages("")` returns `[""]` so every
book has at least one (possibly empty) page. `difficulty.score_text`/`score_general_difficulty`
still call this with its 1500-char default, as a fixed page-size-independent reference
(see the Epic 16 DECISIONS.md entry).

**Reader pagination is client-side (Epic 24, 2026-07-27).** Between 2026-07-24 and
Epic 24 the reader used `split_pages_by_rows`/`estimate_rows`, which budgeted pages by
*estimated visual rows* using a global `chars_per_row`. That could not be made correct:
the server cannot know a device's viewport, so the estimate was wrong on every screen
and wrong by *different factors* — the same page rendered 11 lines on web and 14 on a
phone, and page length also wandered between pages, since the estimate is only wrong for
long lines. All of it (`split_pages_by_rows`, `estimate_rows`, `settings.page_rows`,
`settings.chars_per_row`, `settings.repaginate_all`, `books.current_page`) was deleted in
Epic 24 stage 2.

Today: `pages` is purely a **storage substrate** — contiguous, lossless slices, chunked
by plain `split_pages`, rejoined by `routes/books._book_text`. The reader fetches
character windows from `GET /api/books/{id}/text` (bounds sentence-aligned by
`snap_back`/`snap_forward`) and the *browser* paginates them with CSS multi-column
(`column-width: <viewport>px; column-fill: auto`, on a container whose height is N
measured line-heights), which breaks after exactly N *rendered* lines on any device.
Lines-per-page is a per-device `localStorage` value (`web/lib/reader-lines.ts`), and
reading position is a character offset (`books.current_offset`), so devices share a
position without sharing a pagination.

## API contract (all under `/api`, JSON)

| Method & path | Request | Response |
|---|---|---|
| GET `/api/health` | – | `{ok, version}` — **implemented (Epic 0)** |
| GET `/api/books` | `?topic=&archived=&source=&status=` | `[{id,title,source,current_offset,total_chars,page_count,created,coverage,new_per_page,scored_at,topic,tags,source_url,source_ref,fetched,archived,read,status,general_coverage,general_level,word_count,duration_seconds,feed_id,discard_reason}]` — `source`/`status` filters **implemented (Epic 15)**, `status` defaults to `"library"` when omitted; `topic`/`archived` (Epic 11), base shape (Epic 2), score fields (Epic 9, general fields Epic 15), `word_count`/`duration_seconds` (Epic 18), `feed_id`/`discard_reason` (Epic 19) |
| POST `/api/books` | `{title, text, source?, topic?, tags?, source_url?, source_ref?, fetched?, status?}` | created book (splits pages); 409 on duplicate `source_ref` — **implemented (Epic 2, extended Epic 11, Epic 15)**. `feed_id` is set only by `routes/feeds.py`'s internal `insert_book()` call, not exposed on this request body — manual imports/paste always leave it NULL |
| GET `/api/books/{id}` | – | `{id,title,current_offset,total_chars,page_count}` — **implemented (Epic 2)**; `current_offset`/`total_chars` Epic 24 |
| PATCH `/api/books/{id}` | `{current_offset?, title?, topic?, tags?, archived?, read?, status?}` (`current_offset` = Epic 24 reading position, `ge=0`; replaced `current_page`) | full updated book row (as `GET /api/books` shape); `status` is how the Queue promotes (`"library"`) or discards (`"discarded"`) a candidate — **implemented (Epic 2, extended Epic 11, Epic 15)**. Setting `status: "discarded"` here also stamps `discard_reason: "user"` (Epic 19) — the auto-expiry path (`POST /api/feeds/fetch`) stamps `"expired"` instead, via its own `UPDATE` |
| DELETE `/api/books/{id}` | – | 204 — **implemented (Epic 2)** |
| GET `/api/books/{id}/pages/{n}` | – | `{page_no, page_count, content, tokens, terms}` (see below) — **implemented (Epic 2)**; no longer used by the reader as of Epic 24, kept for scoring/tests |
| GET `/api/books/{id}/text?offset=&window=` | – | `{offset, total_chars, content, tokens, terms}` — the reader's own source of text as of **Epic 24**. A character-addressed slice; both ends snap **outward** to a sentence/newline boundary, so `offset` in the response may precede the one requested. Token offsets are relative to `content` (absolute = `offset + token.s`). `window` defaults to 20k chars and is capped at 50k. Stamps `last_opened` (moved here from the pages endpoint) |
| GET `/api/terms` | `?status=&deck=&q=` | `[term]` — **implemented (Epic 3)** |
| POST `/api/terms` | `{lemma, translation, notes?, status?, deck?, sentence?, forms?: [{text,kind}], examples?, back_items?: [{group,kind,text,korean_def}], source_book_id?, source_page?}` | created term (409 if lemma exists — since Epic 26 the popover answers that by offering to append onto the existing term rather than surfacing the error); `hanja` (Epic 25, a list since Epic 26) = one spelling per sense; `forms` (Epic 20, `kind` added Epic 22) = highlight aliases, `examples` (Epic 21) = legacy card-back usage examples (superseded by `back_items` for new terms, see below), `back_items` (Epic 22) = the structured card builder's Back chips — when non-empty, `translation` is derived from it (`"; ".join(text)`) rather than taken from the request; `source_*` capture where a word was first saved — **implemented (Epic 3, forms Epic 20, examples Epic 21, back_items Epic 22)** |
| PATCH `/api/terms/{id}` | any editable fields (same `forms`/`back_items` shapes) | updated term; sets `anki_dirty=1` if `translation/notes/deck/sentence/examples` changed, or `forms`/`back_items` changed, and `anki_note_id` is set; bumps `updated` — **implemented (Epic 3, back_items Epic 22)** |
| GET `/api/terms/by-lemma` | `?lemma=` | the term with exactly that lemma, or 404 — the "is this word already saved?" check behind Epic 26's append-instead-of-409 flow (the list endpoint's `q` is a LIKE across three columns and can't answer it) — **implemented (Epic 26)** |
| DELETE `/api/terms/{id}` | – | 204 — **implemented (Epic 3)** |
| POST `/api/translate` | `{text, backend?}` | `{translation, backend, cached}` (502 + `{error}` on TranslationError) — **implemented (Epic 3)** |
| GET `/api/dict?word=…` | – | krdict entries `[{word, pos, target_code, definitions, examples}]` — Epic 21 adds `target_code` + `examples` (from a per-entry krdict `view` call). Epic 29: every krdict response is cached in `translate_cache.sqlite3` (`krdict_cache`, no expiry) and the first failed request pauses krdict for 30 min (`krdict_state`); during the pause this returns 503 `{error}` — **implemented (Epic 3, examples Epic 21)** |
| POST `/api/anki/sync` | – | `{added, updated, failed:[{lemma, error}]}` — **implemented (Epic 6)** |
| GET `/api/settings` | – | `{decks, default_deck, translator_backend, candidate_retention_days, last_fetch_attempt}` — **implemented (Epic 7; `candidate_retention_days`/`last_fetch_attempt` Epic 17)**. `page_size` (Epic 16) → `page_rows`/`chars_per_row` (2026-07-24) → **all removed in Epic 24**, when lines-per-page became a per-device localStorage value. Retired keys are deleted from the `settings` table by the migration, since stored rows merge *over* DEFAULTS and would otherwise resurface |
| PUT `/api/settings` | any subset except `last_fetch_attempt` (system-managed, see below) | full settings dict after merge. No setting re-paginates anything as of Epic 24 — `repaginate_all` is gone — so this is a plain write — **implemented (Epic 7; `candidate_retention_days` Epic 17)** |
| POST `/api/import/youtube` | `{url, topic?, tags?}` | created book (source `yt`, `source_ref="yt:<video_id>"`, `duration_seconds` from yt-dlp's own metadata); 502 `{error}` if no Korean subs / fetch fails; 409 on re-import — **implemented (Epic 12, `duration_seconds` Epic 18)** |
| POST `/api/import/article` | `{url, topic?, tags?}` | created book (source `article`, `source_ref="article:<url>"`); 502 `{error}` if fetch/extract fails; 409 on re-import — **implemented (Epic 12)** |
| POST `/api/import/pdf` | multipart: `file`, `title?`, `topic?`, `tags?` (comma-separated), `pages?` (`"1-20"`) | created book (source `pdf`, `source_ref="pdf:<sha256 of file bytes>"`); 502 `{error}` if extraction fails; 409 on re-upload of the same bytes — **implemented (Epic 12)** |
| POST `/api/import/epub` | multipart: `file`, `title?`, `topic?`, `tags?` (comma-separated) | created book (source `epub`, `source_ref="epub:<sha256 of file bytes>"`); 502 `{error}` if extraction fails or the EPUB has no extractable text; 409 on re-upload of the same bytes — **implemented (EPUB import, 2026-07-23)** |
| POST `/api/import/subtitles` | multipart: `files` (**repeatable** — one or many), `title?`, `topic?`, `tags?` (comma-separated) | **Batch**, always 201 with `{imported: Book[], skipped: [{filename, reason}], failed: [{filename, error}]}` — partial success is the normal outcome of dropping a season in, so no single status code can describe it. One book per file (source `subs`, `source_ref="subs:<sha256 of file bytes>"`, `duration_seconds` from the last cue's timestamp), imported in filename order. `title` only applies when exactly one file is uploaded; a batch titles each book from its own filename. Accepts `.srt/.vtt/.smi/.ass/.ttml` and friends — **implemented (subtitle import, 2026-08-18)** |
| POST `/api/score` | `{text}` | `{coverage, new_lemmas, total_lemmas, new_per_page, general_coverage, general_level}` — general fields **implemented (Epic 15)**, personal fields (Epic 9, cold-start Epic 13) |
| POST `/api/books/{id}/score` | – | full updated book row, personal + general difficulty cached under one `scored_at` — **implemented (Epic 9, general fields Epic 15)** |
| GET `/api/feeds` | – | `[{id,name,type,url_or_channel_id,topic,enabled,difficulty_min,difficulty_max,last_fetched}]` — **implemented (Epic 14)** |
| POST `/api/feeds` | `{name, type, url_or_channel_id, topic?, enabled?, difficulty_min?, difficulty_max?}` | created feed — **implemented (Epic 14)** |
| PATCH `/api/feeds/{id}` | any editable field | updated feed — **implemented (Epic 14)** |
| DELETE `/api/feeds/{id}` | – | 204 — **implemented (Epic 14)** |
| POST `/api/feeds/fetch` | `?feed_id=` (optional) | `{checked_feeds, skipped_feed_types, candidates_created, expired, feeds:[{id,name,items_seen?,created?,skipped_duplicate?,skipped_no_subs?,failed?,fetch_error?,skipped_type?}]}` — iterates enabled feeds, inserts new items as `status='candidate'` books, dedups on `source_ref`; `rss` fetches articles (trafilatura), `youtube` pulls each new video's Korean transcript (yt-dlp; no-subs videos skipped), `scraper` skipped — **implemented (Epic 15, YouTube support Epic 14)**. Every call (regardless of `feed_id`) first stamps `settings.last_fetch_attempt` and auto-discards (`status='discarded', discard_reason='expired'`) any candidate older than `settings.candidate_retention_days`, reporting the count as `expired` — **implemented (Epic 17, `discard_reason` Epic 19)**. Every created candidate is also stamped with its `feed_id` (Epic 19) |
| POST `/api/reads` | `{book_id, page_no}` | `{counted}` — logs a page read (`INSERT OR IGNORE`, so revisits are no-ops); reader pings it after a 5s dwell — **implemented (Epic 16)** |
| GET `/api/stats` | – | `{totals, streak, activity:[{date,words,read}], new_words_per_book:[{book_id,title,new_words,days_read}], vocab_depth:{buckets,beginner_pct,total_a}, curation:{by_topic:[{topic,promoted,user_discarded,expired,pending}], by_feed:[{feed_id,feed_name,promoted,user_discarded,expired,pending}]}}` — **implemented (Epic 16, `curation` Epic 19)**. `curation` is computed only over `books` rows with `feed_id IS NOT NULL` (feed-fetched content); manual imports/paste are outside its scope by construction |

**Epic 7 status:** `server/routes/settings.py` stores each top-level settings key
as its own row in the `settings` (key/value) table, JSON-encoded in the `value`
column (so `decks` round-trips as a real array, not a comma string). `GET` merges
stored rows over `DEFAULTS = {"decks": ["Korean"], "default_deck": "Korean",
"translator_backend": "deepl"}` so a fresh DB (or one where only some keys were
ever `PUT`) still returns a complete dict. `PUT` accepts any subset of the three
keys (`exclude_unset`) and upserts only those, via `INSERT ... ON CONFLICT(key) DO
UPDATE` — so a partial `PUT` never clobbers keys it didn't mention.

`web/app/settings/page.tsx` (new): deck list (add/remove, each `PUT` after the
edit — no separate "Save" step, mirroring how `/terms`'s inline edits and the
reader popover already commit per-action rather than batching), default-deck
select, translator-backend select. `web/app/read/page.tsx` now fetches
`GET /api/settings` once per page-mount and passes `decks`/`default_deck`/
`translator_backend` down to `TokenPopover.tsx` as props (replacing its old
hardcoded `DECKS = ["Korean"]` constant from Epic 5); `TokenPopover`'s Translate
button now passes `translatorBackend` through to `POST /api/translate` instead of
always taking the `.env` `TRANSLATOR` default.

`web/app/terms/page.tsx` replaced Epic 6's bare-bones Sync-only stub with the
full page: status/deck/search filters (debounced, hitting `GET /api/terms?status=
&deck=&q=`), a term list where tapping a row switches it into an inline edit
form (lemma/translation/notes/deck/status, Save/Delete — a duplicate-lemma
rename surfaces the same 409 message the reader popover shows), and the
existing Sync button + result toast carried over unchanged.

**Epic 3 status:** `server/routes/terms.py` — full CRUD. `POST` and lemma-renaming
`PATCH` both 409 on a duplicate lemma (DB `UNIQUE` constraint caught via
`sqlite3.IntegrityError` on create; pre-checked with a `SELECT` on rename to give a
clean 409 instead of a 500). `PATCH`'s dirty-flag rule is literal to the spec table:
only a changed `translation`/`notes`/`deck`/`sentence` value sets `anki_dirty=1`, and
only when `anki_note_id IS NOT NULL` — a lemma or status edit never sets it, even
post-sync, and setting a field to its existing value doesn't either. `updated` is
bumped via `CURRENT_TIMESTAMP` in the same `UPDATE` statement on every patch.

`server/routes/translate.py` imports `translate` and `TranslationError` directly
from `translate_svc.translators`, and the `krdict` module (not just its `lookup`
function) from `translate_svc` — tests monkeypatch `server.routes.translate.translate`
and `server.routes.translate.krdict.lookup` respectively, which never touches the
real `translate_cache.sqlite3` or requires `.env` keys. `POST /api/translate` catches
`TranslationError` and returns `502 {"error": "..."}` via `JSONResponse` (not
FastAPI's default `{"detail": ...}` shape, to match the spec's contract exactly).

**Epic 11 status:** `server/db.py`'s `_ADDED_COLUMNS["books"]` grew the seven columns
in the schema block above; `_apply_migrations` also creates the partial
`idx_books_source_ref` unique index every `init_db` call (idempotent — `CREATE …
IF NOT EXISTS`). `feeds` is a brand-new table so it needed no migration entry, just
`CREATE TABLE IF NOT EXISTS` in `SCHEMA` directly. `routes/books.py`: `BookCreate`
gained `topic/tags/source_url/source_ref/fetched` (all optional, defaulting to
empty/`None`); a duplicate `source_ref` surfaces as 409 (`sqlite3.IntegrityError`
caught the same way `terms.py` handles duplicate lemmas). `BookPatch` gained
`topic/tags/archived/read`; `tags` is JSON-encoded before the `UPDATE` (same pattern
`routes/settings.py` uses). `list_books` takes `?topic=` (exact match) and
`?archived=` (bool) query filters, mirroring `terms.py`'s filter style.
`web/app/page.tsx`: a topic `<select>` + "Show archived" checkbox filter row (both
re-fetch from the server rather than filtering client-side, so they compose with the
existing client-side Recent/Easiest-unread sort); each book row shows its
topic/tags line and gained "Mark read"/"Archive" toggle buttons — both call `PATCH`
then re-fetch (rather than patching local state), since toggling either can move a
book out of the current filter view; the add-book modal gained a topic `<select>`
and a comma-separated tags `<input>`. No frontend UI for `source_url`/`source_ref`/
`fetched` yet — nothing sets those until Epic 12's importers exist; verified via API
tests directly (`test_duplicate_source_ref_returns_409`, etc.) instead.
**Not verified in a browser** (still no browser tooling in this environment; also
deliberately not run against the user's real `reader.db` to avoid polluting it with
test books) — do a real pass together with Epic 9's still-pending one.

**Epic 12 status:** `server/routes/books.py` gained `insert_book()` — the shared
page-split + `source_ref`-dedup insert (raises `DuplicateSourceRef` on collision,
caught by each caller to shape its own 409 message) — extracted out of `create_book`
so `routes/imports.py`'s three importers reuse it instead of duplicating the
INSERT/split-pages/commit logic. `import_tools/yt_subs.py`'s `fetch_subs()` now
returns `(title, text, video_id)` (was `(title, text)`) and raises a proper
`NoSubtitlesError` instead of `SystemExit` when no Korean captions exist, so it's
safe to call as a library — the CLI `__main__` block catches it and converts back to
`SystemExit` itself. `import_tools/pdf_text.py`'s `extract()` now accepts either a
`Path` (CLI, unchanged) or raw `bytes` (`fitz.open(stream=..., filetype="pdf")`, used
by the upload route — no temp file needed); `parse_page_range()` was pulled out of
the CLI's inline arg-parsing so the route can reuse the same `"1-20"` syntax.
`server/article.py` (new) wraps `trafilatura.fetch_url` + `.extract` +
`.extract_metadata`, raising `ArticleError` on an unfetchable URL or a page with no
extractable article text. Dedup keys: YouTube on `yt:<video_id>` (from yt-dlp's
`info["id"]`, stable across URL variants like `?t=30s`); article on
`article:<url>` (exact string — a differently-formatted URL to the same article
isn't detected, judged acceptable for a personal single-user app); PDF on
`pdf:<sha256 of the uploaded bytes>` (works even though PDFs have no natural id;
re-uploading the identical file always dedupes, a re-export with different bytes
won't — same rationale); EPUB on `epub:<sha256 of the uploaded bytes>` (same
byte-hash rationale as PDF). The EPUB path uses `import_tools/epub_text.py`
(`ebooklib` walks the spine in reading order; a small stdlib `HTMLParser`
subclass strips each XHTML document to text, so no BeautifulSoup dependency) and
additionally returns `502` when the extracted text is empty (a DRM'd or
image-only EPUB yields nothing to read). The fetch/extract routes catch their
exception and return `502 {"error": ...}` (matching `routes/translate.py`'s
existing convention), then catch `DuplicateSourceRef` separately for the 409.
Tests
(`server/tests/test_imports.py`) monkeypatch `imports.fetch_subs` /
`imports.fetch_article` / `imports.extract_pdf` at the route-module boundary, same
convention as `test_translate.py`; PDF upload tests exercise real multipart
`files=`/`data=` through `TestClient`. New deps: `yt-dlp`, `pymupdf`, `trafilatura`,
`python-multipart` (FastAPI needs it for `UploadFile`/`Form`) — all added to
`requirements.txt`. Real (non-mocked) sanity checks run manually against live
YouTube and a live news URL confirmed `fetch_subs`/`fetch_article` work end-to-end
(not just against mocks) — not run through the API/DB layer, per the
Epic 9/11 convention of never seeding the user's real `reader.db` from this
environment. `web/app/page.tsx`'s add-book modal gained a 4-way mode switch
(Paste/.txt, YouTube, PDF, Article URL); `lib/api.ts` gained `importYoutube`/
`importArticle`/`importPdf` plus a `requestForm` helper (skips the JSON
`Content-Type` header so the browser can set its own multipart boundary).
**Not verified in a browser** (no browser tooling in this environment) — do a real
pass: paste a YouTube URL with Korean captions, upload a PDF, paste an article URL;
confirm each lands as a scored-ready book and that re-submitting the same one 409s
instead of duplicating.

**Epic 13 status:** `server/difficulty.py` gained `COLD_START_THRESHOLD = 50` and
`frequency_grades(conn) -> dict[lemma, grade]` (a full-table read of `vocab_levels`
into a dict — ~5.5k rows, cheap enough to redo per request). `score_text` gained a
third optional parameter, `frequency`; when `len(known) < COLD_START_THRESHOLD` *and*
a frequency map was passed, the "familiar" set (used for both `coverage` and
`new_per_page`) becomes `known | {lemma for lemma with grade == "A"}` instead of just
`known` — otherwise behavior is byte-for-byte the pre-Epic-13 function (both existing
callers that never pass `frequency` are unaffected; the two-arg call shape is still
valid). Both HTTP call sites (`routes/difficulty.py`'s `POST /api/score` and
`routes/books.py`'s `POST /api/books/{id}/score`) now pass `frequency_grades(conn)`
through unconditionally — the threshold check inside `score_text` is what actually
gates whether it's used, so this is safe to always pass. `server/data/vocab_levels.tsv`
(new, committed) is a cleaned/deduped export of the 국립국어원 (NIKL) 2003 "한국어
학습용 어휘 목록" — 5,543 lemmas after stripping homograph-disambiguation suffixes
(가다01 -> 가다) and, where the same lemma appeared under multiple grades (different
senses/POS), keeping its easiest grade. `db.py` gained `vocab_levels`
(`CREATE TABLE IF NOT EXISTS`, see schema block above) and `_seed_vocab_levels()`,
called from `init_db` right after `_apply_migrations`. See DECISIONS.md for: why NIKL
grades over the actual TOPIK exam vocab list, why grade A specifically (not a
continuous weighting across A/B/C), why threshold 50, and the source-download
provenance (the file required following a session-cookie'd download link on
korean.go.kr — not a plain URL — documented there so it can be re-derived if the
list ever needs refreshing).
**Verified:** `pytest` (`test_difficulty.py`'s cold-start section, `test_db.py`'s
seeding test) exercises the fallback logic directly and end-to-end through the real
seeded table; a real live sentence pair (all-common vs. rare/advanced vocabulary) was
hand-verified against the actual `vocab_levels` grades before being hardcoded into
`RARE_STORY`/`STORY` in the test file, so the acceptance-criterion test
(`test_rare_text_scores_harder_than_common_text_with_empty_known_set`) reflects the
real data, not a guess. No frontend changes — `/score` and book-scoring already
render whatever `coverage`/`new_per_page` the API returns, so the add-book "Check
difficulty" preview and per-book score line pick up the new cold-start numbers with
no code changes needed on that side.

**Epic 15 status:** two independent additions — a general/public difficulty tag, and
a feed-fetch curation queue — plus a small source-type filter riding along since the
`source` column already existed. `server/difficulty.py` gained
`GENERAL_WEIGHTS = {"A": 1.0, "B": 0.5, "C": 0.15}` (unlisted lemmas implicitly 0.0)
and `score_general_difficulty(text, frequency) -> {general_coverage, general_level}`
— a weighted average of each unique lemma's grade weight, with **no personal `known`
set at all**; labels at `>=0.75`/`>=0.45`/else "easy"/"medium"/"hard" (recalibrated
lower than `score_text`'s 0.95/0.85 bands — see DECISIONS.md, flagged as tunable).
Shown *alongside* `score_text`'s personal `coverage`, never blended into it — the two
answer different questions. `server/db.py`: `books` gained `status` (`'library'|
'candidate'|'discarded'`, `DEFAULT 'library'`, the one additive column with a `CHECK`
— see DECISIONS.md for the deviation) and `general_coverage`/`general_level`
(cached under the same `scored_at` as `coverage`/`new_per_page`); `_seed_feeds()`
(new, keyed per-URL) inserts the two RSS feeds verified live in Epic 10 (Inven,
Ruliweb game news), called from `init_db` right after `_seed_vocab_levels`.
`server/feeds.py` (new, stdlib `xml.etree.ElementTree` only): `fetch_feed_xml`
(`httpx.get(..., follow_redirects=True)` — Inven's URL 301-redirects http→https) and
`parse_rss` (iterates `<item>`, falls back to `<link>` when `<guid>` is absent),
raising `FeedFetchError` on an unreachable URL or unparsable XML. `server/routes/
books.py` gained `_score_and_cache()`, extracted out of `POST /api/books/{id}/score`
so both that route and the new feed fetcher compute personal + general difficulty
under one `scored_at` without duplicating the scoring logic; `insert_book()` gained a
`status` parameter (default `"library"`, so every pre-Epic-15 caller is unaffected).
`server/routes/feeds.py` (new): `POST /api/feeds/fetch` (optional `?feed_id=` for
manual retry) iterates enabled feeds, skips non-`rss` types gracefully (no fetch
logic yet for `youtube`/`scraper`), checks `source_ref` *before* calling
`fetch_article` (avoids a wasted trafilatura call on an already-imported item),
inserts new items as `status="candidate"` via `insert_book()`, scores each via
`_score_and_cache()`, and isolates per-feed and per-item failures (one bad feed or
unparsable article never blocks the rest — same isolation pattern as
`anki_sync.py`'s per-note failures). `GET /api/books` gained `?source=` (exact match)
and now defaults `?status=` to `"library"` when omitted — the one behavior change to
an existing endpoint, judged safe because every book created before this epic already
defaults to `status='library'` (verified by reading every book-creation call site in
`test_books.py`/`test_difficulty.py`/`test_imports.py`). `BookPatch` gained `status`,
so the Queue's Promote/Discard reuse the existing `PATCH /api/books/{id}` — no new
endpoints for the lifecycle transition itself. Frontend: `web/lib/score-display.tsx`
(new) hoists `ScoreLine`/`coverageClass` out of `page.tsx` (unchanged behavior) and
adds `GeneralScoreLine`/`generalLevelClass`, shared by the home list and the new
`/queue` page; `web/app/page.tsx` gained a source-type `<select>` filter alongside
the existing topic filter, a general-difficulty line per book row, the general
%+label folded into the add-book "Check difficulty" preview, and a **Queue** nav
link with a candidate-count badge (`listBooks({status:"candidate"})` on mount, no
new count endpoint — matches this app's existing single-user-scale conventions);
new `web/app/queue/page.tsx` (modeled on `/terms`) lists `status="candidate"` books
with both score lines, a "Fetch new candidates" button, and Promote/Discard buttons.
**Verified:** 129/129 tests green, including real (non-mocked) sanity checks —
`server.feeds.fetch_feed_xml`/`parse_rss` against both live seeded feed URLs (25/15
items parsed correctly), and `score_general_difficulty` against Epic 13's real
STORY/RARE_STORY sentences through the actual seeded `vocab_levels` table (1.0/
"easy" vs. 0.358/"hard" — the same "rare harder than common" shape Epic 13
established). Deliberately not run through `POST /api/feeds/fetch` against the
user's real `reader.db`, per the standing convention. **Not verified in a browser**
(no browser tooling in this environment) — the Queue page and source filter join
the already-owed Epics 4-13 pass.

**Epic 17 status:** fetch automation, candidate retention, and a terminology pass.
`scripts/fetch_feeds.ps1` (new) is the Task Scheduler action — a one-shot
`Invoke-RestMethod` POST to the already-existing `/api/feeds/fetch`, logging its
result (or error) to `scripts/fetch_feeds.log`; no new server code is needed for
automation itself, since it reuses the same endpoint the Queue's manual button
calls (the user confirmed the server is expected to run continuously on
Tailscale, so no standalone DB-only fetch path was built). `routes/settings.py`
gained `candidate_retention_days` (default 7, `SettingsPut`-editable,
`ge=1,le=90`) and `last_fetch_attempt` (nullable, **deliberately absent from
`SettingsPut`** — system-stamped only, via the new `stamp_last_fetch_attempt()`
helper, using SQLite's own `CURRENT_TIMESTAMP` to match every other
TIMESTAMP-shaped value in the app). `routes/feeds.py`'s `fetch_feeds()` now does
two things before it touches any feed: stamps `last_fetch_attempt`, then runs
`_expire_stale_candidates()` — a single `UPDATE books SET status='discarded'
WHERE status='candidate' AND created <= datetime('now', '-N days')` (N from the
retention setting), reported back as a new `expired` count in the response.
Both run unconditionally on every call (scheduled, manual whole-roster, or a
single-`feed_id` retry) since the check is cheap/idempotent — see
`docs/DECISIONS.md` for why this doesn't need a separate scheduled job, and why
expiry reuses the existing `status='discarded'` value instead of a new enum
member. 171/171 tests green (8 new: `test_settings.py`'s
`candidate_retention_days` round-trip/bounds and the ignored-in-PUT-body case
for `last_fetch_attempt`; `test_feeds.py`'s expiry/retention-setting/
within-window/last-fetch-attempt-stamped-even-on-total-failure cases).
`npm run build`/`lint` clean. Frontend: `/settings` gained a "Queue candidate
retention" numeric input; the umbrella word "book(s)" was swept to **"Library"**
across nav links, the add-content modal ("Add to Library", "+ Add"), and
`/stats` headings/milestones, with **"Book"** now reserved as a small badge on
`pdf`/`epub`-sourced rows on `/` — copy-layer only, no schema/table/column/API
renaming (see `docs/DECISIONS.md`). `last_fetch_attempt`'s actual on-page
display (and the rest of the Queue UX — cards, chips, sort, length, source
link, back-to-top) is Epic 18 scope, not this one.

**Epic 18 status:** Queue browsing UX — cards, chips, sort/filter, length,
source link, back-to-top. `import_tools/yt_subs.fetch_subs()`'s return grew a
4th value, `duration_seconds` (`info["duration"]` off the yt-dlp info dict
already being read — real video length, not a transcript-based estimate);
every call site updated for the new 4-tuple: `routes/imports.py`'s `POST
/api/import/youtube`, `routes/feeds.py`'s `_process_youtube`/
`_insert_and_score` (gained an optional `duration_seconds` passthrough
parameter), and the CLI `__main__`. `books` gained two additive columns:
`word_count` (`len(text.split())`, computed in `insert_book()` for every
source, so every path — paste, all four importers, the feed fetcher — gets it
for free) and `duration_seconds` (NULL except for `source='yt'`). Frontend:
`web/lib/chips.tsx` (`SourceChip`) maps `source` → a small colored badge
(`yt`/`article` today, extendable), styled from the existing palette
tokens (`accent`/`border`/`muted`) rather than new hues, so it stays
theme-aware without touching `globals.css`. `web/lib/length.ts` exposes
`formatLength()` (exact word count or exact duration, whichever field is
non-null — never an estimate) and `estimatedMinutes()` (a 250-wpm heuristic
used *only* to rank mixed source types against each other for the "Shortest
first" sort — never displayed). `web/app/queue/page.tsx` rewritten: a Cards/
List view toggle (`localStorage["queueViewMode"]`, read after mount so the
static export's build-time render never touches `localStorage`, cards
default), a sort-by `<select>` (newest fetched / easiest first / shortest
first — "easiest" mirrors `/`'s existing `new_per_page`-ascending comparator
exactly), the Epic 17 `last_fetch_attempt` line at the top (re-fetched after
every manual "Fetch new candidates" click so it updates without a reload),
an "↗" source-link per item using the existing `source_url` column, and a
back-to-top floating button once scrolled past ~2 viewport heights. The fetch-
result panel also now surfaces Epic 17's `expired` count. 172/172 tests green
(1 new: `test_db.py`'s migration idempotency for the two new columns; existing
YouTube-import tests in `test_imports.py`/`test_feeds.py` extended with
`duration_seconds`/`word_count` assertions, and `test_books.py`'s book-shape
key-set test updated for the two new fields). `npm run build`/`lint` clean.
**Not verified in a browser** (no browser tooling in this environment) — the
card/list toggle, chips, sort, length stat, source link, and back-to-top all
join the already-owed browser/touch pass; a real feed-fetch pulling a real
YouTube video (to confirm `duration_seconds` reflects its actual length, not
an estimate) is worth doing alongside that pass.

**Epic 19 status:** Promotion stats — what gets read vs. what doesn't. `books`
gained two additive columns: `feed_id` (soft reference, no FK, same convention
as `terms.source_book_id` — set only by `routes/feeds.py`'s `_insert_and_score`
for feed-sourced candidates, NULL for every manual import/paste) and
`discard_reason` (`'user'` | `'expired'` | NULL, no `CHECK` — informational,
not a lifecycle gate). Two write sites for `discard_reason`: `routes/books.py`'s
`patch_book` sets `'user'` whenever a `PATCH` sets `status: "discarded"`;
`routes/feeds.py`'s `_expire_stale_candidates` (Epic 17's auto-expiry `UPDATE`)
sets `'expired'` in the same statement — both kept, per the SPEC's flagged
judgment call (see `docs/DECISIONS.md` for why lumping them under plain
`discarded` was rejected). `routes/stats.py` gained `_curation_breakdown()`:
one query grouping `books` by `(topic, feed_id, status, discard_reason)` over
rows with `feed_id IS NOT NULL`, folded in Python into `by_topic`/`by_feed`
arrays of `{promoted, user_discarded, expired, pending}` counts (`status`
directly gives `promoted`/`pending`; `discarded` rows split by
`discard_reason`). `by_feed` `LEFT JOIN`s `feeds` for the display name and
falls back to `"(deleted feed #<id>)"` if the feed was since deleted — feed
deletion never touches the books it produced. 176/176 tests green (7 new:
`test_db.py` migration idempotency for the two columns; `test_feeds.py`'s
candidate-creation tests extended with `feed_id` assertions and the expiry
test extended with a `discard_reason == "expired"` assertion; `test_books.py`'s
manual-discard test extended with `discard_reason == "user"`, plus its
book-shape key-set test updated for the two new fields; `test_stats.py` gained
`_insert_curation_book()` plus tests for the empty case, a multi-topic/
multi-feed aggregation across all four buckets, and a deleted-feed fallback
name). `npm run build`/`lint` clean. Frontend: `web/lib/api.ts` gained
`CurationCounts`/`CurationByTopic`/`CurationByFeed` types and `Stats.curation`;
`web/app/stats/page.tsx` gained a "What gets promoted" section (two stacked-bar
breakdowns, by topic and by feed, hand-rolled SVG/CSS — no new npm dependency,
same convention as every other `/stats` chart) rendered after `VocabDepth`.
**Not verified in a browser** (no browser tooling in this environment) — joins
the already-owed pass; also worth confirming with real feed activity (promote
a few candidates, let a few expire, discard a few by hand) that the by-topic/
by-feed bars actually look meaningful at real-world counts, not just in tests.

**Page payload** (the core endpoint, implemented in Epic 2):
```json
{
  "page_no": 3, "page_count": 12,
  "content": "그는 옷을 입고 나갔다. …",
  "tokens": [ {"s": 7, "e": 9, "surface": "입고", "lemma": "입다", "pos": "VV"}, … ],
  "terms":  { "입다": {"id": 5, "lemma": "입다", "translation": "to wear", "notes": "", "status": "learning", "deck": "Korean", "forms": [], "examples": [], "back_items": []}, … }
}
```
Epic 22: `notes` and `back_items` were added here (previously missing entirely — the
reader's tap-to-edit popover gets its prefill from *this* endpoint, not `/api/terms`,
so it needs the full card-builder state) and `forms` entries gained `kind`; reuses
`routes/terms.py`'s own `_forms_for`/`_back_items_for` rather than a third copy of
the query.
`tokens` covers every eojeol with a resolvable lemma (`s`/`e` are char offsets into
`content`). `terms` contains saved terms whose lemma **or one of its Epic-20 `forms`**
appears in this page's tokens; keyed by the matched string (direct lemma wins over a
form of the same string), each entry carrying `lemma` + `forms`. The frontend renders
spans from offsets and applies the highlight class when
`token.lemma in terms && status === 'learning'`.

## Tokenizer (`server/tokenizer.py`, Epic 1 — implemented)

`kiwipiepy.Kiwi()` module-level singleton (`_kiwi`). `_kiwi.tokenize(text)` returns
`Token(form, tag, start, len)` namedtuples sorted by `start`.

Algorithm — group morphemes into **eojeols** via `re.finditer(r"\S+", text)` (runs of
non-whitespace, so a trailing/attached punctuation mark stays part of the eojeol, e.g.
`"갔다."`), assign each eojeol the morphemes whose `start` falls in `[eojeol.start,
eojeol.end)`, then pick the eojeol's *primary* morpheme from its first one or two
morphemes:

1. **하다-derivations first:** morpheme[0] tagged `NNG/NNP/XR` and morpheme[1] tagged
   `XSV`/`XSA` → lemma = morpheme[0].form + `하다` (공부했어요 → 공부하다), pos = `VV`
   if the suffix was `XSV`, `VA` if `XSA`.
2. Else morpheme[0] tag **starts with** `VV`, `VA`, or `VX` → lemma = form + `다` (입고
   → 입다, 갔다 → 가다, 예뻐요 → 예쁘다). `pos` = the literal kiwi tag, unnormalized —
   see deviation below.
3. Else morpheme[0] tagged exactly `NNG NNP NNB NR NP MAG MAJ IC` → lemma = form
   (학교에 → 학교, 사람들이 → 사람).
4. Else (eojeol is only particles/endings/symbols/numbers, or a copula `VCP`/`VCN`) →
   emit no token for it.

Returns `list[Token]` (frozen dataclass: `surface`, `s`, `e`, `lemma`, `pos`). Wrong
guesses are acceptable — the UI lets the user edit the lemma before saving; a crash or
a `text[s:e] != surface` mismatch is the only real bug.

**Deviation from the spec's literal rule 2 wording:** kiwi tags irregular-conjugation
stems with a suffixed subtag (`VV-R`, `VV-I`, `VA-I`, …), not the bare `VV`/`VA`/`VX`
the spec's prose implies — verified directly against 입고 (`VV-R`), 들어요/돕다
(`VV-I`), 더워요 (`VA-I`). Rule 2 therefore matches by tag **prefix**. See
`docs/DECISIONS.md` (2026-07-21).

## Frontend spec (`web/`, Epic 4+)

Next.js 16.2.10, React 19, App Router, TypeScript, Tailwind v4. **Mobile-first** —
primary device is a phone. Visual design (Epic 28): indigo palette tokens in
`app/globals.css` (light + dark), Noto Sans KR via `next/font/google`, and one button
language (`.btn-primary` / `.btn-secondary` / `.btn-link` / `.btn-quiet` / `.field`
component classes in `globals.css`). Config: `output: 'export'`,
`images: { unoptimized: true }`, `trailingSlash: true` (required — see below); dev
uses `next.config` rewrites `/api/* → http://localhost:8002/api/*` (build-time
no-op for the static export, ignored with a warning; only takes effect under `next
dev`, where FastAPI must be separately running on 8002).

Routes:
- `/` — **implemented (Epic 4).** Book list (title, progress as a percentage of
  `current_offset/total_chars` — Epic 24; page numbers are per-device now) drawn
  as a thin bar. Cards in the Queue's layout (Epic 28 follow-up): source chip +
  topic/tags, title, progress, scores, and a solid Start/Continue button; score /
  read / edit / source / archive live in a per-card "⋯" menu, Archive last, so it
  is never one stray tap from the title. Sort is a select, filters fold behind a
  "Filters" button with an active count. `app/page.tsx` holds the list;
  `app/LibrarySheets.tsx` the Add to Library and Edit details sheets, built on
  `lib/sheet.tsx` (`Sheet`, `Field`, `TopicPicker` chips, `FilePicker`).
- `/read/?id=<bookId>` — **implemented (Epic 4 rendering, Epic 5 tooltip flow).**
  `app/read/page.tsx`. Renders `content` as spans using `tokens` offsets; only
  tokens whose lemma is in `terms` with status `learning` get a highlight
  (`bg-highlight` with vertical padding, so it fills the line height without moving
  text; the tapped token turns solid accent while its popover is open, Epic 28).
  Prev/next moves one CSS column and `PATCH`es `current_offset` (best-effort — a
  failed PATCH doesn't block navigation). Progress is a percentage, not a page
  number (Epic 24), shown since Epic 28 as `ProgressStations` under the header: a
  stop at every 10%, the reader on the nearest one, exact % under it.
  **Not `/read/[bookId]` as SPEC literally names it** — see "Deviations" below.

  **Tap/selection handling (Epic 5):** one delegated `onClick` on the `<article>`
  container (not per-span handlers). It checks `window.getSelection()` first — a
  non-empty selection is treated as a phrase (SPEC's "long-press drag" case), using
  the raw selected text as both surface and lemma, and its first-occurrence offset
  in `content` (via `indexOf`) as the center point for sentence extraction. Otherwise
  it resolves `e.target.closest('[data-token-index]')` to find which token span (if
  any) was tapped — every span carries `data-token-index`, not just highlighted
  ones, since untapped words must open the "new term" flow too.

  **Popover (`app/read/TokenPopover.tsx`):** editable lemma input; Translate
  (`POST /api/translate` on the current lemma value → fills the translation
  textarea); Dictionary (`GET /api/dict` on the current lemma value → renders
  entries inline, read-only, doesn't touch the textarea); Translate sentence
  (`POST /api/translate` on the extracted sentence → shown as read-only reference
  text, also not written into the textarea — the user copies by hand into their own
  enriched translation, matching CLAUDE.md's "hand-enrich the translation"). Deck
  `<select>` — see deviation 4 below. Save: if the popover opened on a token/phrase
  that already had a saved term (any status, not just `learning`), `PATCH`s that
  term's id; otherwise `POST`s a new one with `status: "learning"` — this create/
  edit mode is fixed at popover-open time, not re-decided at save time. A 409 from
  a rename-into-an-existing-lemma surfaces the backend's message directly. Mark
  known / Ignore (`PATCH status`) and Delete only render when the popover opened on
  an existing term. `sentence` is sent on every save (current tap context), even
  when editing — there's no "only set sentence once" special case.

  **Instant client-side highlight refresh on save (SPEC §7):** `page.terms` is
  updated in React state from the `Term` the API returns — no refetch. If the save
  renamed the lemma, the old key is deleted from the local map so a stale entry
  doesn't linger. Verified directly against a live server that this produces the
  exact behavior SPEC describes *and* its edge case: saving a lemma correction that
  no other token's own tokenizer-lemma matches means, correctly, that no span
  highlights after a reload — see `docs/DECISIONS.md` 2026-07-21 ("Highlighting
  stays exact-lemma-match...").
- `/terms` — table (filter: status, deck, search); tapping a row opens
  `TokenPopover` (Epic 22 follow-up, 2026-07-24 — see below) instead of the old
  flat inline `TermEditRow` (removed), closing the gap Epics 20/21 left ("management
  page does not yet edit forms/examples") — `bookId`/`pageNo` are passed `null`
  since they're only read on the create path and every `/terms` edit is an existing
  term. "Sync to Anki" button + `{added, updated, failed}` toast unchanged.
- `/settings` — deck list editor, default deck, translator backend, page-size
  controls, retention days.

  **Epic 22 popover rewrite** (the flat translation textarea + "Also highlight"
  input above are gone): the lemma input stays, followed by centered Translate/
  Dictionary buttons, the captured context sentence, then a live read-only Front→
  Back chip preview — a true WYSIWYG of the Anki card, one row per Front entry
  with its own Back chips inline after a `→` (not two independent columns, which
  desync visually the moment group sizes differ — a decluttering pass after the
  first real try-out), colored by provenance (lemma + manual entries orange,
  dictionary-derived chips a blue family paling as more are added this session,
  Translate results green), each chip deletable (deleting a Front form cascades to
  its Back items). Dictionary results: clicking a headword adds/attaches its Front
  chip (deduped by exact text against the lemma and existing chips) plus its first
  sense as a Back item and that sense's Korean definition into the Examples
  preview; every sense is independently clickable to add more Back items to the
  same group. Translate appends a Back item under the lemma's group rather than
  overwriting anything. An "Examples" preview (exactly that label, matching the
  real Anki field — not "Notes") shows one deletable line per active Korean
  definition and a free-typed textarea (`notes`) underneath — the reading sentence
  itself is shown once, above the buttons, not repeated here. A manual "Add entry"
  form (Front text + Back text) creates its own independent group, guarded by a
  duplicate-text check — the hand-enrichment path now that Front/Back chips
  themselves aren't freely typable. A term with no `back_items` yet (never touched
  by this system) shows its old flat translation read-only, labeled "(legacy)" —
  no forced migration. Status actions (isEditing only) show "Mark learning"/"Mark
  known"/"Ignore" — each hidden when it matches the term's current status — plus
  Delete; the `/terms` reuse needed the "learning" direction, which the reader
  context alone never did.

Keep dependencies minimal: Next + Tailwind only; no state library (React context/props
suffice), no component kit. Small shared `lib/api.ts` fetch wrapper (typed, throws
on non-2xx, reads `{error}`/`{detail}` from the body when present) plus `lib/
sentence.ts`'s `extractSentence(content, centerIndex)`, a client-side reimplementation
of `server/paging.py`'s sentence-boundary heuristic (same break-character class:
`. ? ! …` or a newline) — used to fill the popover's `sentence` field without a
server round-trip.

**Deviations from this section (Epic 4, both forced by `output: 'export'`; full
reasoning in `docs/DECISIONS.md` 2026-07-21):**
1. **Reader route uses a query string, not a dynamic segment.** Static export
   requires every dynamic route (`[bookId]`) to be enumerable at build time via
   `generateStaticParams()`; book IDs are created at runtime and are unbounded, so
   they can't be. `/read` is one static route; the id comes from `?id=` via
   `useSearchParams()` (wrapped in `<Suspense>`, which Next requires for search
   params in a prerendered route).
2. **`trailingSlash: true` is required**, not optional, in this stack. Static
   export's default output for a route named `read` is a flat `out/read.html`.
   Starlette's `StaticFiles(html=True)` (`server/main.py`'s static mount) only
   auto-resolves a *directory* path to `index.html` — it does not append `.html`
   to a bare path — so `GET /read/` would 404 without this. With
   `trailingSlash: true`, export emits `out/read/index.html` instead, which
   resolves correctly.
3. **Removed `next/font/google` (Geist) from the default scaffold.** It fetches
   font files from Google Fonts at build time; kept the layout on the system font
   stack instead to avoid an unnecessary external-network build dependency.
   **Reversed in Epic 28** for Noto Sans KR (see `docs/DECISIONS.md` 2026-10-07):
   `next build` now needs network unless the font is already in `.next/cache`.
4. **(Epic 5) Deck select is hardcoded to `["Korean"]`**, not sourced from
   `GET /api/settings` — that route is Epic 7 scope and doesn't exist yet. See
   `docs/DECISIONS.md` 2026-07-21.

## Anki sync spec (`server/anki.py` + `routes/anki_sync.py`, Epic 6 — implemented)

AnkiConnect at `http://127.0.0.1:8765` (POST JSON `{action, version: 6, params}`);
Anki desktop with the AnkiConnect add-on (code 2055492159) is already installed from
the Lute setup.

Sync algorithm:
1. `version` ping — if unreachable, return 503 `{error: "Anki is not running (or
   AnkiConnect missing)"}`.
2. For each deck referenced by pending terms: `createDeck` (idempotent).
2b. **Epic 21:** `ensure_model()` — create the custom two-way note type
   `"Korean Reader 2-way"` once (idempotent, guarded on `modelNames`). Fields
   `Korean`/`English`/`Examples`; two card templates (KO→EN Front `{{Korean}}`,
   EN→KO Front `{{English}}`) that **both** put `{{Examples}}` on the back only —
   studying either direction never spoils the prompt. Best-effort like `createDeck`.
3. New: terms `status='learning' AND anki_note_id IS NULL` → `addNote` on the **Epic 21
   two-way model** (fields still `Korean`/`English`/`Examples` — unchanged since Epic
   21), tags `["korean-reader"]`, `options.allowDuplicate: false`. Content **(Epic 22)**:
   `Korean` = the lemma alone if it has no forms (unchanged simple case), else a
   numbered stack (`1. 승인<br>2. 승인서`); if the term has any `term_back_items` rows,
   `English`/`Examples` render from them — one line per item, lettered (`1a.`/`1b.`)
   when its front entry has 2+ items, otherwise a bare number or no label at all,
   `Examples` also carrying the reading sentence first and the free-typed `notes`
   last; a term with **zero** `term_back_items` (never touched by the Epic 22 popover)
   renders `English`/`Examples` exactly as before this epic — flat `translation`, the
   old `examples` JSON column + sentence. Store the returned id **and stamp
   `anki_model` with the model name**, clear dirty. On per-note error (e.g. duplicate)
   record in `failed`, continue.
4. Dirty: terms `anki_dirty=1 AND anki_note_id NOT NULL` → **branch by `anki_model`**:
   the two-way model → `updateNoteFields` with `Korean`/`English`/`Examples` (same
   Epic 22 rendering as above); a legacy `Basic` note (`anki_model` NULL, synced before
   Epic 21) → the old Front/Back `updateNoteFields` (Front = lemma+forms, now also
   numbered when 2+; Back = translation + `<br><br><i>sentence</i>`), so its SRS
   scheduling history is preserved. On success clear `anki_dirty`.
5. Return counts. Never delete Anki notes; `known`/`ignored` terms are simply not
   synced (existing notes left alone).

**Epic 22 rendering helpers** (`routes/anki_sync.py`): `_front_entries()` builds the
ordered `[lemma, *forms]` list; `_label_items()` pairs every back item with its
display label (front-entry index + a/b/c letter when its group has 2+ items) — Back
and Examples both render from this *same* labeled list, so `1a.` always means the
same back item in both fields. `_render_two_way()` is the single entry point that
picks the legacy-vs-structured branch (zero vs. non-zero `term_back_items` rows) so
`sync()` itself doesn't need to know which. `server/anki.py` is **unchanged** — the
model's third field really is called "Examples" (confirmed against a live Anki
install; an earlier assumption that it should be renamed "Notes" was wrong), only the
content built for `English`/`Examples` changed.

**Epic 6 status:** `server/anki.py`'s `_invoke()` is the single choke point for every
AnkiConnect call (`httpx.post`, 5s timeout) — raises `AnkiError` on transport failure
or a non-null `error` field in the response body, which `routes/anki_sync.py` turns
into the 503 (ping) or a per-term `failed` entry (add/update). A term's `deck` column
defaults to `''` in the schema, but AnkiConnect needs a real deck name, so an empty
deck falls back to the literal string `"Default"` (Anki's own built-in default deck)
— only reachable for hand-seeded/legacy terms, since the UI's deck `<select>` always
has a value. Tests monkeypatch the functions on the `anki` module directly (same
pattern as `translate.py`'s `krdict` module-level patching), plus one test patching
`httpx.post` itself to cover `_invoke`'s transport-error branch per SPEC's "mock the
AnkiConnect HTTP layer" wording. `web/app/terms/page.tsx` is a bare-bones stub (just
a "Sync to Anki" button + `{added, updated, failed}` result) — the full filterable
table is Epic 7 scope; see `docs/DECISIONS.md`.

## Ops & Lute retirement (Epic 8 — implemented)

`translate_svc/main.py` (Lute's HTML tooltip page, served on :8001) is deleted — the
user confirmed they've fully switched to korean-reader, so it's no longer live and
nothing else imports it (`server/routes/translate.py` only ever imported
`translate_svc.translators`/`translate_svc.krdict`, never `.main`). `translate_svc/`'s
other modules (`translators.py`, `cache.py`, `krdict.py`, `config.py`) are unchanged,
still imported as a library. `%LOCALAPPDATA%\Lute3` (Lute's own reading-history DB) was
deliberately left alone — it's the user's data, nothing in this repo touches it, and
deleting it isn't this repo's call to make.

`start.ps1` rewritten from a two-process Lute+translator launcher into a single-app
one: rebuilds `web/` only if any source file under `web/` (excluding
`node_modules`/`.next`/`out`) is newer than the newest file in `web/out` (a plain
`LastWriteTime` comparison — no build-hash tracking, since a single-user local app
doesn't need one), then launches `uvicorn server.main:app --host 0.0.0.0 --port 8002`
in its own window and opens the browser at `http://localhost:8002`. `--host 0.0.0.0`
(rather than the implicit `127.0.0.1`) is what makes the server reachable from a phone
over Tailscale/LAN at all — binding to loopback only would make the Tailscale setup in
`README.md` a dead end.

`README.md` rewritten for korean-reader (daily use, `.env` setup, a pointer to
`ANKI.md`, and full Tailscale phone-access steps: install on PC and phone, find the
MagicDNS name, the Windows Firewall prompt for `--host 0.0.0.0`, the actual phone URL).
Import-tools usage (`yt_subs.py`, `pdf_text.py`) carried over unchanged.

**Not yet done, deliberately:** the user asked for retirement + deployment docs without
actually "going live" yet — so the end-to-end cold-start run (`start.ps1` from a closed
state → server up → phone over Tailscale) has not been executed. See `docs/STATUS.md`.
