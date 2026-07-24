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

## 2026-07-23 — Epic 16: stats/reading-time tracking deliberately un-backlogged
SPEC §227's backlog explicitly listed "stats/reading-time tracking" as out-of-scope, do
not build. Epic 16 reverses that at the user's direct request: they want a stats screen for
accountability (stay honest about reading) and to show off progress ("instagrammable"),
plus two specific asks — new words per book (watch the curve flatten) and new words per
page. The §227 line is amended to point here. The original exclusion was about not gold-
plating the core reading tool; now that the tool is complete, a stats layer is a
deliberate, wanted addition, not scope creep.

## 2026-07-23 — Epic 16: term provenance is two nullable columns, forward-only
`terms.source_book_id`/`source_page` (added via the same `_ADDED_COLUMNS` path as Epics
9/11/15) record where a word was *first* saved — a term is one global row per lemma, so
the origin is unambiguous (you saved it once). Nullable and no FK: terms saved outside the
reader (e.g. `/terms`) have no origin, and a later book delete just leaves a harmless
dangling id (the stats join is an inner join, so orphaned ids simply drop out). Forward-
only — the handful of pre-Epic-16 test terms stay NULL, which is fine since real reading
starts at go-live. This is what makes "new words per book" a count of terms actually
learned *from* that book, not a re-derivation from the difficulty scorer's coverage.

## 2026-07-23 — Epic 16: reading-log dedup via PRIMARY KEY + 5s dwell gate
Two safeguards the user asked for. **No double-count:** `page_reads` is keyed
`PRIMARY KEY(book_id, page_no)` and writes with `INSERT OR IGNORE`, so the first genuine
read of a page inserts a row (stamped `read_at`) and every later revisit — e.g. re-checking
a word on a page read yesterday — is a silent no-op. "Pages read" is therefore *distinct
pages ever read*, each counting once on the day it was first read. **Dwell gate:** the
reader client only pings `POST /api/reads` after the page has been visible for
`READ_DWELL_MS = 5000`, cancelled if the tab is hidden — so flicking past a page in under
5s never counts. Streak = the union of days a word was saved OR a page was first read; pure
re-reading (no new page, no new word) does not extend the streak, matching the user's
"shouldn't count" intent. Both the 5s window and the union rule are tunable.

## 2026-07-23 — Epic 16: page size is a setting; difficulty stays pinned to the paging default
`settings.page_size` (default 650 chars, ~one phone screen at the reader's
text-lg/leading-loose) is passed to `split_pages` at import time and on a library-wide
re-pagination when the setting changes. **Difficulty scoring is deliberately NOT coupled to
it:** `difficulty.score_text` keeps calling `split_pages(text)` with its own 1500-char
default as a fixed reference, so a book's `new_per_page` means the same thing regardless of
how the user has set their reading page size — otherwise every score would silently shift
when the setting changed. Re-pagination reconstructs each book's original text by joining
its stored page slices (lossless — `split_pages` slices are contiguous), re-splits,
preserves reading position by character offset, and **clears that book's `page_reads`
rows** (page_no boundaries moved, so old read marks no longer map — accepted, since re-
pagination is deliberate and rare, and there's near-zero read history pre-go-live).

## 2026-07-23 — Epic 14: the curated feed roster (content selection over automation)
The "curated list of content" the user dreaded. Sources were **selected by the assistant
to the user's stated tastes** (they don't consume this content themselves, so "go with the
popular ones that fit"): male-presenter, idea-exposition/science-focused essayists over
variety/lifestyle/interview content. Final roster (15 feeds, see docs/CONTENT_CATALOG.md
for names + channel IDs): gaming (Inven, Ruliweb RSS + G식백과, 김실장 YouTube), ideas
(슈카월드, 충코의 철학, 셜록현준, 최준영 지구본연구소), science (리뷰엉이), fitness
(김명섭의 헬스교실), tech (조코딩 YouTube + 요즘IT RSS), news/long-form (ㅍㅍㅅㅅ,
슬로우뉴스, 뉴스페퍼민트 RSS). **Every feed was verified live this session** — RSS via the
app's own no-UA `fetch_feed_xml` (slownews 403s *with* a browser UA but works without one,
which is exactly how the app fetches; ppss lives at the CMS `/rss/allArticle.xml` path),
YouTube channel IDs resolved via yt-dlp and confirmed against each channel's Atom feed.
Dropped in review: 김지윤 지식Play (user cut), 1분과학 (dead ~1yr), 과학드림 (biology/low
cadence), 피지컬갤러리·핏블리 (variety/mixed-gender), 씨리얼 (documentary, no host),
운동하는 물리치료사 자반 (too clinical), 얄팍한 코딩사전 (user cut), 디스이즈게임 (RSS
hard-403s every path — Inven/Ruliweb already cover gaming). Shipped as seeds (db._SEED_FEEDS,
guarded per-URL by _seed_feeds), not a migration — a growing hand-editable roster.

## 2026-07-23 — Epic 14: YouTube-channel fetch support (channel feed → transcript)
Epic 15's fetcher only handled `rss` (article feeds) and skipped `youtube`. Since the
curated roster is mostly YouTube essayists, the fetch job would have been inert without
this. `server.feeds.parse_youtube_feed` parses a channel's Atom feed
(youtube.com/feeds/videos.xml?channel_id=UC…, ~15 latest, `<yt:videoId>` per entry);
`routes/feeds._process_youtube` dedupes each video on `source_ref="yt:<video_id>"` **before**
fetching, then pulls the Korean transcript via the existing `import_tools.yt_subs.fetch_subs`
(yt-dlp) and inserts a `status='candidate'` book scored like any other. Decisions:
(1) reuses the **same `yt:<video_id>` source_ref shape as Epic 12's manual YouTube import**,
so a video imported by hand and via feed collapse to one book. (2) A video with **no Korean
subtitles is `skipped_no_subs`, not `failed`** — it's an expected outcome, not an error, and
shouldn't read as a broken feed. (3) `YOUTUBE_MAX_PER_FETCH = 5` caps new videos processed
per channel per run — each transcript is a yt-dlp round-trip, so an uncapped first run over
9 channels could stall the interactive "Fetch new candidates" button for minutes; later runs
pick up the rest. All three are tunable. Verified live (network-only, no DB): 조코딩's feed →
real 37k-char transcript end-to-end.

## 2026-07-23 — Epic 14: feeds CRUD + /feeds page (retouch the roster without code)
The user wanted to "easily retouch the content list to swap something later." Added
GET/POST/PATCH/DELETE `/api/feeds` and a `/feeds` management page (add / inline-edit /
enable-disable toggle / delete), so the roster is user-editable at runtime — swapping a
channel or turning a noisy source off is a few taps, not a re-seed. No UNIQUE constraint on
`url_or_channel_id` (single-user, UI-curated — a duplicate is the user's call to make, and
the fetch job dedupes on `books.source_ref` regardless). The topic vocabulary grew to
gaming/ideas/science/tech/fitness/news/literature/other (shared `web/lib/topics.ts`), used
by the home filter, add-book modal, and feeds editor.

## 2026-07-23 — Epic 14: Queue title-translate button; Task Scheduler timing deferred
Folded in a per-row **"Translate" button on the Queue** (calls `POST /api/translate` on the
candidate's title) so an unfamiliar auto-fetched item can be judged at a glance before
promote/discard — the user flagged that judging content they can't read is otherwise hard.
Candidate **category is already handled**: each fetched item inherits its feed's `topic`
(+ the feed name as a tag), shown on the Queue row. **Deferred to a later Task Scheduler
session** (the user's call): the actual scheduled timer that pings `POST /api/feeds/fetch`,
and the policy for new-content cadence / retention/archival of stale candidates. The manual
"Fetch new candidates" button on /queue covers the workflow until then.

## 2026-07-23 — EPUB import: ebooklib + stdlib HTML-strip, byte-hash dedup
Added a fifth importer (`POST /api/import/epub`, source `epub`) mirroring the PDF path
exactly: multipart upload → in-memory bytes → `import_tools/epub_text.py:extract(bytes)`
→ shared `insert_book` with `source_ref="epub:<sha256 of bytes>"` (same byte-hash
rationale as PDF — EPUBs have no natural id, an identical re-upload always dedupes).
**Library choice:** `ebooklib` (already had `lxml` transitively via trafilatura, so the
only genuinely new package) to walk the OPF spine in reading order, plus a small stdlib
`HTMLParser` subclass to strip each XHTML document to text rather than pulling in
BeautifulSoup — the extraction we need (drop script/style, insert newlines at block
boundaries, collapse whitespace) is small enough to own. **Spine order over
declaration order:** iterate `book.spine` and resolve each idref to its document so
chapters come out in reading order, falling back to `get_items_of_type(ITEM_DOCUMENT)`
only if a book declares no spine. **Empty-text 502:** unlike the PDF route, the EPUB
route explicitly returns `502 {"error": "No extractable text in this EPUB."}` when the
strip yields nothing — a DRM'd or purely image-based EPUB parses without raising but has
nothing to read, and a silently-empty book is worse than a clear error. **Title:** taken
from the typed field or the filename stem (same as PDF), not the EPUB's embedded `DC:title`
metadata — kept the `extract()` boundary returning a plain `str` so the route tests can
mock it exactly like `extract_pdf`; using embedded metadata is an easy future enhancement
if the filename-stem default proves annoying.

## 2026-07-23 — Epic 17: retention reuses status='discarded', no new enum value
The user considered a distinct "expired" status but chose to keep candidate auto-expiry
indistinguishable from a manual discard: both flip `books.status` to `'discarded'`, so the
existing permanent `source_ref` block (never re-fetched) applies identically either way —
no schema/CHECK-constraint change, no new branch in any code that already switches on
`status`. The tradeoff (can't tell "aged out" from "actively rejected" in stats) is
deliberately deferred to Epic 19, which is free to add a `discard_reason` column later
without touching this epic's code again.

## 2026-07-23 — Epic 17: expiry piggybacks on every /api/feeds/fetch call, no separate cron
Considered a second Task Scheduler entry dedicated to expiry so its cadence could be tuned
independently of the fetch interval. Rejected: the expiry check is a single indexed
`UPDATE ... WHERE status='candidate' AND created <= cutoff`, cheap and idempotent, so
running it on every fetch call (scheduled or manual, whole-roster or single-feed retry)
costs nothing extra — and a second scheduled entry is a second thing that can silently fail
with no user-visible symptom, for a feature the first entry already covers for free.

## 2026-07-23 — Epic 17: last_fetch_attempt is a settings row, not a fetch_log table
A single nullable `settings` key (`last_fetch_attempt`, JSON-encoded string like every
other settings value) rather than a new append-only log table — the requirement is "when
did we last try," not a history of every run (scripts/fetch_feeds.log already covers
after-the-fact debugging of individual runs). Deliberately excluded from `SettingsPut` so
a `PUT /api/settings` body can never clobber it — pydantic silently drops unknown fields,
so sending it back is harmless, it just never writes. Stamped via SQLite's own
`CURRENT_TIMESTAMP` (not Python's clock) to match the string format every other
TIMESTAMP-ish column in this app already uses (`books.created`, `feeds.last_fetched`).

## 2026-07-23 — Epic 17: "Library" replaces "book(s)" as the umbrella word, copy-only
The user found "book" overloaded — used for both "your whole reading list" and "an actual
long-form book" (PDF/EPUB import). Resolved as a **UI copy pass only**: nav links, the
add-content modal, and stats headings now say "Library"/"item(s)"; a small "Book" badge
was added next to `pdf`/`epub`-sourced rows on `/` to reserve that specific word. The
`books` table, `source` column values, every API field name, and every TS type/identifier
(`Book`, `book_id`, `NewWordsPerBook`, etc.) are unchanged — renaming those would be a much
bigger, purely-cosmetic migration for zero user-facing benefit beyond what the copy pass
already delivers.

## 2026-07-23 — Epic 18: source-type chips reuse the existing palette, no new hues
Considered per-source arbitrary Tailwind colors (red for YouTube, blue for articles,
etc.), rejected in favor of the existing warm "paper" theme tokens (`accent`/`border`/
`muted`) — the palette was deliberately kept small and cohesive (see the Epic 16-era
DECISIONS entry on the Tailwind redesign), and only two source types reach the Queue
today. `web/lib/chips.tsx` stays a one-file lookup table, easy to extend with a new
hue if a third source type genuinely needs its own color later.

## 2026-07-23 — Epic 18: word_count computed for every source, not just text ones
`insert_book()` derives `word_count` from `text.split()` unconditionally rather than
only for `article`/`pdf`/`epub` — simpler (one code path, no source-type branching)
and harmless for `yt` (a transcript's word count is still a real, useful number,
`formatLength()` just prefers `duration_seconds` when both are present).

## 2026-07-23 — Epic 18: "Shortest first" sort uses a 250-wpm heuristic, never shown
Ranking a short article against a 2-hour video transcript needs one common unit.
`estimatedMinutes()` (`web/lib/length.ts`) converts both to a rough "minutes to
consume" number using a standard reading-speed constant — but only to order the list;
`formatLength()` always displays the *exact* word count or *exact* duration, never the
estimate, so the heuristic's imprecision never reaches the user as a stated fact.

## 2026-07-23 — Epic 19: kept discard_reason as its own column, per the spec's recommendation
SPEC §10 flagged this as a judgment call: lump auto-expiry and manual discard under
plain `status='discarded'`, or add `discard_reason` to tell them apart. Kept the
column — a pile of `expired` candidates in one topic (nobody looked, cadence/volume
problem) reads completely differently from a pile of `user`-discarded ones (looked,
rejected, taste/relevance problem), and that distinction is the entire point of a
"what's NOT being promoted" stats section; collapsing it would make half the feature
unable to answer its own question. Nullable, no `CHECK` (unlike `status`) — it's
informational, not a lifecycle gate, and pre-Epic-19 discards (and the
`test_fetch_feeds_skips_scraper_feed_type`-era rows with no `feed_id` at all) simply
have it NULL. Two write sites only: `routes/books.py`'s manual `PATCH
status='discarded'` sets `'user'`; `routes/feeds.py`'s `_expire_stale_candidates`
(Epic 17's auto-expiry `UPDATE`) sets `'expired'` in the same statement — no third
place ever writes it.

## 2026-07-23 — Epic 19: feed_id is a soft reference, no FK, mirrors terms.source_book_id
`books.feed_id` replaces the old `tags=[feed["name"]]` join-back-to-a-feed convention
(fragile across feed renames — Epic 14/15's `_insert_and_score` used to stash the
feed's *name* as a tag) with a stable id, but deliberately without a foreign key: a
deleted feed (`DELETE /api/feeds/{id}`) must never cascade-delete or orphan-block the
books it produced, since those books' reading/curation history is worth keeping even
after the subscription itself is gone. `GET /api/stats`'s curation breakdown handles a
now-missing feed by `LEFT JOIN`-ing and falling back to `"(deleted feed #<id>)"` rather
than dropping the row. Manual imports (`routes/imports.py`'s four importers) and
paste/txt (`routes/books.py`'s `create_book`) never set it, which is also exactly the
condition the curation query uses to exclude non-automated content
(`WHERE feed_id IS NOT NULL`) — no separate "is this feed-sourced" flag needed.

## 2026-07-23 — Epic 20: term "forms" (aliases) as a normalized table doing double duty
The reported bug: the user hand-edited a term's **lemma** into `승인 / 승인서` to keep the
derived word 승인서 visible on the Anki card, which silently broke highlighting — matching
is exact `token.lemma == terms key` equality and `승인 / 승인서` is no tokenizer lemma. Fix:
a term can carry extra **forms** (aliases). Three choices worth recording:
- **Normalized `term_forms(term_id, form)` table, not a JSON `forms` column on `terms`.**
  Matching in `books.get_page` stays a set-membership `WHERE form IN (page_lemmas)` join
  (the same shape as the existing lemma match), instead of loading every term's JSON to
  test membership in Python. `ON DELETE CASCADE` + the always-on FK pragma means deleting
  a term drops its forms; plain `CREATE TABLE IF NOT EXISTS` in `SCHEMA` (like
  `pages`/`page_reads`), no migration bookkeeping.
- **One `forms` list serves both highlighting and the Anki card** (the user's explicit
  choice over two separate lists). Each form both lights up in the reader *and* renders on
  the card's Korean face (`_render_front` → `lemma / form1 / form2`). `lemma` stays the one
  clean dictionary form so the tokenizer/`known_lemmas` logic is untouched.
- **`get_page` now returns `lemma` + `forms` per matched term, and keys the map by the
  form string too** (direct-lemma match wins on collision). Carrying the parent `lemma`
  lets the reader popover show 승인 when a 승인서 token is tapped; a forms change is a
  dirty trigger so the card front re-syncs. Deferred to Epic 21 (no Claude, per the user):
  interactive dictionary click-to-add, krdict example sentences, and a custom two-way Anki
  note type with examples confined to each card's answer side.

## 2026-07-23 — Epic 21: dictionary click-to-add, krdict examples, custom two-way note type
Phase B of the term-forms plan (`hey-babes-i-need-temporal-beacon`). Hard user
constraint carried through: **no Claude API** anywhere — krdict + DeepL + manual only.
Four choices worth recording:
- **krdict examples come from a second `view` call, not the search response.** The
  `search` API's `<sense>` carries glosses but no example sentences; examples live under
  `word_info/sense_info/example_info/example`, only returned by the `view` API keyed on
  an item's `<target_code>`. So `krdict.lookup()` now does 1 search + up to N `view`
  calls (N = `max_entries`, raised 3→5 so more derived headwords surface for click-to-add),
  each `view` best-effort (returns `[]` on any failure — no key, network, bad XML — so a
  dictionary lookup never breaks over examples). Deduped and capped at 5 per entry.
- **Examples stored as a JSON `examples` column on `terms`, not a normalized table.**
  Unlike `term_forms` (matched against page tokens in `get_page`, so it must be a
  set-membership join), examples are **display-only** — they only ever render on the Anki
  card back. A JSON list column is simpler; `routes/terms.py` folds it into the same
  generic UPDATE + `_DIRTY_TRIGGER_FIELDS` dirty check as the plain text columns (the
  value is compared as its stored JSON string).
- **Custom two-way note type, existing `Basic` notes preserved not migrated.** New terms
  sync onto `"Korean Reader 2-way"` (fields Korean/English/Examples; two templates, both
  keeping `Examples` on the back only — the anti-spoiler guarantee, asserted in tests).
  A new `anki_model` column records which model a synced term lives in: notes synced
  before Epic 21 have it NULL and keep the stock Front/Back update path, so their SRS
  scheduling history is never disturbed — the sync loop branches on `anki_model`, no
  re-creation, no `notesInfo` round-trip needed. `ensure_model()` is create-once
  (guarded on `modelNames`), called best-effort each sync like `createDeck`.
- **Phrase selections get a translate-only popover.** A multi-word span has no single
  dictionary lemma or card-worthy forms, so `read/page.tsx` flags `isPhrase` (selection
  contains whitespace) and `TokenPopover` hides the dictionary / forms / examples UI for
  it — matching the user's words-vs-phrases distinction. Clicking a dict headword adds it
  to `forms`; clicking a sense appends its English gloss to the translation; clicking an
  example chip attaches it to the card's examples.

## 2026-07-24 — Reader pagination switched from char count to estimated row count
Ad hoc user request (not a numbered epic), three small asks in one session; this is the
substantial one. The complaint: `settings.page_size` (Epic 16, char-budget) made pages look
wildly inconsistent depending on how newline-dense the text was — a page of subtitle-style
short lines or dialogue racked up far more on-screen rows than a page of one dense paragraph
at the same char count, since char count says nothing about line-wrap behavior.
- **New `paging.split_pages_by_rows(text, max_rows, chars_per_row)`, `split_pages` (char-based)
  left untouched.** `difficulty.score_text`/`score_general_difficulty` still call `split_pages(text)`
  with its own fixed 1500-char default as a page-size-independent scoring reference (the Epic 16
  rule) — that reference must not drift just because the reader's own pagination changed, so it
  was left as a separate function entirely rather than folding rows into `split_pages` itself.
- **`estimate_rows(s, chars_per_row)` is a pure heuristic, not a DOM measurement:** every `\n`
  forces a row, and each line between newlines wraps every `chars_per_row` characters (ceil
  division, blank line = 1 row). No client-side measurement needed — pagination stays fully
  precomputed server-side (at import and on a settings change), so per-page reading load stays
  exactly as cheap as before (one page's content + tokenize, independent of book length).
  `chars_per_row` is deliberately a user-editable setting (not hardcoded) since real wrap width
  depends on the device/font — the user tunes it once they're actually looking at their phone.
- **`settings.page_size` replaced outright by `page_rows` (default 22) + `chars_per_row`
  (default 32)**, not kept alongside it — there's no use for a char-budget reader setting once
  rows exist, and keeping both would mean two independent "page size" concepts to reconcile.
  Old `page_size` rows left in an existing `settings` table are simply inert extra keys (the
  settings table is a merge-over-defaults k/v store, not a migrated column), harmless.
- **Performance: `split_pages_by_rows` walks the sorted breakpoint list with a single forward
  cursor across the whole call**, instead of `split_pages`'s original pattern of rescanning the
  full breakpoint list from the start on every page. This was specifically to address the user's
  stated worry about lag/jitter repaginating a very long (1000+ page) book on a settings change —
  total breakpoint-list work is now linear in text length rather than closer to quadratic.
- Same session, two smaller UI asks: a source link (`↗`) on Library rows (Queue already had
  one) — placed in the row's action-button strip, not inside the row's own `<Link>` wrapper,
  since nesting an `<a>` inside a Next `Link`'s anchor is invalid HTML; and topic/source filter
  `<select>`s on `/queue` matching `/`'s existing ones (the API already accepted `?topic=`/
  `?source=` on `GET /api/books`, just wasn't wired into the Queue page's UI).

## 2026-07-24 — Epic 22: `term_back_items.group_key` is a stable id, not a live lemma join
The popover's Front/Back card builder needs to know which "group" (the lemma, or a specific
extra form) each Back chip belongs to. The tempting shortcut — join on the term's current
`lemma` text — breaks the moment the lemma is hand-corrected (a routine action: SPEC's whole
premise is that the tokenizer's lemma guess is sometimes wrong and the user has final say). If
the lemma's own back items were keyed by its literal text, editing the lemma would silently
orphan them. Instead `group_key` is `''` for the lemma's own group, a fixed sentinel
independent of whatever the lemma field currently says, and a `term_forms.form` string for
every other group (forms themselves are add/delete-only, never renamed in place, so keying by
their text is safe). This mirrors the same reasoning Epic 20 already applied to `term_forms`
matching by string rather than by a live foreign key into a mutable field.

## 2026-07-24 — Epic 22: the old `examples` column is superseded, not dropped
The structured card builder's `term_back_items.korean_def` (plus the reading `sentence` and
free-typed `notes`) now supplies everything that goes into the Anki `Examples` field for any
term that uses it — the old flat `examples` JSON column (Epic 21's krdict-collocation list) has
no role in that path. It's left in the schema untouched rather than dropped, per the project's
additive-only migration convention (`_ADDED_COLUMNS`, no destructive `ALTER TABLE`), and it
still matters for genuinely legacy terms: `routes/anki_sync.py` renders from it whenever a term
has zero `term_back_items` rows, so a term nobody has opened in the new popover keeps syncing
exactly as it did before this epic. Also folded into this epic: the user's assumption that the
Anki field itself needed renaming from "Examples" to "Notes" turned out to be a false alarm
(checked against a live Anki install) — the field really is called "Examples," so `server/
anki.py`/`ensure_model()` needed no changes at all, only what gets rendered into it.
