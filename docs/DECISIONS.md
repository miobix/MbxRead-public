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
