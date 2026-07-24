# Learned lessons — documentation & dev-cycle practices

*Reference doc (meta). Captured at project closure, 2026-07-24, from building MbxAndria with
Claude Code. This is the transferable process knowledge — carry it to the next project.*

---

## 1. Docs are not one thing. Sort them by read-pattern.

The core mistake that made this repo's docs rot: treating every `.md` as one append-only
pile. They're actually four kinds, and the maintenance rule follows from **how often the file
is read and whether it's read in full** (full taxonomy in `docs/README.md`):

- **Living state** (`STATUS.md`) — read first, every session. Cost = length × every session.
  **Rewrite in place; prune ruthlessly.**
- **Contract** (`SPEC.md`, `ARCHITECTURE.md`) — read when building the thing. Keep accurate.
- **Append-only log** (`DECISIONS.md`) — looked up, never read in full. **Never compress.**
  Length is nearly free and the growth is the point.
- **Reference / ephemeral** (catalogs, this file, `archive/`) — on demand; ephemeral ones
  get archived once spent.

The anxiety about "files getting too long" is **only** justified for *living state*. A
946-line `STATUS.md` titled "read this first" was the bug. An 828-line append-only
`DECISIONS.md` was working exactly as designed.

## 2. Git + the decision log ARE your history — so prune the living docs fearlessly.

Because every epic was one commit (`Epic N: …`) that included the docs, the full narrative of
everything already lives in `git log` and `DECISIONS.md`. That's what *earns* the right to
delete finished-work detail from `STATUS.md`: you are removing a **duplicate** of history from
the hot path, not losing anything. `git log`, `git show <commit>`, and dated DECISIONS entries
recover any detail on demand.

## 3. When to compress — prune-in-place continuously, roll up at checkpoints.

Two motions, two rhythms. Don't confuse them:

- **Prune-in-place, every epic.** When an epic ships, delete its "in progress / next steps /
  verification owed" scaffolding from `STATUS.md`. Cheap; just part of "update docs."
- **Big roll-up, at cycle boundaries** (cycle end, go-live, major refactor). Collapse the
  whole run of completed epics into one line each; archive spent planning docs. Heavier — do
  it at the natural checkpoint, **not** every couple of epics (too disruptive, and you lose
  the checkpoint as a signal).

Trigger signals that a *living-state* file needs compressing: it passes ~200–300 lines; you
catch yourself scrolling past sections about finished work; a section describes a state that's
no longer true.

## 4. Ephemeral planning docs have a lifecycle that ENDS.

`NEXT_STAGE_OPTIONS.md` and `HANJA_STUDY_OPTIONS.md` were thinking docs. The moment their
decision was made, they became dead weight in `docs/`. The decision itself belongs in
`DECISIONS.md`; the options doc gets **moved to `archive/` (or deleted — git remembers)**.
Name a doc's *kind* in its opening line so "this one is ephemeral" is explicit from day one.

## 5. The dev cycle that worked: spec-driven, model-tiered.

*discuss features → plan with a strong model → write plan/epic files → execute with a cheaper
model → add tests → lock the tests → update docs → one commit per epic.*

Why it worked: **the docs were the executor's memory.** A well-scoped `SPEC.md` + a `STATUS.md`
pointing at the next epic is what let a cheaper model execute reliably without re-deriving
context each session. Commit-per-epic-with-docs was the quiet hero — it made git a queryable
history, which in turn licensed aggressive pruning of the living docs (lesson 2).

**Three refinements for next time:**

1. **Doc hygiene is engineering, not paperwork.** The one thing that decayed was the one
   thing with no maintenance step: living state. Add an explicit **cycle-level** hygiene pass
   ("at go-live / cycle end, roll up STATUS and archive spent docs") — not epic-level (too
   frequent), not never (what happened here).
2. **Name the doc taxonomy up front**, in the project's `CLAUDE.md` and a `docs/README.md`.
   One line per doc kind. That single paragraph would have prevented the pile-up, because
   every session would know `STATUS.md` is prune-in-place, not append.
3. **Keep the SPEC / STATUS / DECISIONS split and name it.** Contract (stable) vs. state
   (volatile) vs. log (append-only) is a strong, reusable pattern. Starting a new project
   with those three files and the four-kind taxonomy is the whole lesson, pre-loaded.

## 6. Where Anthropic documents this

- **"Claude Code best practices"** (Anthropic engineering blog) — `CLAUDE.md` philosophy:
  keep it concise, human-readable, refine over time, don't let it bloat.
- **"Effective context engineering for agents"** (Anthropic engineering) — the principle that
  every token in always-loaded context has a *recurring* cost, which is exactly why
  living-state bloat matters and append-only logs (read on demand) don't.
- In-product docs on **`CLAUDE.md` and the memory tool.**

The four-kind taxonomy and the STATUS/SPEC/DECISIONS split above aren't Anthropic-official —
they're this project's synthesis, and they're the reusable part.
