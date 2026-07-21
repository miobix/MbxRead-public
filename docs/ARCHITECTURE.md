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
    anki.py                AnkiConnect client (http://localhost:8765)
    routes/
      books.py  terms.py  translate.py  anki_sync.py  settings.py
  server/tests/            pytest suite
  translate_svc/           used as a library (translators.py, cache.py, krdict.py,
                           config.py) — main.py (Lute's HTML tooltip page) deleted
                           in Epic 8, Lute is fully retired
  web/                     Next.js app (TypeScript, Tailwind, output: 'export')
  import_tools/            existing
  docs/                    living design docs (see Executor conventions)
  requirements.txt         direct Python deps
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

Foreign keys ON (`PRAGMA foreign_keys=ON` per connection, set in `db.get_connection`).
Settings keys used: `decks` (JSON array of deck names, default `["Korean"]`),
`default_deck`, `translator_backend`.

### Page splitting (`server/paging.py`, Epic 2 — implemented)

`split_pages(text, max_chars=1500)`: candidate break points are every position right
after a run of `. ? ! …` (optionally followed by a closing quote/bracket) or right
after a `\n`, plus `len(text)` itself. Greedily walks the text, at each step taking
the furthest break point that still fits within `max_chars` of the current position;
if none fits (a single sentence longer than `max_chars`), takes the next break point
past the limit rather than ever cutting mid-sentence — so an oversized page is
possible but a split mid-sentence is not. `split_pages("")` returns `[""]` so every
book has at least one (possibly empty) page.

## API contract (all under `/api`, JSON)

| Method & path | Request | Response |
|---|---|---|
| GET `/api/health` | – | `{ok, version}` — **implemented (Epic 0)** |
| GET `/api/books` | – | `[{id,title,source,current_page,page_count,created}]` — **implemented (Epic 2)** |
| POST `/api/books` | `{title, text, source?}` | created book (splits pages) — **implemented (Epic 2)** |
| GET `/api/books/{id}` | – | `{id,title,current_page,page_count}` — **implemented (Epic 2)** |
| PATCH `/api/books/{id}` | `{current_page?, title?}` | updated book — **implemented (Epic 2)** |
| DELETE `/api/books/{id}` | – | 204 — **implemented (Epic 2)** |
| GET `/api/books/{id}/pages/{n}` | – | `{page_no, page_count, content, tokens, terms}` (see below) — **implemented (Epic 2)** |
| GET `/api/terms` | `?status=&deck=&q=` | `[term]` — **implemented (Epic 3)** |
| POST `/api/terms` | `{lemma, translation, notes?, status?, deck?, sentence?}` | created term (409 if lemma exists) — **implemented (Epic 3)** |
| PATCH `/api/terms/{id}` | any editable fields | updated term; sets `anki_dirty=1` if `translation/notes/deck/sentence` changed and `anki_note_id` is set; bumps `updated` — **implemented (Epic 3)** |
| DELETE `/api/terms/{id}` | – | 204 — **implemented (Epic 3)** |
| POST `/api/translate` | `{text, backend?}` | `{translation, backend, cached}` (502 + `{error}` on TranslationError) — **implemented (Epic 3)** |
| GET `/api/dict?word=…` | – | krdict entries as JSON list — **implemented (Epic 3)** |
| POST `/api/anki/sync` | – | `{added, updated, failed:[{lemma, error}]}` — **implemented (Epic 6)** |
| GET `/api/settings` | – | `{decks, default_deck, translator_backend}` — **implemented (Epic 7)** |
| PUT `/api/settings` | any subset of the above | full settings dict after merge — **implemented (Epic 7)** |

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

**Page payload** (the core endpoint, implemented in Epic 2):
```json
{
  "page_no": 3, "page_count": 12,
  "content": "그는 옷을 입고 나갔다. …",
  "tokens": [ {"s": 7, "e": 9, "surface": "입고", "lemma": "입다", "pos": "VV"}, … ],
  "terms":  { "입다": {"id": 5, "translation": "to wear", "status": "learning", "deck": "Korean"}, … }
}
```
`tokens` covers every eojeol with a resolvable lemma (`s`/`e` are char offsets into
`content`). `terms` contains only saved terms whose lemma appears in this page's
tokens. The frontend renders spans from offsets and applies the highlight class when
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
primary device is a phone. Clean, modern, uncluttered. Config: `output: 'export'`,
`images: { unoptimized: true }`, `trailingSlash: true` (required — see below); dev
uses `next.config` rewrites `/api/* → http://localhost:8002/api/*` (build-time
no-op for the static export, ignored with a warning; only takes effect under `next
dev`, where FastAPI must be separately running on 8002).

Routes:
- `/` — **implemented (Epic 4).** Book list (title, progress
  `current_page/page_count`), "Add book" modal: title + paste-textarea or `.txt`
  upload → `POST /api/books`. `app/page.tsx`, both the list and the modal in one
  file (single small component, no separate `components/` dir yet).
- `/read/?id=<bookId>` — **implemented (Epic 4 rendering, Epic 5 tooltip flow).**
  `app/read/page.tsx`. Renders `content` as spans using `tokens` offsets; only
  tokens whose lemma is in `terms` with status `learning` get a highlight
  (`bg-amber-200/70 dark:bg-amber-300/25`). Page prev/next `PATCH`es
  `current_page` (best-effort — a failed PATCH doesn't block navigation).
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
- `/terms` — not yet built (Epic 7).
- `/settings` — not yet built (Epic 7).

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
4. **(Epic 5) Deck select is hardcoded to `["Korean"]`**, not sourced from
   `GET /api/settings` — that route is Epic 7 scope and doesn't exist yet. See
   `docs/DECISIONS.md` 2026-07-21.

## Anki sync spec (`server/anki.py` + `routes/anki_sync.py`, Epic 6 — implemented)

AnkiConnect at `http://localhost:8765` (POST JSON `{action, version: 6, params}`);
Anki desktop with the AnkiConnect add-on (code 2055492159) is already installed from
the Lute setup.

Sync algorithm:
1. `version` ping — if unreachable, return 503 `{error: "Anki is not running (or
   AnkiConnect missing)"}`.
2. For each deck referenced by pending terms: `createDeck` (idempotent).
3. New: terms `status='learning' AND anki_note_id IS NULL` → `addNote` (`modelName:
   "Basic"`, Front = lemma, Back = translation + `<br><br><i>sentence</i>` when
   present, tags `["korean-reader"]`, `options.allowDuplicate: false`). Store returned
   id, clear dirty. On per-note error (e.g. duplicate) record in `failed`, continue.
4. Dirty: terms `anki_dirty=1 AND anki_note_id NOT NULL` → `updateNoteFields` with the
   same field rendering; on success clear `anki_dirty`.
5. Return counts. Never delete Anki notes; `known`/`ignored` terms are simply not
   synced (existing notes left alone).

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
