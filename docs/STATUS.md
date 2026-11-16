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
FastAPI + Postgres + kiwipiepy backend, Next.js static-export frontend served by FastAPI,
all in Docker compose, phone access over Tailscale.

**Test suite: 275 passing** (`.venv\Scripts\python.exe -m pytest server/tests -q`; needs
`docker compose up -d db`).
`web/`: `npm run build` and `npm run lint` clean.

## Checklist: epics 0–32 (solo development)

Full write-up for any line is in `git log` (commit `Epic N: …`) and `docs/DECISIONS.md`.
Later work is numbered as units in the roadmap below (naming: `docs/README.md`).

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
- [x] **17** — Fetch automation, candidate retention, "Library" terminology (scheduled job
  removed in 32)
- [x] **18** — Queue browsing UX (cards/list, chips, sort/filter, length, source link)
- [x] **19** — Promotion stats (what gets read vs. discarded/expired)
- [x] **20** — Term forms/aliases + highlighting fix
- [x] **21** — Dictionary click-to-add + krdict examples + two-way Anki note type
- [x] **22** — Structured Front/Back/Examples card builder
- [x] **—** — Pre-go-live storage/UI pass (queue-text auto-purge, rebrand, Library/Queue pagination)
- [x] **23** — Go-live: `start.ps1`, Tailscale phone access
- [x] **—** — Background tray launcher (ad-hoc; removed in unit 4)
- [x] **24** — Client-side reader pagination + Library nav/card pass
- [x] **—** — Subtitle-file import (`.srt/.vtt/.smi/.ass/.ttml`, batch) + Library card edit (ad-hoc)
- [x] **25–27** — Hanja terms, multi-sense hanja, hanja study skill (removed in 32)
- [x] **28** — Visual redesign (indigo palette, Noto Sans KR, metro-station progress)
- [x] **29** — Hanja word-list pipeline (removed in 32)
- [x] **—** — Over-engineering cleanup, 2026-10-21 (dead migrations, legacy Basic sync,
  `/pages/{n}`, scraper feed type; see `DECISIONS.md`)
- [x] **30** — Add batch (removed in 32)
- [x] **31** — Sync marks Anki-mature terms `known` (dotted underline in reader); Terms
  newest first, 50 at a time
- [x] **32** — Removed in-app hanja (deck, note type, multi-sense UI, Add batch) and the
  scheduled fetch; old DBs open unchanged (roadmap unit 0)

## Live operational facts

- **Server runs on port 8002.** Port 8000 belongs to an unrelated Docker-based Android sync
  service on this machine — don't use it or kill things on it without checking. No app code hardcodes the port (passed via `uvicorn --port`).
- **Daily launcher is compose** (unit 4): `docker compose up -d --build` runs the app (8002)
  and Postgres (`db`, `127.0.0.1:5433`); `restart: unless-stopped` brings both back when
  Docker Desktop starts. The Windows tray launcher was deleted. `start.ps1` = the *dev*
  launcher (compose db + uvicorn in a visible console, rebuilds `web/` if stale); stop the
  compose app first, both want 8002.
- **Port 5432 is not ours:** an unrelated native Windows Postgres service holds it.
- **CI** (`.github/workflows/ci.yml`): jobs `test`, `web`, `image` on every PR and push
  to `main`; all three are required to merge. Pushes to `main` publish
  `ghcr.io/miobix/mbxread:latest` and `:<sha>`.
- **Feed fetch is manual:** the Queue's "Fetch new candidates" button (`POST
  /api/feeds/fetch`). Each fetch also expires stale candidates and stamps
  `last_fetch_attempt`.
- **Tailscale** address: `<machine>.<tailnet>.ts.net` — phone reaches the app at
  `http://<machine>.<tailnet>.ts.net:8002`.
- **Reader pagination is client-side.** The browser breaks pages with CSS columns after
  exactly N rendered lines; N lives in **localStorage per device** (`readerLines`, default
  15, editable on `/settings`). The footer shows a percentage, not a page number. Position is
  `books.current_offset`, a character offset, so devices stay in sync.
- **Python 3.14.10 everywhere:** the repo's `.venv` (`pip install -r requirements-dev.txt`)
  and the Docker image run the same version; the suite passes on both.
- **Storage is one Postgres database** (`DATABASE_URL`, volume `mbxread-pg`), caches
  included; no SQLite anywhere. `TZ` in `.env` sets the local day for reads and stats.
  `pages.content` holds raw text in ~1500-char slices (storage only; the reader reads
  `GET /api/books/{id}/text?offset=`). Discarded article/yt candidates have their `pages`
  text auto-purged; paste/pdf/epub/txt text is kept indefinitely.
- **Schema changes:** new columns are `ADD COLUMN IF NOT EXISTS` lines in `init_db`.
  Removed features leave their columns in place (`terms.hanja`, unused since Epic 32).
- **Old SQLite data:** `scripts/sqlite_to_pg.py` copies a pre-unit-4 `reader.db` into an
  empty database once. A `reader.db` older than Epic 26 needs a checkout from before
  `6d7eb08` first.

## Next: grow the app (2026-11-13)

**Goal:** take MbxRead from a single-machine desktop app to something that runs anywhere and
does more with its texts. Every unit is a branch + PR. Bring your own API keys: `.env` is
never committed; copy `.env.example`.

| # | Unit | State |
|---|---|---|
| 0 | Remove the hanja feature and the Windows Task Scheduler automation | done (Epic 32) |
| 1 | Dockerfile for the API | done |
| 2 | Compose: API + static web, env file for keys | done |
| 3 | CI: GitHub Actions, pytest + `npm run build` + `npm run lint`, required check, image to GHCR | done |
| 4 | SQLite to Postgres migration, in compose and CI | done; live cutover deferred |
| 5 | RAG: several retrieval pipelines compared on public-domain Korean texts, pgvector | **next** |
| 6 | Agent: a model "decider" that routes between cheap and strong models | |
| 7 | Eval: eval set + LLM judge on the unit 5-6 data, quality vs cost | |
| 8+ | Later: cloud deploy with Terraform, MLflow, vLLM, Kubernetes, a queue | |

**Unit 4 cutover: deferred by the user (2026-11-16).** The private repo's tray stays the
daily app for now; don't propose the switch unprompted. When asked: stop the private repo's tray (`C:\Personal\MbxRead`, live
on 8002) and remove its `MbxRead tray.lnk` Startup shortcut, run `sqlite_to_pg.py` on its
`reader.db` + `translate_cache.sqlite3` into the empty compose db, `docker compose up -d
--build`, check counts, turn on Docker Desktop's start-at-sign-in.

**Unit 5:** build several pipelines (chunking, embeddings, hybrid or keyword search) and
record where each fails. Public-domain Korean texts only, for the repo, tests and any demo.
Needs pgvector: swap the `db` image for a pgvector build of the same Postgres major.

**Unit 6:** modelled on Strands' decider
(https://strandsagents.com/blog/amazon-saves-millions-replacing-sonnet-with-strands-decider/).
Translation already calls DeepL/Claude, so the router has a real job.

**Before the first deploy:** add a LICENSE (MIT is the usual pick). A remote server can't
reach desktop Anki, so the deploy unit adds CSV export (Anki imports CSV natively).

## Open follow-ups (not blockers)

- **Live sync through Docker not yet exercised:** compose points at
  `host.docker.internal:8765`, but Anki was closed when unit 2 was verified. Try one sync
  with Anki open.
- **Local yt-dlp has no JS runtime** (deno is only in the image). YouTube import works
  today with a deprecation warning; install deno locally if it stops.
- **Aesthetics later:** the design is dark-mode only, by choice. Deployment comes first.
- **Content idea: early-school basics (2026-10-23).** Everyday terms a Korean picks up in
  elementary school: grammar and linguistics words (자모, 자음, 모음, 받침…), the names of each
  자모 (기역, 니은, 디귿…), school-subject vocabulary. No feature or scope decided yet.

## Gotcha for future dev sessions

- On Windows, a background `uvicorn` started by a Bash-tool `&` job can outlive its call and
  squat on the port. If a fresh run fails to bind: `netstat -ano | grep :8002` then
  `taskkill //PID <pid> //F`.
- Tests must pass offline with no API keys: mock DeepL/Claude/krdict/AnkiConnect HTTP, a
  temp Postgres DB per test (`db_url`). Use `127.0.0.1`, never `localhost`, in Postgres
  URLs on Windows: `localhost` stalls on IPv6.
