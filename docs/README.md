# docs/ — what each file is, and how to maintain it

Not every doc is the same *kind* of thing. Each has a different read-pattern and therefore a
different maintenance rule. Treating them all as one append-only pile is what makes docs rot.
The four kinds:

| Kind | Read pattern | Rule | Files here |
|---|---|---|---|
| **Living state** | Read first, every session, top-to-bottom | **Rewrite in place.** Prune finished work; keep it short. | `STATUS.md` |
| **Contract** | Read when building the thing it specifies | Update to match reality; log deviations in the log. | `SPEC.md`, `ARCHITECTURE.md` |
| **Append-only log** | Looked up on demand ("why did we…?"), never read in full | **Never rewrite, never compress.** Growth is correct. | `DECISIONS.md` |
| **Reference / ephemeral** | On demand; ephemeral ones die once decided | Reference: keep accurate. Ephemeral: **archive when spent.** | `CONTENT_CATALOG.md`, `LEARNED_LESSONS.md`, `archive/` |

**Naming:** epics 0–32 come from solo development, where an *epic* meant one scoped change
(one session, one commit, one `DECISIONS.md` entry), not the Scrum sense. From the public
repo on, the same thing is a *unit*: one roadmap item, one PR, numbered as in `STATUS.md`
("Next: grow the app"). Epic 32 is unit 0.

## The files

- **`STATUS.md`** — *Living state.* The current picture of the app + the epic checklist +
  live operational facts + open follow-ups. Read it first. **Prune it as you go:** when an
  epic finishes, its blow-by-blow detail is deleted from here (it's in `git log` +
  `DECISIONS.md`), leaving a one-line checklist entry. Do a full roll-up at cycle
  boundaries, not mid-cycle.
- **`SPEC.md`** — *Contract.* Architecture, schema, API shapes, tokenizer heuristic, UX
  spec, per-epic scope/tests/acceptance, executor conventions. The stable source of truth.
- **`ARCHITECTURE.md`** — *Contract.* The as-built schema + API surface. Kept in sync with
  the code; the "what is wired up" reference.
- **`DECISIONS.md`** — *Append-only log.* One dated entry per non-obvious decision, with the
  why. **Never edit past entries.** This is the project's memory; it's *supposed* to be long.
  It's what lets `STATUS.md` stay short — the history lives here, not there.
- **`CONTENT_CATALOG.md`** — *Reference.* The curated source roster (feeds, authors, notes).
- **`LEARNED_LESSONS.md`** — *Reference (meta).* Process lessons from building this project —
  the doc-hygiene and dev-cycle practices worth reusing on the next project.
- **`archive/`** — *Ephemeral, retired.* Planning/thinking docs that have served their
  purpose. Kept for provenance (git has them too); not part of the live doc set. Currently:
  `NEXT_STAGE_OPTIONS.md`, `EPIC_24_CLIENT_PAGINATION.md`.

## Adding a new doc

Decide its **kind** first (the table above), and put the answer in its opening line. If it's
a thinking/planning doc, expect it to end up in `archive/` once the decision it explores is
made — move it there and record the decision in `DECISIONS.md`. That one habit is what keeps
`docs/` from silently accreting dead files.
