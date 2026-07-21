# Architecture

This document describes the app **as built**. It starts as a copy of `docs/SPEC.md`
sections 3–8 (the plan) and must be amended whenever an epic's implementation diverges
from the plan — this file always describes the code as it currently is, not the
original intent. See `docs/DECISIONS.md` for the reasoning behind divergences.

## Layout

```
korean-reader/
  server/                  FastAPI app, port 8000
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

- New Python deps: `kiwipiepy` (no system deps, works on Windows), plus existing
  `fastapi`, `uvicorn`, `httpx` already in `.venv`.
- Port **8000** (Lute keeps 5001 and translate_svc 8001 during the transition — no
  clashes).
- Node.js required for the `web/` build. If Node is missing on the machine, tell the
  user to install Node LTS and stop (`needs input`), don't work around it.

**Epic 0 status:** `server/main.py` exposes an app factory `create_app(db_path=None)`
returning a FastAPI app whose `lifespan` calls `db.init_db(path)` on startup (not at
import time) — this lets tests point at a temp DB via `create_app(tmp_path / "test.db")`
without ever touching the real `reader.db`. Module-level `app = create_app()` is the
uvicorn entrypoint (`uvicorn server.main:app --port 8000`) and uses the default path
(`reader.db` at repo root). Only `GET /api/health` exists so far; `web/out` static
mount is wired but inert until Epic 4 creates that directory. `routes/` package exists
but is empty until Epic 2 onward. `.venv` was created with Python 3.10 (`py -3.10 -m
venv .venv`) per kiwipiepy's Windows compatibility story.

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
Page splitting at import: split text into pages of ≤ ~1500 chars, breaking only at
sentence ends (`.` `?` `!` `…` `다.` patterns / newlines); never split mid-sentence.
Settings keys used: `decks` (JSON array of deck names, default `["Korean"]`),
`default_deck`, `translator_backend`.

## API contract (all under `/api`, JSON)

| Method & path | Request | Response |
|---|---|---|
| GET `/api/health` | – | `{ok, version}` — **implemented (Epic 0)** |
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

Everything except `/api/health` is unimplemented as of Epic 0 (`routes/` is empty).

**Page payload** (the core endpoint, Epic 2):
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

## Frontend spec (`web/`, Epic 4+ — not yet scaffolded)

Next.js (latest stable), App Router, TypeScript, Tailwind CSS. **Mobile-first** —
primary device is a phone. Clean, modern, uncluttered. Config: `output: 'export'`; dev
uses `next.config` rewrites `/api/* → http://localhost:8000/api/*`.

Routes:
- `/` — book list (title, progress `current_page/page_count`), "Add book" modal: title
  + paste-textarea or `.txt` upload.
- `/read/[bookId]` — the reader: renders `content` as spans using `tokens` offsets.
  Base text plain; only tokens whose lemma is in `terms` with status `learning` get a
  subtle highlight. Tap a token → popover: surface, editable lemma input, Translate /
  Dictionary / Translate-sentence buttons, editable translation textarea, deck select,
  Save. Tap a highlighted token → same popover pre-filled, plus mark known / ignore /
  delete. Text selection → same popover with raw selection as lemma. Page prev/next
  with `current_page` persistence. Sentence extraction: previous sentence-end to next
  sentence-end around the token.
- `/terms` — table (filter: status, deck, search), inline edit, delete, "Sync to
  Anki" button showing `{added, updated, failed}` toast.
- `/settings` — deck list editor, default deck, translator backend (deepl/claude).

Keep dependencies minimal: Next + Tailwind only; no state library (React context/props
suffice), no component kit. Small shared `lib/api.ts` fetch wrapper.

## Anki sync spec (`server/anki.py` + `routes/anki_sync.py`, Epic 6 — not yet
implemented)

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
