# Epic 24 — Client-side pagination (exact N lines per device)

*Ephemeral / planning doc. Delete or move to `docs/archive/` once the epic ships; the
decision goes in `docs/DECISIONS.md`.*

## Problem

Reader pages are split **server-side** by `split_pages_by_rows` using a single global
`chars_per_row: 32` estimate (`server/paging.py:45`). The server can't know the client's
viewport, so the estimate is wrong on every device, and wrong by *different factors*:

| | content width | chars/row at `text-lg` (18px, full-width Hangul) |
|---|---|---|
| Web (`max-w-lg` 512px − 32px padding) | 480px | ≈ 27 |
| Phone (~390px − 32px padding) | 358px | ≈ 20 |
| Configured estimate | — | **32** |

Observed 2026-07-27: same page 7 renders **11 lines on web, 14 on mobile**. Page length is
also *irregular between pages*, because the estimate is only wrong for long lines — a page
of short dialogue lines estimates correctly, a page of long paragraphs badly.

Root cause is structural, not a tuning miss: **one shared `pages` table serves both devices**,
and `current_page` / `page_reads` are keyed to those global page numbers. No value of
`chars_per_row` can fix it.

## Decision (2026-07-27, with user)

Move pagination to the **client**, and let the browser do it via CSS columns:

```css
height: 15lh;        /* exactly 15 rendered lines, any device */
column-width: 100%;
column-gap: 0;
```

The `lh` unit = one line-height, so the browser breaks a column every N *real* lines,
measured after wrapping. No estimate, no measurement loop, no resize handler.

**Line count is per-device** (localStorage, not a server setting): phone = 15, web free to
run longer. Accepted consequence: page *boundaries* and page *counts* differ across devices.
Reading position syncs by **character offset**, so switching devices lands on the same
sentence; only the page numbers differ.

**Footer shows percentage, not page numbers** (decided 2026-07-27). `49%` is derived from the
char offset so it reads identically on every device, sidestepping the only user-visible
consequence of per-device pagination.

Retires `settings.page_rows`, `settings.chars_per_row`, `paging.split_pages_by_rows`,
`paging.estimate_rows`, and `settings.repaginate_all`.

**Not affected:** `new_per_page` difficulty scoring uses the separate fixed 1500-char
`split_pages` (`server/difficulty.py:89`) — deliberately independent of reader pagination.

## Key simplification

**Keep the `pages` table as a storage substrate; stop treating `page_no` as a reading unit.**
The rows already hold the book's text as contiguous, lossless slices (`repaginate_all`
relies on this). The new endpoint just joins and slices them by character offset. No content
migration, no re-splitting — this keeps the blast radius small.

## Sizing (measured on live `reader.db`, 481 books)

median **1,843** chars · p90 **14,107** · p99 **45,221** · max **104,198** (long YT transcripts)

Whole-book delivery is fine at the median but not at the tail — a 104k-char book tokenizes
to ~1–2.5 MB of token JSON. Hence a **windowed** endpoint rather than whole-book.

## Plan

### Server

1. **Extract** the ~50-line term-matching block currently inline in `get_page`
   (`server/routes/books.py:351-404`) into `_terms_for_lemmas(conn, lemmas)`. Pure refactor,
   no behaviour change — `get_page` keeps working during the transition.
2. **New** `GET /api/books/{id}/text?offset=<int>&window=<int>` →
   `{offset, content, tokens, terms, total_chars}`.
   - Joins `pages.content` in `page_no` order, slices `[offset, offset+window)`.
   - Snaps both ends **outward** to sentence/newline boundaries (reuse `paging._BREAK_RE`)
     so a window never starts or ends mid-sentence.
   - `tokens` offsets are **absolute** (window offset added), so the client can map a
     rendered token straight back to a book position.
   - Default window ~20k chars: covers a median book whole, ~3 fetches for 어린 왕자.
   - Stamps `last_opened` (moved from `get_page`).
3. **Schema** (additive, via `db.py`'s column map): `books.current_offset INTEGER DEFAULT 0`.
   Backfill once from `current_page` by summing prior page lengths — same arithmetic
   `repaginate_all` already does (`server/routes/settings.py:111`). Leave `current_page` in
   place, unused by the reader, until stage 2.
4. **Retire** `page_rows` / `chars_per_row` from `SettingsPut` + `DEFAULTS`, delete
   `repaginate_all` and its call site. Delete `split_pages_by_rows` / `estimate_rows` and
   their tests; `_insert_book` switches to plain `split_pages` for storage chunking.

### Client

4b. **Fix Korean mid-word wrapping** (pre-existing bug, found 2026-07-27; not caused by this
   epic). There is no `word-break` rule anywhere in `web/` — so the article inherits
   `word-break: normal`, under which browsers may break between any two Hangul syllables.
   `성공` can render as `성` / `공`. Harmless at a line break; **bad at a column break**,
   where the halves land on two different screens. Add to the article:

   ```css
   word-break: keep-all;      /* break only at spaces — 어절 boundaries, standard for Korean */
   overflow-wrap: break-word; /* escape hatch for an unbroken run longer than one line (URLs) */
   ```

   Note this fix was *incompatible* with the old design — `keep-all` yields a more ragged
   right edge, i.e. more real rows than `chars_per_row` predicts, worsening the estimate.
   Under browser pagination it is free: the browser counts what it actually laid out.

   **Not affected by wrapping** (verified, no work needed): the tokenizer runs server-side on
   the raw string (`books.py:348`) and wrapping inserts no characters; the popover resolves
   via `closest("[data-token-index]")` (`read/page.tsx:161`) and a wrapped span is still one
   element with one index; highlight spans likewise paint across both fragments.

5. **Reader** (`web/app/read/page.tsx`) renders the window inside a column container
   (`height: {lines}lh; column-width: 100%; column-gap: 0; overflow: hidden`), translating
   horizontally by column index. Prev/Next step one column; at the last column of a window,
   fetch the next window and reset to column 0.
6. **Per-device setting** in localStorage (`readerLines`, default **15**), with a control on
   `/settings` — clearly labelled as this-device-only, replacing the Page-size section.
7. **Position** = the absolute offset of the first token in the active column, read off the
   DOM; persisted via `PATCH /api/books/{id}` (`current_offset`), debounced. On open, the
   client fetches the window containing `current_offset` and scrolls to the column
   containing it.

### Risks / to verify

- **`lh` unit support**: Chrome 109+, Safari 16.4+, Firefox 120+. Fine on a current phone;
  fall back to `calc(N * <line-height>)` if the phone's browser is older than expected.
- **Popover positioning — checked 2026-07-27, NOT a risk.** `TokenPopover` is a full-screen
  overlay (`fixed inset-0 … items-end sm:items-center`, `TokenPopover.tsx:271`) — a bottom
  sheet on mobile, centred on desktop. It never anchors to the tapped token, and it renders
  as a *sibling* of `<article>` (`web/app/read/page.tsx:260`), outside the column container.
  No change needed. Residual footnote: `position: fixed` resolves against a transformed
  ancestor, so scroll the columns with `scrollLeft`, **not** `translateX`, and the hazard
  cannot arise even if the popover later moves inside the container.
- **`TokenPopover` takes `pageNo`** (`web/app/read/page.tsx:264`) for term provenance —
  rekey to a char offset. Mechanical.
- **Dwell-based read logging** (`READ_DWELL_MS`, `web/app/read/page.tsx:20`) is keyed to
  `page_no` — needs rekeying (see below).

## The pages-read stat — decided 2026-07-27

User: *"we can ditch the pages read stat, it's not being helpful — the rest can stay if it
is free info."* So the **counts** go. But `page_reads` has a non-obvious second consumer:

`server/routes/stats.py:143` builds `active_days` from `set(words_by_day) | set(pages_by_day)`,
so **the reading streak counts a day active if you saved a word _or_ read a page.** Delete
`page_reads` outright and the streak silently becomes words-only — a day spent reading a
book you mostly understand, saving nothing, would break the streak.

**Resolution:** replace `page_reads (book_id, page_no)` with `read_days (book_id, day)`,
`UNIQUE(book_id, day)`, logged on the same dwell timer. No page numbers, so nothing is
device-dependent.

| consumer | fate |
|---|---|
| streak (`stats.py:143`) | **kept**, unchanged semantics — reads still count as activity |
| `pages` series on the activity chart (`stats.py:138`) | dropped, or becomes books-read-that-day |
| `pages_week` (`stats.py:148`) | dropped |
| per-book `pages_read` (`stats.py:160`) | dropped from the new-words-per-book table |

Data loss: negligible (3 rows, 2 days, 1 book as of 2026-07-27).

## Delivery

Stage in two commits, both on `main`:

- **Stage 1 — the visible fix**: steps 1–3, 5–7. Reader shows exactly N lines, per device,
  no overflow. `page_rows`/`chars_per_row` still exist but are ignored by the reader.
- **Stage 2 — the cleanup**: step 4 + the stat rework. Removes the dead settings, the
  `repaginate_all` machinery, and `current_page`.

Exit criteria per `CLAUDE.md`: `pytest server/tests -q` green, `npm run build` **and**
`npm run lint` green in `web/`, docs updated, one commit per stage.

## Note for the executor

`web/AGENTS.md`: this repo's Next.js has breaking changes vs. training data — read the
relevant guide in `node_modules/next/dist/docs/` before writing frontend code.
