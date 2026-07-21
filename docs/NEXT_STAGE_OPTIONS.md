# Next-stage options — content sourcing

Working notes on how to source and manage reading content for korean-reader, captured
2026-07-21. This is a thinking doc, not a spec — nothing here is committed scope yet.

## Where the app stands

Epics 0–5 done: the app can tokenize Korean (kiwipiepy, lemma-based), store books/pages,
translate + save terms by dictionary form, highlight all inflections, and drive the whole
tap → translate → enrich → save flow. Remaining: Epic 6 (Anki sync), 7 (terms/settings
pages), 8 (ops + Lute retirement). The machine is nearly done; its value now hinges on
**content**.

Content sources already tagged in the schema: `paste | txt | yt | pdf`.
- Paste + .txt upload: wired into the UI.
- YouTube subs (`import_tools/yt_subs.py`) and PDF (`import_tools/pdf_text.py`): working
  CLI scripts that emit a cleaned `.txt`; not yet wired into the app.

## The core worry

Sourcing content the user actually cares about, at a level that's readable — and knowing
whether a given epub/article is an easy or hard read *before* committing to it.

## Three threads

### 1. Difficulty — compute it against the user's own vocabulary, not external labels

For a learner, difficulty is the relationship between the text and what you already know,
not a fixed property of the text. The app already has both halves:
- kiwipiepy lemmatizes any candidate text into dictionary forms.
- The `terms` table records which lemmas are known / learning / ignored.

So difficulty is computable for any text (epub, article, transcript) before reading:
- **Known-lemma coverage %** — fraction of unique lemmas already known. Rules of thumb:
  ~95–98% comfortable, ~90–95% productive study zone, <85% a slog.
- **New lemmas per page** — often more actionable than the %. "≈4 new words per page" tells
  you the reading cost at a glance.

External lists (TOPIK 1–6 vocab, frequency rankings) are a useful **secondary / cold-start**
signal — tag lemmas with frequency rank so texts full of rare words flag as hard even before
the known-set is large. But personal coverage is the primary metric, and it's cheap because
the tokenizer already runs.

Payoff for epubs: a "score this text" tool — point it at a sample chapter, get coverage %
and new-words-per-page. The bookstore not listing a level stops mattering.

### 2. Automation — RSS backbone + existing importers

A daily "bring me content I care about" pipeline, mostly on RSS:
- **News** — most Korean news sites expose RSS by section.
- **YouTubers** — every channel has an RSS feed
  (`youtube.com/feeds/videos.xml?channel_id=…`); combined with `yt_subs.py` this auto-pulls
  transcripts of new uploads from favorite channels. Strongest early-automation hook.
- **Game guides / reviews / fitness** — RSS where available; per-site scrapers for the
  handful of sources worth the effort.

Daily job (Windows Task Scheduler): fetch feeds → clean text (reuse yt_subs/pdf_text +
article extractor) → score difficulty → dedupe → auto-create a book with a topic tag, only
importing items within a chosen difficulty band.

Caution: **build the interest list before the automation.** A firehose of lukewarm content
rots in the queue and makes the app a chore. Nail the specific sources first.

### 3. DB expansion — yes, to support sorting/filtering/dedup/difficulty

On `books`:
- `topic` / `tags` — JSON or comma text column (single-user; a tags join table is overkill;
  matches the `settings.decks` JSON pattern).
- `source_url` + `source_ref` (stable id: video id / feed guid) — with a **unique index** on
  `source_ref` so the daily job never re-imports the same item.
- `difficulty` — cached coverage % / new-per-page, to sort the queue by "easiest unread".
- `fetched` date + `archived`/`read` flag — to keep the auto-imported queue manageable.

New `feeds` (subscriptions) table:
`id, name, type (rss|youtube|scraper), url_or_channel_id, topic, enabled, difficulty_min,
difficulty_max, last_fetched` — what the daily script iterates and a future settings page
edits.

## Decision so far

Of the four possible first steps (difficulty scorer · content/interest list · DB+schema ·
daily pipeline), the chosen starting point is the **content / interest list**: define the
real sources the user cares about — and confirm what's RSS-able — before writing any
automation.

## Source catalog — the shape to fill in

One row per source: **name/URL · type (RSS | YouTube | needs-scraper) · feed available? ·
topic tag · rough difficulty tier**. End product: a ranked shortlist of "definitely
automate" vs. "needs a custom scraper, do later".

Reality check on the user's stated interests (news, video games, guides/reviews, gym):
these skew native-adult / fast-register, so early coverage may sit below the comfortable
zone (Hanja-heavy news vocab, gaming slang/abbreviations, fitness English loanwords). Worth
also cataloguing learner-friendly / simplified sources in the same topics as a ramp — and
noting that casual YouTube transcripts are often *easier* than written news.

(The Hanja angle has been split into its own thinking doc — studying Hanja as a *separate*
track, not for the reader: see `HANJA_STUDY_OPTIONS.md`.)

## Open questions (TODO — not yet answered)

- Korean reading level (early / solid / upper-intermediate+) — sets how hard to aim sources.
- Preferred register to automate first (YouTube transcripts vs. written articles vs. both).
- Games: news/community (인벤, 루리웹) vs. guides for specific games vs. gaming YouTubers?
- Fitness: YouTubers/vloggers vs. written blog/article content?
- Specific YouTubers already followed (to check for usable Korean captions).
- English things read for fun that want a Korean equivalent.
