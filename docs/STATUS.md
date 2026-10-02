# Project status — read this first, update it last

**MbxAndria** (internal repo name: korean-reader). **Live and in daily use since
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
files/article) and an automated feed roster that fetches candidates into a review Queue. A difficulty scorer
(personal coverage + a NIKL-vocab general signal) tells you a text's cost before you commit.
A `/stats` screen tracks reading and vocabulary growth. FastAPI + SQLite + kiwipiepy backend,
Next.js static-export frontend served by FastAPI, phone access over Tailscale.

**Test suite: 311 passing** (`.venv\Scripts\python.exe -m pytest server/tests -q`).
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
- [x] **16** — `/stats` screen + UI makeover (page-read logging, provenance)
- [x] **—** — EPUB import (ad-hoc, between 16 and 17)
- [x] **17** — Fetch automation (Task Scheduler), candidate retention, "Library" terminology
- [x] **18** — Queue browsing UX (cards/list, chips, sort/filter, length, source link)
- [x] **19** — Promotion stats (what gets read vs. discarded/expired)
- [x] **20** — Term forms/aliases + highlighting fix
- [x] **21** — Dictionary click-to-add + krdict examples + two-way Anki note type
- [x] **—** — Row-based reader pagination + Library source link + Queue filters (ad-hoc)
- [x] **22** — Structured Front/Back/Examples card builder (+ same-day follow-up: `/terms`
  editing parity via the shared popover, 422-error-message fix, popover decluttering)
- [x] **—** — Pre-go-live storage/UI pass: queue-text auto-purge, **rebrand to
  "MbxAndria"**, dark-mode `<select>` contrast fix, palette bump, Library/Queue pagination
- [x] **23** — Go-live: cold-start `start.ps1`, Tailscale phone access, Task Scheduler fetch
  job — all verified live
- [x] **—** — Background tray launcher (ad-hoc)
- [x] **24** — Client-side reader pagination (both stages) + Library nav/card pass
- [x] **—** — Subtitle-file import (ad-hoc, 2026-08-18): `.srt/.vtt/.smi/.ass/.ttml`,
  batch upload for a whole season, source `subs`. Text shaping: SubStation tags
  stripped for every format, dash-prefixed speaker turns kept on their own lines,
  2 s of silence becomes a paragraph break. Speaker *names* need an SDH/CC track —
  a plain track has none to give.
- [x] **—** — Library card edit affordance (ad-hoc, 2026-08-18): an `edit` button in the
  card's action column opens a modal for title / topic / tags. `PATCH /books/{id}` already
  took all three — the UI was the only gap.
- [x] **25** — Save-a-word: on-demand hanja term entry, separate deck + note type
  (`Korean Reader Hanja`: Korean/Hanja/English/KoreanDef, Hanja on its own line under
  Korean on the Front — it disambiguates homographs like 제일 祭日 vs 第一, so it can't be
  the thing under test). Entry point: "Add word" on `/terms` reuses `TokenPopover`. Verified
  live: krdict origin/homograph display, save, and a real AnkiConnect sync. Grew out of a
  separate Hanja-study exploration (`hanja/`, not part of the app) that tried and abandoned
  full deck automation — see `hanja/DECISIONS.md`. Same-day follow-up (2026-09-02): the
  `/terms` deck filter didn't include `hanja_deck`, and picking a dictionary *definition*
  (vs. the headword itself) never captured krdict's `origin` into the Hanja field — both
  fixed, plus a save-time guard requiring Hanja non-empty from this entry point. The Hanja
  note type also deliberately ships with only one card direction (Korean+Hanja→English);
  a reverse card is a manual add in Anki desktop, safe because `ensure_hanja_model()` never
  touches an existing model.
- [x] **26** — Multi-hanja terms (2026-09-09): a lemma now holds an *ordered list* of hanja
  senses (시장 = 市場 market + 市長 mayor), not one spelling. `terms.hanja` is a JSON list
  (backfilled in place, no table rebuild), a sense's meanings are its `term_back_items`
  group, and the card renders both as numbered stacks that line up (`1. 市場 / 2. 市長`
  against `1. market / 2. mayor`). Still **one row and one Anki note per lemma**, so
  appending a sense updates the existing note and keeps its SRS history. A lemma that's
  already saved no longer dead-ends on the 409: the popover checks on the Enter that fires
  the dictionary lookup (`GET /api/terms/by-lemma`), banners what's already there, and turns
  Save into "Append to <lemma>"; the preview shows the merged card before you commit and
  `/terms` lists every sense after. See `docs/DECISIONS.md` for why the alternative
  (`UNIQUE(lemma, hanja)`, one note per sense) was rejected.
- [x] **27** — `/hanja` study skill (2026-10-02): one character per run, from the user's
  Anki queue to saved terms. krdict origin search supplies real candidates (modifier
  derivatives dropped by rule, shown on request), annotated with a corpus count over the
  user's books, NIKL rank and homographs; the skill shows up to 3 per usage category and
  appends senses through `save`, or converts a reading-saved word in place (`--convert`).
  The `Hanja::*` Anki decks are read-only to it. Logic is
  `server/hanja_study.py` + `scripts/hanja_study.py`; rationale in `docs/DECISIONS.md`.

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
  **Paused 2026-07-27** — task `korean-reader fetch feeds` is *Disabled*, because reading
  is currently focused on one book and the queue was accumulating unread text. Re-enable
  with `Enable-ScheduledTask -TaskName 'korean-reader fetch feeds'` (trigger/action are
  unchanged; nothing else was touched).
- **Tailscale** address: `<machine>.<tailnet>.ts.net` — phone reaches the app at
  `http://<machine>.<tailnet>.ts.net:8002`.
- **Reader pagination is client-side** (Epic 24). The browser breaks pages with CSS columns
  after exactly N rendered lines; N lives in **localStorage per device** (`readerLines`,
  default 15, editable on `/settings`) — your phone and the laptop each keep their own. The
  footer shows a percentage, not a page number, because page numbering is now per-device.
  Position is `books.current_offset`, a character offset, so devices stay in sync.
- **Storage** is one plain SQLite `reader.db`; `pages.content` holds raw text (tokens
  computed on read). Since Epic 24 `pages` is *storage only* — the reader reads
  `GET /api/books/{id}/text?offset=`, not `/pages/{n}`. As of go-live: ~200 books / 1.14M chars / 3.7MB — nowhere near a
  constraint. Discarded article/yt candidates have their `pages` text auto-purged (Epic 17
  retention + the storage pass); paste/pdf/epub/txt text is kept indefinitely.

## Open follow-ups (not blockers)

- **One feed still errors:** `김성회의 G식백과` (YouTube) hit a transient Atom-feed fetch
  error during the go-live run, correctly isolated from the other 14 feeds. Worth a manual
  retry to confirm it clears; reads as network/rate-limit, not a regression.
- **Live-Anki two-way card check:** Epics 21–22 built a custom two-way note type
  (KO→EN / EN→KO, examples on the back of both, front of neither) and numbered/lettered
  Front/Back stacks, but were implemented without a live Anki desktop in the build
  environment. Worth confirming once, on a real sync, that a multi-sense word's card
  matches the popover preview and that pre-Epic-21 `Basic` notes still update in place
  without losing SRS history.
- A **fuller per-screen UI makeover** was always wanted "later" — current styling
  (warm-paper palette, the go-live contrast bump) is a baseline, not final.

## Gotcha for future dev sessions

- On Windows, a background `uvicorn` started by a Bash-tool `&` job can outlive its call and
  squat on the port. If a fresh run fails to bind: `netstat -ano | grep :8002` then
  `taskkill //PID <pid> //F`.
- Tests must pass offline with no API keys: mock DeepL/Claude/krdict/AnkiConnect HTTP, temp
  sqlite per test.
