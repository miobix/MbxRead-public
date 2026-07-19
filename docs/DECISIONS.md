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
