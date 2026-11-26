# Unit 8 audit: curated fix list (2026-11-17)

**Status:** items 1, 3, 4, 5, 6 fixed in unit 9; 8, 9, 11, 12 in unit 15; item 2 deferred to issue #1; the rest open.

*Ephemeral.* The pick list from unit 8's six blind audits plus `/ponytail-audit`. The user
picks; the fixes are a follow-up unit. Move to `archive/` once that unit ships. How the
audit ran and which agents earned their keep: `DECISIONS.md`, 2026-11-17.

Each line: what, where, fix, who found it (V vulnerabilities, M user mistakes, E error
handling, D data integrity, S fresh setup, L lemma, P ponytail). ✔ = verified in the main
session by reading the code; others were confirmed by the agent's own probe test or are
marked plausible.

## Tier 1: data loss or exposure, small fixes

1. ✔ **Anki sync isn't crash-safe.** One commit at the end (`server/routes/anki_sync.py:179`):
   any exception mid-run (DB error, `KeyError`, non-JSON reply `anki.py` `_invoke`, a 5 s
   timeout after Anki already added the note) drops every `anki_note_id` stamped so far;
   those terms then fail "duplicate" on every sync, forever. Also: an edit saved while sync
   runs is cleared by `SET anki_dirty = 0` and never reaches Anki. Fix: commit per note;
   wrap JSON/other errors as `AnkiError`; on "duplicate", adopt the note via `findNotes`;
   clear dirty only `WHERE updated = <value read>`. (E, M, D: three agents independently)
2. ✔ **App reachable from the whole LAN, no auth.** `compose.yaml:13` publishes
   `8002:8002` on every interface; Dockerfile and `start.ps1` bind `0.0.0.0`; no Host or
   Origin check, so DNS rebinding and cross-site multipart POSTs work from any web page.
   Fix: publish on the tailnet IP (or `tailscale serve`) instead of all interfaces, plus
   `TrustedHostMiddleware`. Loopback-only would cut off the phone. (V)
3. ✔ **`scripts/sqlite_to_pg.py` can wipe a database from a typo.** A wrong or missing path
   (even `--help`) makes `sqlite3.connect` create an empty file, then `DELETE FROM feeds`
   and `vocab_levels` (`:62-63`) run against `DATABASE_URL`, whose code default is the live
   compose db. This is what happened in this audit (see DECISIONS). Fix: refuse unless the
   file exists, open it `mode=ro`, require the target URL explicitly and print it. (S)
4. ✔ **Duplicate import poisons the transaction.** `insert_book` re-raises on
   `UniqueViolation` without `conn.rollback()` (`server/routes/books.py:126`): a subtitle
   batch with a duplicate sorted before a new file returns 500 after a partial import;
   racing feed fetches 500 too. Fix: one `conn.rollback()`. (E)
5. ✔ **Renaming a lemma never re-syncs the card.** `lemma` missing from
   `_DIRTY_TRIGGER_FIELDS` (`server/routes/terms.py:16`). Fix: add it. (M, D)
6. **Upload limits and the EPUB zip bomb.** ebooklib inflates every zip entry: a 306 KB
   EPUB hit 601 MB (confirmed). Uploads are read whole (`imports.py:147,262`), no cap.
   Fix: size cap per upload; read EPUBs with stdlib `zipfile` + `ElementTree` with an
   entry-size/ratio check, which also drops the ebooklib dependency (P). (V, P)

## Tier 2: user-facing loss and wrong data

7. **Discard can't be undone and blocks re-import.** Discarding a Queue article/YouTube
   item purges its text at once (`books.py:87,270`), no confirm, no undo, and the kept
   `source_ref` makes a re-import 409. Fix: purge only on expiry, Undo toast, let re-import
   replace a discarded row. (M)
8. **One tap loses work.** Term delete has no confirm (`TokenPopover.tsx:646`) and cascades
   the hand-built card; backdrop click closes the popover and every Sheet with unsaved
   input (`web/lib/sheet.tsx:19`). Fix: confirm on delete; ignore backdrop clicks while
   dirty. (M)
9. **Deleted seed feeds come back on restart.** `_seed_feeds` re-inserts any missing seed
   URL at every startup (`server/db.py`); editing a seed URL yields a duplicate. Fix: seed
   only when `feeds` is empty. (M, D, S: three agents)
10. **Lemma errors from the wrapper, ~3.6% of tokens.** Rule 1 always appends 하다
    (`server/tokenizer.py:89-91`): 해결됐어요 → 해결하다 (want 해결되다), 교육시켰다 →
    교육하다; kiwi's `XSA-I` tag misses the exact set, so 자연스럽게 → 자연, 평화로운 → 평화.
    Also: compound nouns cut to the first part (기자회견 → 기자), 잘하다/못하다 → 잘/못,
    MM (새, 모든, 한번) and counters after numbers (3시) untappable. Fix: suffix form + 다
    with `startswith`; join adjacent NNG; MAG+하 rule; MM/SN rules. Borderline cases for
    you to judge (aux verbs 도와주다 → 돕다, VX 보다 vs VV 보다, 그거/그것): agent report in
    DECISIONS. (L)
11. **Imported text can run JS inside Anki.** Card fields are `"<br>".join`ed unescaped
    (`anki_sync.py:23-85`); subtitle cleanup unescapes `&lt;img onerror=…&gt;` into real
    HTML. Fix: `html.escape` each part. (V)
12. **Lemma not normalized.** `"입다 "` and `"입다"` save as two terms; NFD vs NFC too;
    rename race gives 500 not 409 (`terms.py:212,270,286`). Fix: `NFC(strip())`, catch
    `UniqueViolation`. (M, D)

## Tier 3: error handling and robustness

13. **Raw 500s instead of clear errors.** DeepL transport errors and a bad JSON body escape
    `TranslationError` (`translate_svc/translators.py:18`); embed 4xx and an empty Ollama
    reply 500 in `usage.py:44,242`; AnkiConnect non-JSON (`anki.py`). Fix: map to the
    existing error types. (E)
14. **Outbound fetches unguarded.** No private-IP/scheme check on article, yt-dlp and RSS
    URLs (SSRF to ollama/embed/AnkiConnect from inside the container); RSS body uncapped,
    per-read timeout only (`server/feeds.py:22`). Fix: http(s) only, refuse private
    addresses, byte cap + total deadline. (V)
15. **Fetch is one long blocking request.** RSS items uncapped (YouTube capped at 5), ~3 min
    and 185 candidates on a fresh DB; one unexpected exception aborts the run
    (`feeds.py:331-344`); `last_fetched` stamped even on error (`:466`). Fix: cap per feed,
    catch per item, skip the stamp on error. (E, S)
16. **krdict: one failure = 30 min dead dictionary** (`translate_svc/krdict.py:60`); no key
    returns `[]` 200, which reads as "no results". Fix: trip after N failures; 503 on no
    key. (E, S)
17. **Smaller:** reading-position save swallowed with no retry (`read/page.tsx:195`);
    `termByLemma` turns any error into "not saved" (`web/lib/api.ts:338`); `split_pages`
    is O(n²), ~15 s at 3 MB (bisect); known term re-promoted right after a manual demote;
    queue purge lacks a `status`/`feed_id` guard; no `connect_timeout` on psycopg;
    LLM prompt doesn't fence library text, and the explain cache keys on client-sent
    examples. (E, M, D, V)

## Tier 4: setup and docs drift

18. **Fresh setup stumbles** (S): `docker compose up` requires an NVIDIA GPU
    (`compose.yaml:72`) and pulls ~2 GB for embed, no minimal-start line near the top; no
    venv/Python 3.14 step; `start.ps1` never runs `npm ci` (no Node version documented);
    missing `web/out` gives a silent 404; `TEST_DATABASE_URL` undocumented; ports and
    `image: mbxread` not overridable for a second clone; `TZ=Asia/Seoul` from `.env` is
    misread on Windows dev runs (plausible); seed feeds undocumented.
19. ✔ **Docs that lie:** README:100-127 says YouTube/PDF import is a CLI-and-paste job
    (the UI has Article/YouTube/PDF/EPUB/Subtitles); ANKI.md:36 says note type `Basic`
    Front/Back (code uses `Korean Reader 2-way`, Korean/English/Examples). (S)
20. ✔ **Test template has a fixed name** (`server/tests/conftest.py:17`): two pytest runs
    at once drop each other's template (69 errors in one audit run). Fix: per-run name. (D)
21. **Default DB password `mbxread` in public code**; make `POSTGRES_PASSWORD` required. Low
    while 5433 is loopback-only. (V)

## Ponytail (over-engineering, whole repo)

Lean overall: 11 runtime deps, all doing real work; no single-implementation layers.
- `yagni:` `TRANSLATOR` env var + `_BACKENDS` registry + `backend` request field for one
  backend. Call `_deepl` directly. [translate_svc/config.py, translators.py, routes/translate.py]
- `delete:` the four `__main__` CLIs in `import_tools/` and README's CLI import section;
  the in-app import covers all of them. [import_tools/*.py, README.md]
- `delete:` `'scraper'` in the `feeds.type` CHECK (feature removed 2026-10-21). [server/db.py:108]
- `yagni:` `method` on the public `/api/usage` body; only `scripts/eval_usage.py` picks a
  method, and it calls `usage.search` directly. [server/routes/usage.py]
- `stdlib:` ebooklib → `zipfile` + `ElementTree` (merged into item 6).

net: about -70 lines, -1 dep possible.
