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
