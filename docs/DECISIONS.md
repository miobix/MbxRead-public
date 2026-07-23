# Decision log (append-only)

## 2026-07-19 — Rebuild from scratch instead of extending Lute
Lute keys terms by surface text; the user needs lemma-based terms (save 입다, highlight
입고/입은/입었어요…), a deliberate tap→tooltip→translate→save flow instead of
all-words-clickable, and hand-editable lemma+translation. All three fight Lute's core
design. `translate_svc/` (DeepL/Claude + cache + krdict) is reused as a library.

## 2026-07-19 — kiwipiepy for Korean morphology
Pure-pip, no system deps, works on Windows/Py3.10. Heuristic eojeol→lemma mapping is
acceptable because the UI lets the user correct the lemma before saving.

## 2026-07-19 — Remote access via Tailscale, no auth code
App stays on the user's PC; tailnet-private. Public deploy + login explicitly out of scope.

## 2026-07-19 — Anki: AnkiConnect pool-sync, no .apkg files
User wants words to accumulate with per-word deck assignment and be pushed manually in
bulk from the PC; edits must UPDATE existing notes (store `anki_note_id`), never duplicate.
Downloads (.apkg) rejected as bothersome.

## 2026-07-19 — Frontend: Next.js static export served by FastAPI
User rejected Jinja ("ugly and clunky") and asked for Next.js. Static export keeps
production to a single uvicorn process; `next dev` for development.

## 2026-07-19 — 3 word statuses
learning (highlighted, synced) / known (plain, not synced) / ignored. Lute's 1–5 scale
deemed unnecessary UI.

## 2026-07-21 — venv on Python 3.10, not the system's newer default
The machine has 3.10, 3.12 (x2), and Anaconda's python on PATH; `py -3.10 -m venv
.venv` was used explicitly since SPEC assumes 3.10 for kiwipiepy compatibility. 3.10
installed kiwipiepy 0.23.2 cleanly with no build step needed.

## 2026-07-21 — Tokenizer rule 2 matches verb tag by prefix, not exact tag
kiwipiepy tags irregular-conjugation verb/adjective stems with a suffixed subtag —
`VV-R` (ㄹ-irregular, e.g. 입다), `VV-I` (ㄷ-irregular, e.g. 듣다/돕다), `VA-I`
(ㅂ-irregular, e.g. 덥다) — rather than the bare `VV`/`VA`/`VX` SPEC §6 rule 2 shows
in its examples. Verified via direct `kiwi.tokenize()` probing on 입고, 들어요, 더워요,
도와요, 갔다. `tokenizer.py` matches `tag.startswith(("VV","VA","VX"))` so these
common irregular verbs still resolve; `pos` on the emitted token is left as the exact
kiwi tag (e.g. `VV-R`) rather than normalized, since SPEC only requires "pos (tag of
chosen morpheme)".

## 2026-07-21 — Oversized single-sentence pages allowed over mid-sentence splits
`paging.split_pages` prioritizes "never split mid-sentence" over the ~1500-char page
size target: if one sentence alone exceeds `max_chars` (no break point found within
the limit), it takes the next available break point past the limit rather than
cutting the sentence. An oversized page is a minor UX cost; a torn sentence would
break tokenizer offsets' usefulness to the reader.

## 2026-07-21 — Translate/dict tests mock at the route module boundary, not httpx
`server/routes/translate.py` imports the `translate` function by name from
`translate_svc.translators`, so tests monkeypatch `server.routes.translate.translate`
directly rather than `translate_svc.translators.translate` (patching the latter
wouldn't affect the already-bound name in the route module) or `httpx.post` (which
would still exercise `translate_svc.cache`, writing to the real
`translate_cache.sqlite3` — forbidden by CLAUDE.md). `krdict` is imported as a
module, not a bare function, so `server.routes.translate.krdict.lookup` and
`translate_svc.krdict.lookup` are the same object and either patch target works.

## 2026-07-21 — DB init moved to FastAPI lifespan, not app-factory call time
`create_app()` only registers a `lifespan` handler that calls `db.init_db(path)`;
init doesn't run at import/factory-call time. This lets `server/main.py` be imported
(and `create_app()` called with a temp path) in tests without ever touching the real
`reader.db`, while `uvicorn server.main:app` still initializes the real DB on actual
startup via the same lifespan hook.

## 2026-07-21 — Highlighting stays exact-lemma-match even right after a correction
SPEC §5 defines highlighting as `token.lemma in terms && status === 'learning'` —
purely a string match against each token's own (fixed, tokenizer-computed) lemma.
Verified directly: created a term for 입다 (matching the 입고 token, which
highlighted correctly), then renamed it to 착용하다 via PATCH (simulating "tap a
highlighted token → edit lemma → Save"). On a fresh page reload, *no* token
highighted anymore — because 입고's own computed lemma is still 입다, and the terms
map no longer has that key. This is correct per the literal spec rule, but means
SPEC §11's manual-check wording ("hand-correct a bad lemma guess; highlight follows
the corrected lemma") only holds for *other* occurrences whose own tokenizer lemma
matches the corrected string, not necessarily the exact instance that was tapped, if
its own tokenizer guess differs from the correction. No special-case "instance
override" was added — the plain rule is simpler, matches the spec's own words, and
avoids client/server highlight state diverging after a reload.

## 2026-07-21 — Deck select is hardcoded to `["Korean"]` pending Epic 7
SPEC §7's popover needs a deck `<select>` "from settings, default `default_deck`",
but `GET/PUT /api/settings` is explicitly Epic 7 scope (SPEC §10), and building it
now would preempt that epic's own deliverable and blur epic boundaries.
`web/app/read/TokenPopover.tsx` hardcodes `DECKS = ["Korean"]` (matching section 4's
own default) with a `TODO(Epic 7)` comment, plus a fallback that adds an existing
term's deck to the option list if it's some other value (so editing a
hand-seeded/legacy term with a different deck doesn't silently blank the select).
Replace with real settings once Epic 7 builds that route.

## 2026-07-21 — Sentence extraction reimplemented client-side, mirroring paging.py
"Current sentence extracted around the tap point" (SPEC §7) needs to run against
`page.content` in the browser — there's no API round-trip for it. `web/lib/
sentence.ts`'s `extractSentence()` uses the same break-character class as `server/
paging.py` (`[.?!…]` or a newline) to find the previous/next sentence boundary
around a character index. Verified against a live server: for "그는 옷을 입고
나갔다. 날씨가 좋았다." tapping 입고 (offset 6) extracts exactly "그는 옷을 입고
나갔다." — the first sentence, correctly excluding the second.

## 2026-07-21 — Click-delegated tap/selection handling, not per-span handlers
`read/page.tsx` uses one `onClick` on the `<article>` container rather than a
handler per token `<span>` (~10-50+ spans per page). Inside it: check
`window.getSelection()` first — if non-empty, treat it as a phrase selection
(SPEC's "long-press drag" case) and use the raw selected text as the lemma; else
fall back to `e.target.closest('[data-token-index]')` to resolve which token (if
any) was tapped. This single delegated handler correctly disambiguates a plain tap
from a drag-selection without double-firing, since a plain click always collapses
any prior selection before the handler runs.

## 2026-07-21 — Dropped next/font/google (Geist) from the create-next-app default
The scaffold's `app/layout.tsx` used `next/font/google` to self-host Geist Sans/Mono,
which fetches font files from Google's CDN during `next build`. Replaced with the
system font stack (no font import at all) to keep the build free of an external
network dependency — relevant since this app is meant to build reliably on the
user's PC without assuming reliable internet at build time.

## 2026-07-21 — `npm run lint` is now part of the pre-commit check, not just `tsc`
`next build`'s TypeScript pass didn't catch a real bug: `app/read/page.tsx` called
`setState` synchronously inside a `useEffect` body for the "no book id in URL" case,
which `eslint-plugin-react-hooks`'s `react-hooks/set-state-in-effect` rule flags
(can cause cascading renders). Fixed by deriving that condition at render time
instead of storing it in the async `error` state meant for fetch failures. `npm run
build` alone would not have caught this — `npm run lint` must run too from Epic 4
on.

## 2026-07-21 — Reader route is `/read/?id=<bookId>`, not `/read/[bookId]`
SPEC §7 names the reader route `/read/[bookId]`. With `output: 'export'`, Next.js
requires every dynamic route segment to be enumerable at build time via
`generateStaticParams()` (confirmed against the bundled Next 16 docs —
`node_modules/next/dist/docs/.../static-exports.md` explicitly lists "Dynamic Routes
without `generateStaticParams()`" and "with `dynamicParams: true`" as **unsupported**
for static export). Book IDs are created at runtime after deployment and are
unbounded, so they can't be enumerated at build time. Used a single static `/read`
route instead, reading the book id from `?id=` via `useSearchParams()` (wrapped in a
`Suspense` boundary per Next's requirement for search params in prerendered routes).
FastAPI's static mount doesn't care about the query string, so this has no server-side
cost. `web/next.config.ts` also sets `trailingSlash: true`, since static export's
default output (`out/read.html`) isn't resolvable by Starlette's
`StaticFiles(html=True)` (which only auto-serves `index.html` for a *directory* path,
not `<name>.html` for a bare path) — `trailingSlash: true` makes export emit
`out/read/index.html` instead, which does resolve for `GET /read/`.

## 2026-07-21 — Bugs found during the Epic 4/5 manual visual/touch pass
The user did the overdue browser pass and hit three real issues, fixed same-day:
1. **`sqlite3.ProgrammingError` on the very first request after boot.** FastAPI runs
   sync generator dependencies (`db.get_db`) in a worker-thread pool via anyio, and
   the pool doesn't guarantee the thread that opens the connection is the same one
   that later closes it — `sqlite3.connect()` defaults to `check_same_thread=True`
   and refuses that. Fixed by passing `check_same_thread=False` in
   `db.get_connection()`; safe here because a given connection is still only ever
   touched by one logical request at a time, never concurrently from two threads.
2. **Saved phrase/sentence terms never highlighted and couldn't be "recovered"**
   (reselecting showed an empty popover, then Save 409'd because the term already
   existed). Root cause: `GET /api/books/{id}/pages/{n}` only returns terms whose
   lemma matches a *tokenizer-produced* lemma (`server/routes/books.py`), so a
   multi-word phrase's lemma — which never matches any single token — is invisible
   in `page.terms` even though it's in the `terms` table. The no-highlight half is
   correct per SPEC's literal per-token rule (matches the earlier 착용하다 decision
   above) and was left as-is. The no-recovery half was a real gap: `web/app/read/
   page.tsx`'s phrase-selection branch now falls back to `GET /api/terms?q=<text>`
   (added as `api.listTerms` in `lib/api.ts`) and filters for an exact lemma match
   when `page.terms` doesn't have the selection, so a saved phrase term now reopens
   pre-filled.
3. **Removed the "Translate sentence" button.** It worked (network tab confirmed a
   response), but wrote to a separate `sentenceTranslation` paragraph above the
   textarea instead of into the editable translation field, which read as broken
   and was redundant with "Translate" per the user's own call. Deleted the button,
   handler, and state from `TokenPopover.tsx`; the italic sentence-context line
   (used for the saved `sentence` field) stays.

## 2026-07-21 — Epic 6: bare-bones `/terms` stub instead of building Epic 7 early
SPEC §7's "Sync to Anki" button lives on the `/terms` page, but that page (filter
table, inline edit, delete) is explicit Epic 7 scope — building it now would blur
epic boundaries and duplicate work. `web/app/terms/page.tsx` is a minimal stub: a
heading, the Sync button, and the `{added, updated, failed}` result — nothing else.
Linked from the home page header. Epic 7 replaces this file's contents with the
real table; the Sync button/logic moves in as-is.

## 2026-07-21 — Anki sync: empty `deck` column falls back to Anki's "Default" deck
`terms.deck` defaults to `''` in the schema (SPEC §4), but AnkiConnect's `createDeck`/
`addNote` need an actual deck name. The current UI's deck `<select>` always has a
value (`TokenPopover.tsx`'s hardcoded `["Korean"]`), so `''` is only reachable for
hand-seeded/legacy terms. `routes/anki_sync.py` treats an empty deck as the literal
string `"Default"` (Anki's own built-in default deck) rather than erroring or
skipping the term.

## 2026-07-21 — Server port changed 8000 → 8002
Discovered while manually testing Epic 2/3: the user's Android app syncs content via
a Docker-based service already listening on `localhost:8000` on this machine (it was
polling `/sync/pull` in the background and its 404s showed up in our server's log
once our test uvicorn instance briefly occupied the port). korean-reader now uses
**8002** instead throughout the docs (SPEC.md, ARCHITECTURE.md, CLAUDE.md) — no app
code needed to change since the port was never hardcoded anywhere (only passed via
`uvicorn --port` on the command line, and will be passed to `web/next.config`'s dev
rewrite target once that's written in Epic 4).

## 2026-07-21 — Epic 8: Lute retired, on the user's explicit confirmation
The user confirmed they've fully switched to korean-reader and no longer use Lute
day-to-day, and explicitly chose to fully replace `start.ps1` (rather than keep a
separate `start-lute.ps1` fallback). Per SPEC §10 Epic 8's gating condition ("delete
`translate_svc/main.py`'s Lute-HTML role only after confirming the user has stopped
using Lute"), `translate_svc/main.py` is deleted. `%LOCALAPPDATA%\Lute3` (Lute's own
data) is explicitly out of scope — not touched, not this repo's to manage.

## 2026-07-21 — Epic 8: docs/launcher done, live cold-start verification deferred
The user asked to prepare for deployment (retire Lute, rewrite `start.ps1`/`README.md`,
add Tailscale docs) but explicitly not to "go live yet," and said they want to keep
developing afterward — so this isn't treated as the project's final epic in spirit,
just the ops chapter. SPEC §10's Epic 8 accept criterion ("fresh `start.ps1` run serves
the full app on :8002 from a cold start") was not executed in this session on that
basis — `start.ps1`'s build-staleness check and the `--host 0.0.0.0` uvicorn launch
were reasoned through and match the already-verified individual pieces (`npm run
build`, `uvicorn server.main:app --port 8002`) from prior epics' manual checks, but the
actual double-click-to-browser flow, the Windows Firewall prompt, and the Tailscale
phone connection are all still the user's to run when they're ready. See
`docs/STATUS.md`.

## 2026-07-21 — Warm "paper" palette via Tailwind v4 @theme + dark-mode variable override
Ad-hoc visual redesign (not tied to a SPEC epic — the user asked directly, after
trying Claude Design and deciding it wasn't the right tool for polishing an
already-working app; see the "not going live yet" Epic 8 entry above for the
session's broader arc). `web/app/globals.css` defines semantic color tokens
(`--color-paper`, `-surface`, `-ink`, `-muted`, `-border`, `-accent`, `-accent-ink`,
`-highlight`, `-danger`, `-danger-soft`) inside Tailwind v4's `@theme` block, which
auto-generates `bg-*`/`text-*`/`border-*` utilities from them. A single
`@media (prefers-color-scheme: dark)` block re-declares the same custom-property
names on `:root` with dark values. Because that block sits outside any `@layer`
(unlike Tailwind's own generated rules, which are layered), it wins the cascade
whenever the media query matches, regardless of source order — so every consumer
utility (`bg-paper`, `text-muted`, etc.) tracks the swap automatically. This let
almost every page in `web/app/` drop its old paired `dark:bg-zinc-950
dark:text-zinc-50`-style classes down to a single semantic class. Headings use
Tailwind's built-in `font-serif` utility (zero new fonts, no network dependency)
for a little "reading app" character; body/UI text stays on the default sans stack.
**User has confirmed the palette but still wants a fuller per-page UI makeover
later** — this redesign is a baseline, not a final pass.

## 2026-07-21 — Epic 9: difficulty counts every saved term as "known", all statuses
`difficulty.known_lemmas()` is `SELECT lemma FROM terms` with no status filter — a
`learning`, `known`, or `ignored` term all count toward coverage. Rationale: difficulty
is "how much of this text is *not new to me*." `learning`/`known` are words the user has
already met (whether or not mastered), and `ignored` words won't be studied, so counting
any of them as new would overstate difficulty. The alternative (only `known` counts)
would make coverage track *mastery* rather than *familiarity*, which is the wrong signal
for "should I pick up this text" — a text of words you're mid-learning isn't as hard as
one of words you've never seen. `new_per_page` (unknown-unique / reader-page-count) is
the headline cold-start metric since it's meaningful even from an empty known-set;
`coverage` is `None` (not 0) when a text has no resolvable lemmas, to keep "undefined"
distinct from "0% known".

## 2026-07-21 — Epic 9: additive schema changes via idempotent ALTER, not a rewrite
The three new `books` columns (`coverage`, `new_per_page`, `scored_at`) are applied by
`db._apply_migrations()`, called from `init_db` right after `executescript(SCHEMA)`.
SQLite has no `ADD COLUMN IF NOT EXISTS`, so it guards each `ALTER TABLE ... ADD COLUMN`
on a `PRAGMA table_info()` check. This upgrades an existing `reader.db` in place (the
user has real data) without a destructive recreate and without a migration framework
(overkill for a single-user app). `_ADDED_COLUMNS` is a plain `{table: {col: decl}}` map
so future additive columns (Epic 11's `topic`/`source_ref`/etc.) extend the same path.
Idempotent by construction — re-running `init_db` never double-adds (covered by
`test_migration_is_idempotent`).

## 2026-07-22 — Epic 11: `tags` as a JSON-encoded TEXT column, `topic` as plain TEXT
Single-user app, so a `book_tags` join table is overkill — same reasoning already
applied to `settings.decks`. `topic` stays a single plain string (one primary category:
gaming/fitness/news/literature/other, matching `docs/CONTENT_CATALOG.md` and the future
`feeds.topic` column) rather than JSON, since a book has one home shelf but can carry
several free-form tags. `tags` round-trips through `json.dumps`/`json.loads` in
`routes/books.py`, same pattern as `routes/settings.py`.

## 2026-07-22 — Epic 11: `source_ref` dedup via a partial UNIQUE index, not a `NOT NULL` column
`source_ref` (video id / feed guid) is `NULL` for every paste/txt book and only ever
set by Epic 12's importers / Epic 14's daily job. A plain `UNIQUE` column would still
work in SQLite (multiple `NULL`s never collide under `UNIQUE` there), but a partial
index (`CREATE UNIQUE INDEX ... WHERE source_ref IS NOT NULL`) makes that guarantee
explicit rather than relying on an easy-to-forget SQLite-specific `NULL` behavior, and
keeps the dedup rule visible next to `_apply_migrations` rather than buried in a column
declaration. `POST /api/books` catches the resulting `sqlite3.IntegrityError` and
returns 409, same shape as `terms.py`'s duplicate-lemma 409.

## 2026-07-22 — Epic 11: `feeds` table lands with no CRUD routes yet
Per the Cycle 2 plan, Epic 11 only needs the schema to exist so Epic 14's daily job and
a future settings page have somewhere to read/write; nothing in this epic populates or
edits it, so no `routes/feeds.py` was written — would be an unused, untestable
abstraction before Epic 14 exists. It's a brand-new table (`CREATE TABLE IF NOT EXISTS`
in `SCHEMA` directly), not an additive column, so it needed no `_apply_migrations` entry.

## 2026-07-22 — Epic 11: `PATCH /api/books/{id}` now returns the full book row
Previously reused `get_book()`'s reduced `{id,title,current_page,page_count}` shape
(matching what the reader page's pagination patch needed). Now that `PATCH` can change
`topic`/`tags`/`archived`/`read`, callers (the home page's Archive/Mark-read buttons)
need those fields back to update state without a second round trip, so `patch_book`
returns `_book_dict()` directly — the same full shape `POST`/`score` already return.
`GET /api/books/{id}` (used by the reader page, which only ever wants the reduced
shape) is unchanged. Checked the one other `patchBook` caller (`read/page.tsx`'s
current-page persistence) discards the response already, so this is a safe widening.

## 2026-07-22 — Epic 12: `trafilatura` for article extraction, not a hand-rolled BeautifulSoup heuristic
No existing code did HTML→article-text extraction (`import_tools` only covers
YouTube/PDF). Considered a lightweight BeautifulSoup heuristic (grab `<article>`/`<p>`
tags) vs. a dedicated extraction library. Chose `trafilatura`: it's specifically built
for exactly this (boilerplate/nav/ad stripping, main-content detection across
arbitrary site templates) and ships its own metadata extraction for a title, which a
hand-rolled heuristic would have to redo badly. Accepted the larger transitive
dependency tree (lxml, courlan, htmldate, justext, dateparser, babel, …) as the
tradeoff for not maintaining bespoke extraction logic across however many different
Korean news/blog templates the user ends up feeding it. Verified live against a real
URL (`https://www.yna.co.kr/`) — title + clean body text extracted correctly.

## 2026-07-22 — Epic 12: three different dedup-key shapes for one `source_ref` column
`source_ref` is a single nullable TEXT column (Epic 11), but the three importers have
no shared natural id, so each prefixes its own namespace into the same column rather
than adding per-source columns: `yt:<video_id>` (yt-dlp's own stable id, immune to URL
query-string variants), `article:<url>` (exact string match — accepted as a known gap;
a re-formatted URL to the same article won't dedupe, judged not worth a canonicalizer
for a personal app), `pdf:<sha256 of the uploaded bytes>` (PDFs have no natural id at
all; hashing the raw bytes means an identical re-upload always dedupes regardless of
filename/title typed at upload time). The `yt:`/`article:`/`pdf:` prefixes also mean
the three namespaces can never collide with each other under the one partial unique
index from Epic 11.

## 2026-07-22 — Epic 12: `yt_subs.fetch_subs` raises instead of `SystemExit`, gains a `video_id` return
The pre-existing CLI script used `raise SystemExit(...)` for the no-subtitles case,
which is fine for a script exiting the process but would crash the FastAPI worker if
called as a library. Changed to a proper `NoSubtitlesError(Exception)`; the CLI
`__main__` block now catches it and converts back to `SystemExit` itself, so
`python import_tools/yt_subs.py <url>` behaves identically from the command line.
`fetch_subs` also now returns the video id (`info["id"]`, already available from the
same `yt_dlp` call) as a third tuple element — needed for the `yt:<video_id>`
dedup key — so its return shape changed from `(title, text)` to
`(title, text, video_id)`; the CLI's unpacking was updated to match.

## 2026-07-22 — Epic 12: `pdf_text.extract()` accepts bytes directly, no temp file
The upload route receives the PDF as in-memory bytes from `UploadFile.read()`.
Rather than writing them to a temp file just so `extract()` could keep taking a
`Path` (extra disk I/O, Windows temp-file cleanup edge cases), `fitz.open()` already
supports `stream=<bytes>, filetype="pdf"` directly — so `extract()` now branches on
`isinstance(pdf_source, bytes)` and the CLI's `Path` usage is unchanged.

## 2026-07-22 — Epic 13: NIKL's graded word list, not the actual TOPIK exam vocab
`docs/CONTENT_CATALOG.md` named two candidates: the official NIIED TOPIK vocab lists
(graded 1–6) or 국립국어원(NIKL)'s "한국어 학습용 어휘 목록" (graded A/beginner,
B/intermediate, C/advanced). Went with NIKL's: it's hosted directly on korean.go.kr
with an explicit public-use statement ("이용자의 편의를 위해... 목록을 원하는 사람은
누구나 이용할 수 있도록... 공개"), whereas the actual TOPIK vocab list's licensing/
distribution terms weren't as cleanly verifiable in this pass. A pre-existing
third-party GitHub repo (`julienshim/combined_korean_vocabulary_list`) had already
combined both sources into a TSV, but its GitHub API metadata shows `license: null`
— no stated license on that specific compiled derivative — so it was used only to
confirm the two source lists existed and roughly what a combined schema could look
like, not as the actual data source; the real import goes straight to NIKL's own
download, not through that repo. 3 grades (not TOPIK's 6 levels) is coarser but
sufficient for score_text's binary "assume familiar" cold-start signal.

## 2026-07-22 — Epic 13: NIKL vocab list downloaded via a session-cookie'd request, not a plain URL
`https://www.korean.go.kr/front_eng/down/down_02V.do?etc_seq=70` (the page's own
"text file" download link) 403s directly — the site requires a session cookie
established by first loading the etcData detail page
(`front/etcData/etcDataView.do?mn_id=46&etc_seq=71`), whose HTML embeds the real,
one-time download URL under a *different* path prefix (`/common/download.do?
file_path=etcData&c_file_name=<uuid>_0.xls&o_file_name=...`). Fetched with `curl -c/-b`
carrying that cookie plus a browser `User-Agent` and the detail page as `Referer`;
without cookie+referer it 404s. Downloaded the `.xls` (Excel 97-2003 binary,
cp949-codepage internally — `xlrd` decodes it correctly despite how it displays in a
non-UTF-8 terminal) rather than the "text file" variant since the text download link
was the one that 403'd. This only matters if the list ever needs re-downloading; the
committed `server/data/vocab_levels.tsv` is what the app actually reads at runtime.

## 2026-07-22 — Epic 13: convert to a committed TSV at build time, not xlrd-at-runtime
Considered shipping the raw `.xls` and parsing it with `xlrd` on every `init_db` call.
Rejected: `xlrd` would become a permanent runtime dependency for a file that only
needs parsing once, the binary `.xls` doesn't diff cleanly in git, and homograph
dedup (가다01/가다02 -> 가다, keeping the easiest grade) has to happen somewhere
regardless. Instead ran the xlrd conversion once (locally, `xlrd` installed
transiently and then uninstalled — never added to `requirements.txt`), and committed
the clean output as `server/data/vocab_levels.tsv` (lemma/grade/rank, UTF-8, sorted by
lemma for readable diffs). `db.py`'s `_seed_vocab_levels()` just does `csv.DictReader`
over this file — stdlib only, no new runtime dependency.

## 2026-07-22 — Epic 13: cold-start fallback is grade-A-only, binary, threshold-gated at 50
Three judgment calls with no spec-mandated number, made together because they compose:
(1) **Grade A only, not a continuous weight across A/B/C** — a text's cold-start
coverage is "how much of this would a beginner already know," and NIKL's grade A is
specifically the beginner tier; partial credit for grade B added complexity (a weight
to justify) without a clear benefit for the coarse "does this text look hard" signal
`new_per_page`/`coverage` exist to give. (2) **Binary membership, not rank-weighted**
— the `rank` column is stored (per Epic 13's "tag lemmas with frequency rank" goal,
for potential future use) but unused by `score_text` itself; grade alone already
satisfies the acceptance criterion (rare text scores harder than common text) without
inventing a rank-to-familiarity curve. (3) **Threshold 50** — arbitrary but
conservative: low enough that a user who's saved a real, personal vocabulary
(anything approaching normal daily use) quickly falls back to pure personal coverage
(the "secondary to personal coverage" requirement from STATUS.md), high enough that a
handful of terms saved while just poking around during onboarding doesn't
prematurely disable the fallback before it's done any good. All three are easy to
revisit if real usage shows the fallback over- or under-shoots.

## 2026-07-23 — Epic 15 named after the already-planned Epic 14/15, not in place of them
The user had already planned Epic 14 (daily fetch job, capstone) and Epic 15 (UI
makeover + go-live) in `docs/STATUS.md`. This session's plan — a curation queue, a
general/public difficulty tag, and a source-type filter — was drafted independently and
initially wasn't sure where it fit; the plan's own footer even said "mark Epic 14 done."
Asked the user directly: this work becomes **Epic 15**, the old Epic 15 (UI makeover)
shifts to **Epic 16**, and the old Epic 14 (daily fetch job) entry stays in place but
gets a short amendment noting its scope is now much smaller (see its STATUS.md entry) —
rather than being silently rewritten, since the user might decide it's not needed at all
once `/queue`'s manual "Fetch new candidates" button exists.

## 2026-07-23 — Epic 15: `status` gets a CHECK constraint, unlike every prior additive column
Epics 9/11/13 all added columns via `_ADDED_COLUMNS`/`_apply_migrations` with no CHECK
(`coverage`, `topic`, `archived`, etc.) — incidental flags/caches where a bad value just
means bad data, not bad behavior. `status` is different: it's a central enum (`'library'|
'candidate'|'discarded'`) that `GET /api/books`'s default filter, the Queue page, and the
promote/discard flow all key off of — a typo'd value would silently break filtering
everywhere at once. Worth the deviation. Still applied through the same idempotent
`ALTER TABLE ... ADD COLUMN` path (the full declaration string, CHECK included, is just a
longer value in the same `{col: decl}` dict) — no new migration mechanism needed.

## 2026-07-23 — Epic 15: candidate lifecycle is a `books.status` value, not a separate table
A feed-fetched candidate needs full page content (to read/score it) and a cached
difficulty score (to judge it) before the user decides — i.e. it's structurally a book
already, not a lighter-weight preview record. Reusing `books` with a `status` column
means "promote" is a single `PATCH .../status=library`, not a copy across tables with a
new id; the reader, scorer, and every existing book route work on a candidate with zero
special-casing. The alternative (a `candidates` table) would have needed its own page-
storage, its own scoring path, and a real INSERT-into-books + DELETE-from-candidates
migration step at promote time for no real benefit at this single-user scale.

## 2026-07-23 — Epic 15: discard is a soft delete (`status='discarded'`), never a real DELETE
Rejected `DELETE /api/books/{id}` for the Queue's Discard button specifically because the
`source_ref` unique index (Epic 11) is what stops the same feed item from being re-fetched
and re-created on every subsequent `POST /api/feeds/fetch` run — a hard delete would free
up that `source_ref` and the exact item the user already said no to would reappear next
fetch. `status='discarded'` keeps the row (and its `source_ref`) around forever, at the
cost of a permanently-growing `books` table — an acceptable tradeoff for a single-user app
where "discarded" items are a small fraction of total volume. `DELETE /api/books/{id}`
still exists for a genuine hard-delete need (e.g. a future "empty discarded" action), just
not wired to Discard.

## 2026-07-23 — Epic 15: general/public difficulty is a separate function, never blended with personal coverage
`score_general_difficulty(text, frequency)` takes no `known` set at all — it answers "how
hard is this for a typical learner" using only the `vocab_levels` grade distribution,
while `score_text`'s `coverage` answers "how hard is this for *me*". Epic 13's cold-start
fallback already blends frequency-grade data into personal coverage when the user's own
vocabulary is thin, which could look similar at a glance — but that blend is a *temporary,
threshold-gated stand-in* for personal coverage during onboarding, whereas this is a
*permanent, independent* second number shown side by side, useful even after the user has
thousands of saved terms (a text can be "80% covered by what I personally know" and still
be "hard for a typical learner" if it's full of book-specific proper nouns, or vice versa).
Keeping them as two separate functions/fields (`coverage` vs `general_coverage`) rather
than one blended score means the two numbers can never silently contaminate each other's
meaning as usage evolves — verified directly:
`test_general_difficulty_is_independent_of_personal_known_set` saves a personal term and
confirms `general_coverage`/`general_level` don't move while `coverage` does.

## 2026-07-23 — Epic 15: general-difficulty weights (A=1.0/B=0.5/C=0.15/unlisted=0) and 0.75/0.45 bands
Judgment calls, flagged here as tunable (same spirit as Epic 13's threshold-50 note):
**grade C gets a small nonzero floor (0.15), not 0** — a text tagged "advanced" in NIKL's
scheme is often still partly loanwords/technical terms a learner half-recognizes, so
treating it identically to a totally unlisted lemma felt too harsh. **Unlisted lemmas get
0**, the most conservative choice, since an unrecognized word (proper noun, slang, typo,
a word simply missing from a 5.5k-entry list) is *more* likely to trip up a learner than
a word NIKL bothered to grade at all, not less. **Bands recalibrated to 0.75/0.45**
(lower than `score_text`'s 0.95/0.85): a weighted average across every unique lemma in a
real text — including its inevitable minority of unlisted/rare words — rarely climbs into
the high-90s even for genuinely easy text, so reusing the personal-coverage bands verbatim
would have mislabeled almost everything "hard". Verified this matches intuition on the two
real reference sentences from Epic 13: the all-common STORY scored 1.0/"easy", the mixed/
mostly-unlisted RARE_STORY scored 0.358/"hard" (see STATUS.md's Epic 15 entry for the live
`vocab_levels`-backed numbers, not hand-built test dicts). All four numbers are easy to
retune once real candidate text (from the actual feeds) has been scored and eyeballed.

## 2026-07-23 — Epic 15: `GET /api/books` defaults `?status=` to `"library"`, judged a safe widening
Before this epic, `list_books` had no concept of `status` and returned every row. Now that
candidates/discarded rows exist, returning everything by default would mean a fresh
`POST /api/feeds/fetch` run immediately clutters the home page with un-vetted candidates —
exactly what Epic 15 exists to prevent. Defaulting the filter to `'library'` when the
query param is omitted keeps the home page's existing behavior *for every book that
existed before this epic* (all default to `status='library'` per the column's own
`DEFAULT`), while giving `/queue` an explicit `?status=candidate` to see the rest. Checked
every existing `test_books.py`/`test_difficulty.py`/`test_imports.py` book-creation call
site: all go through `insert_book`/`BookCreate`, both of which default `status="library"`,
so nothing currently visible becomes hidden — confirmed by reading all three files, not
just reasoning about it.
