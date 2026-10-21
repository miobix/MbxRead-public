# Project status — read this first, update it last

**MbxRead** (renamed 2026-10-14 from korean-reader / MbxAndria). **Live and in daily use since
2026-07-24.** All planned epics are done; future work is ad-hoc user requests and polish, not
a fixed backlog.

This file is **living state**: it describes what is true *now*. When something is finished,
its detail is *removed* from here — the full narrative of every epic lives in `git log` and
`docs/DECISIONS.md`, so nothing is lost by pruning. Keep this file short enough that "read
this first" is actually realistic. See `docs/README.md` for what each doc is for.

## What the app is, right now

Read Korean texts → tap a word → translate (DeepL/krdict) → hand-enrich into a structured
Anki card → save the term by dictionary form so every inflection highlights → bulk-sync to
Anki. Content arrives two ways: manual import (paste/txt/YouTube/PDF/EPUB/subtitle
files/article) and an automated feed roster (RSS + YouTube) that fetches candidates into a
review Queue. A difficulty scorer (personal coverage + a NIKL-vocab general signal) tells you
a text's cost before you commit. A `/stats` screen tracks reading and vocabulary growth.
Sino-Korean words get their own hanja deck and note type, fed by the `/hanja` and
`/hanja-today` study skills. FastAPI + SQLite + kiwipiepy backend, Next.js static-export
frontend served by FastAPI, phone access over Tailscale.

**Test suite: 326 passing** (`.venv\Scripts\python.exe -m pytest server/tests -q`).
`web/`: `npm run build` and `npm run lint` clean.

## Epic checklist

Full write-up for any line is in `git log` (commit `Epic N: …`) and `docs/DECISIONS.md`.

- [x] **0** — Repo, scaffolding, docs; app factory + lifespan DB init
- [x] **1** — Tokenizer (kiwipiepy wrapper, lemma-based, table-driven tests)
- [x] **2** — Books & pages API + sentence-aware paging
- [x] **3** — Terms & translate APIs (DeepL/krdict, dirty-flag rules)
- [x] **4** — Frontend scaffold, book list, reader rendering + highlighting
- [x] **5** — Tooltip flow (tap → translate → edit → save)
- [x] **6** — Anki sync (AnkiConnect add/update) — verified live against Anki desktop
- [x] **7** — Terms & settings pages
- [x] **8** — Ops chapter + Lute retirement (Lute fully retired)
- [x] **9** — Difficulty scorer (personal coverage / new-per-page)
- [x] **10** — Content catalog (`docs/CONTENT_CATALOG.md`, non-code)
- [x] **11** — DB expansion (topic/tags/source_ref/feeds table) + library UX
- [x] **12** — Import wiring (YouTube / article / PDF)
- [x] **13** — Cold-start difficulty signal (NIKL graded vocab, `vocab_levels`)
- [x] **14** — Curated feed roster + feeds CRUD/`/feeds` page + YouTube fetch
- [x] **15** — Curation Queue + general-difficulty score + source-type filter
- [x] **16** — `/stats` screen + UI makeover (reading log, provenance)
- [x] **—** — EPUB import (ad-hoc, between 16 and 17)
- [x] **17** — Fetch automation (Task Scheduler), candidate retention, "Library" terminology
- [x] **18** — Queue browsing UX (cards/list, chips, sort/filter, length, source link)
- [x] **19** — Promotion stats (what gets read vs. discarded/expired)
- [x] **20** — Term forms/aliases + highlighting fix
- [x] **21** — Dictionary click-to-add + krdict examples + two-way Anki note type
- [x] **22** — Structured Front/Back/Examples card builder
- [x] **—** — Pre-go-live storage/UI pass (queue-text auto-purge, rebrand, Library/Queue pagination)
- [x] **23** — Go-live: `start.ps1`, Tailscale phone access, Task Scheduler fetch job
- [x] **—** — Background tray launcher (ad-hoc)
- [x] **24** — Client-side reader pagination + Library nav/card pass
- [x] **—** — Subtitle-file import (`.srt/.vtt/.smi/.ass/.ttml`, batch) + Library card edit (ad-hoc)
- [x] **25** — Save-a-word: on-demand hanja terms, own deck + `Korean Reader Hanja` note type
- [x] **26** — Multi-hanja terms: one lemma, an ordered list of hanja senses, one note
- [x] **27** — `/hanja` study skill (one character per run; `Hanja::*` decks read-only)
- [x] **28** — Visual redesign (indigo palette, Noto Sans KR, metro-station progress)
- [x] **29** — Local hanja pipeline (libhangul word list) + `/hanja-today` daily list
- [x] **—** — Over-engineering cleanup, 2026-10-21 (dead migrations, legacy Basic sync,
  `/pages/{n}`, scraper feed type; see `DECISIONS.md`)

## Live operational facts

- **Server runs on port 8002.** Port 8000 belongs to an unrelated Docker-based Android sync
  service on this machine — don't use it or kill things on it without checking; 5001/8001
  were the legacy Lute setup. No app code hardcodes the port (passed via `uvicorn --port`).
- **Two launchers.** `start.ps1` = the *dev* launcher (visible console, rebuilds `web/` if
  stale). `scripts/tray_app.py` = the *daily* launcher — hidden uvicorn + tray icon
  (Open / Restart / Quit), auto-started at logon via a **Startup-folder shortcut**
  (`shell:startup`), *not* Task Scheduler (logon-trigger registration hits Access Denied in
  this environment). Server output → `scripts/server.log` (gitignored).
- **Feed fetch** is a daily 06:00 Task Scheduler job (`scripts/fetch_feeds.ps1` → `POST
  /api/feeds/fetch`, `-WindowStyle Hidden`, logs to `scripts/fetch_feeds.log`).
  **Paused 2026-07-27** — task `MbxRead fetch feeds` is *Disabled*, because reading
  is currently focused on one book and the queue was accumulating unread text. Re-enable
  with `Enable-ScheduledTask -TaskName 'MbxRead fetch feeds'` (trigger/action are
  unchanged; nothing else was touched).
- **Tailscale** address: `<machine>.<tailnet>.ts.net` — phone reaches the app at
  `http://<machine>.<tailnet>.ts.net:8002`.
- **Reader pagination is client-side.** The browser breaks pages with CSS columns after
  exactly N rendered lines; N lives in **localStorage per device** (`readerLines`, default
  15, editable on `/settings`). The footer shows a percentage, not a page number. Position is
  `books.current_offset`, a character offset, so devices stay in sync.
- **Storage** is one plain SQLite `reader.db`; `pages.content` holds raw text in ~1500-char
  slices (storage only; the reader reads `GET /api/books/{id}/text?offset=`). As of go-live:
  ~200 books / 1.14M chars / 3.7MB. Discarded article/yt candidates have their `pages` text
  auto-purged; paste/pdf/epub/txt text is kept indefinitely.
- **Hanja study deck** is `STUDY_DECK` in `server/hanja_study.py` (currently 4급-II); change
  it when the user moves on. `/hanja-today` writes `hanja_output/<date>.md` (gitignored).
- **Schema upgrades are additive only** (`_ADDED_COLUMNS` in `server/db.py`). The one-time
  Epic 24/26 migrations were removed 2026-10-21; a `reader.db` backup older than Epic 26
  must be opened with a checkout from before commit `6d7eb08` to upgrade it.

## Open follow-ups (not blockers)

- **Two small bugs found by the 2026-10-21 audit** (for a `/code-review` pass):
  `score_book` joins pages with `"\n"` while `/text` joins them with `""`, so a score sees
  slightly different text than the reader; and the Claude translator is selectable in
  Settings but `anthropic` is not in `requirements.txt`.
- **Audit items 11–15 not done:** the term-without-back_items rendering branches in
  `anki_sync.py` (check whether `/terms` can still create one first), `html_unescape` wrapper
  in `import_tools/yt_subs.py`, `score_book` reusing `_book_text`, the duplicate `except` in
  `import_subtitles`, and the one-caller `_group_key`.
- **One feed still errors:** `김성회의 G식백과` (YouTube) hit a transient Atom-feed fetch
  error during the go-live run. Worth a manual retry; reads as network/rate-limit.
- **Live-Anki two-way card check:** worth confirming once, on a real sync, that a
  multi-sense word's card matches the popover preview.
- **Epic 28 light mode** was only checked in dark mode; worth one look on a light-mode device.

## Gotcha for future dev sessions

- On Windows, a background `uvicorn` started by a Bash-tool `&` job can outlive its call and
  squat on the port. If a fresh run fails to bind: `netstat -ano | grep :8002` then
  `taskkill //PID <pid> //F`.
- Tests must pass offline with no API keys: mock DeepL/Claude/krdict/AnkiConnect HTTP, temp
  sqlite per test.
