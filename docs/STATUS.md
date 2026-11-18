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
review Queue. "Similar usage" in the word popover finds the word in other library
sentences ranked by sense (embeddings) and a local LLM names the sense (unit 5). A difficulty scorer (personal coverage + a NIKL-vocab general signal) tells you
a text's cost before you commit. A `/stats` screen tracks reading and vocabulary growth.
FastAPI + Postgres + kiwipiepy backend, Next.js static-export frontend served by FastAPI,
all in Docker compose on `127.0.0.1`, phone access through `tailscale serve` (unit 10).

**Test suite: 315 passing** (`.venv\Scripts\python.exe -m pytest server/tests -q`; needs
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
- **Daily launcher is compose** (unit 4): `docker compose up -d --build` runs the app (8002),
  Postgres with pgvector (`db`, `127.0.0.1:5433`), `embed` (bge-m3, `127.0.0.1:8081`) and
  `ollama` (`gemma4:e4b`, `127.0.0.1:11434`, runs on CPU: see follow-ups); `restart: unless-stopped` brings both back when
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
- **Network:** compose publishes 8002 on `127.0.0.1` only (no auth; the LAN can't reach
  it). `tailscale serve --bg --http=8002 localhost:8002` forwards it to the tailnet: the
  phone opens `http://<pc-name>:8002`. Plain HTTP by choice (no cert, so the `ts.net`
  name stays out of certificate-transparency logs). Serve routes by hostname: a bare
  `100.x` IP gets 404. This PC's Tailscale reports a DNS-config health warning ("Unable
  to remove the file to be replaced"); harmless so far.
- **Backups:** the `backup` service dumps nightly into `./backups` (newest 14 kept);
  `docker compose logs backup` shows each run. Restore steps: README, "Moving machines".
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
| 5 | RAG as same-sense usage search: pgvector, keyword/vector/hybrid compared, local LLM explains | done |
| 6 | Eval: how often the local LLM's Explain line is right, on the unit 5 labeled set | done |
| 7 | Router: cheap vs strong model, only if unit 6 shows the cheap one fails often | not justified: gemma right ~96% (unit 6) |
| 8 | Blind audits (six agents) + ponytail audit; one curated fix list | done: pick list in `docs/UNIT_8_AUDIT.md` |
| 9 | Audit fixes: Anki sync crash safety, cutover script guard, duplicate-import rollback, lemma re-sync, EPUB/upload caps | done (PR #9, with unit 8) |
| 10 | The move: compose is the daily app, local only, cutover, nightly backups, LICENSE | done (PR #10) |
| 11 | Public demo on GitHub Pages (static, seeded with real model output) | done (PR #2), live on Pages |
| 12 | Terraform pipeline with the Docker provider, local + CI | done (`infra/`, CI job `infra`) |
| 13 | Finishing: README as the run-it-locally guide, `docs/FEATURES.md` as the project explainer (screenshots, diagrams, demo link) | done |
| — | Oracle Always Free | deferred; private only if ever |

**Cutover done (unit 10, 2026-11-17):** the compose stack is the daily app with the real
library. The private repo's tray is stopped and its Startup shortcut moved to
`C:\Personal\MbxRead\MbxRead tray.lnk.retired`; its `reader.db` is untouched, as a
fallback until the compose app has been used for a while.

**Units 6-7 swapped (user, 2026-11-16).** Unit 6's eval says the router has no job yet
(`gemma4:e4b` names the right sense ~96% of the time; misses are 차다-like). Revisit only
if real use shows wrong Explain lines; it would be modelled on Strands' decider
(https://strandsagents.com/blog/amazon-saves-millions-replacing-sonnet-with-strands-decider/).
Unit 5-6 numbers and failure cases: `docs/DECISIONS.md` (2026-11-16).

**Units 8-9 (2026-11-17):** six blind agents + `/ponytail-audit` produced the pick list
`docs/UNIT_8_AUDIT.md`; unit 9 fixed items 1 and 3-6. One PR for both units. Item 2 (LAN
exposure, no auth) is issue #1, deferred to the move off this PC, when remote access
changes anyway; a login is not a priority. The rest
of the list is open for later units. Agent trial notes and the audit incident:
`DECISIONS.md`.
Phone / accessibility audit deliberately left out: front-end only, belongs with the
aesthetics pass.

**Re-published 2026-11-18:** `miobix/MbxRead-public` was recreated, public, from a
rewritten history (DECISIONS 2026-11-18); old PRs #1-10 and issue #8 are gone. Ruleset on
`main` (PR required, checks `test`, `web`, `image`); Pages from GitHub Actions; audit item 2
is issue #1. The GHCR package `mbxread` grants the new repo Write under "Manage Actions
access" (a recreated repo loses it).

**Live demo:** https://miobix.github.io/MbxRead-public/ (unit 11, PR #2, deployed by the
`pages` job on every push to `main`).

**Next:** the roadmap is complete. Open choice: make the `infra` CI job a required check on `main`.

**PRs at the user's pace:** the user reviews each unit before it becomes a PR. Finish
units as local commits on their branch; push and open the PR only when asked.

**Units 10-13 (user, 2026-11-17):** scope in SPEC. No paid hosting; the roadmap ends
after unit 13. Unit 10 lifts the unit 4 cutover deferral.

## Open follow-ups (not blockers)

- **Ollama GPU:** CUDA init fails inside WSL2 (`cuInit failed: named symbol not found`)
  though `nvidia-smi` works in containers; Ollama runs on CPU (~3 s per explanation).
  Likely an NVIDIA driver / Docker Desktop update. Compose already requests the GPU.
- **Revisit the model containers** (user, unit 5): each model got its own container to
  start with; review what runs where once it has been used for a while.

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
