# korean-reader

Korean reading setup: **Lute v3** (reader with clickable words, saved terms, highlights)
plus a small **translation service** that shows DeepL/Claude translations inside Lute's
dictionary pane, plus import tools for YouTube subtitles and PDFs.

## Daily use

Double-click / run `start.ps1` — it opens two windows (Lute on :5001, translator on :8001)
and your browser at http://localhost:5001. Keep Anki open if you want to export cards.

Reading flow: open a book → click an unknown word → the pane shows the DeepL/Claude
translation + krdict entry → type/paste the meaning into the term form → Save.
Click a sentence's "translate sentence" icon for full-sentence translation.
Term statuses (1-5 / known / ignore) are your persistent highlights — they show
every time you reopen the text.

## One-time setup (still to do)

### 1. API keys → `.env`
Copy `.env.example` to `.env` and fill in:
- **DEEPL_API_KEY** — free at https://www.deepl.com/pro-api ("DeepL API Free", 500k chars/month).
- **KRDICT_API_KEY** — free at https://krdict.korean.go.kr/openApi/openApiInfo (instant, needs an account).
- **ANTHROPIC_API_KEY** — only when you want to try the Claude backend; then set `TRANSLATOR=claude`.
Restart the translate service after editing `.env`.

Test: http://localhost:8001/lookup?text=사랑 should show a translation, not an error.

### 2. Anki export (AnkiConnect)
1. In Anki desktop: Tools → Add-ons → Get Add-ons → code **2055492159** (AnkiConnect).
2. Tools → Add-ons → AnkiConnect → Config → add Lute to `webCorsOriginList`:
   ```json
   { "webCorsOriginList": ["http://localhost", "http://localhost:5001"] }
   ```
3. **Restart Anki** (required).
4. In Lute: Settings (hamburger menu) → Anki export → map fields, e.g. note type "Basic":
   Front = `{{ term }}`, Back = `{{ translation }}<br>{{ sentence }}`.
   Then select terms on the Terms page → Export to Anki.
5. AnkiWeb sync gets the cards to AnkiDroid for free.

### 3. Phone on Wi-Fi
Lute and the translator already listen on all interfaces. Find your PC's IP
(`ipconfig` → IPv4, e.g. 192.168.1.20) and open `http://192.168.1.20:5001` on your phone.

Two gotchas:
- Windows Firewall will prompt the first time — allow Private networks for Python,
  or add inbound rules for TCP 5001 and 8001.
- The dictionary URLs registered in Lute use `localhost:8001`, which the phone can't
  reach. In Lute: Settings → Languages → Korean → change both
  `http://localhost:8001/lookup?text=[LUTE]` entries to `http://<your-PC-IP>:8001/lookup?text=[LUTE]`.
  (Works from the PC too.)

## Importing texts

- **Short stories / any text**: Lute → New book → paste text or upload .txt.
- **YouTube**: `.venv\Scripts\python import_tools\yt_subs.py "https://youtube.com/watch?v=..."`
  → creates a cleaned .txt (manual Korean subs preferred, auto-subs as fallback).
- **PDF**: `.venv\Scripts\python import_tools\pdf_text.py book.pdf --pages 1-30` → .txt.

## Switching translation backends

Edit `.env`: `TRANSLATOR=deepl` or `TRANSLATOR=claude`, restart the service.
Per-request override for comparing: add `&backend=claude` to the lookup URL.
Every result is cached in `translate_cache.sqlite3`, so repeat lookups are free.

## Korean conjugations (later, if needed)

Lute's space-delimited parser doesn't link 했어요 → 하다 automatically. Use Lute's
"parent term" field while reading (type the dictionary form; it links and highlights
together). If that gets tedious, options: adapt [lute-lemma](https://github.com/LuteOrg/lute-lemma)
with Stanza's Korean model, or write a kiwipiepy-based Lute parser plugin.

## Layout

```
.venv/                  everything installed here (lute3, fastapi, yt-dlp, pymupdf, anthropic)
translate_svc/          FastAPI tooltip service (port 8001)
import_tools/           yt_subs.py, pdf_text.py
start.ps1               launches Lute + translator
.env                    your API keys (copy from .env.example)
translate_cache.sqlite3 translation cache
```

Lute's own data (books, terms, settings) lives in `%LOCALAPPDATA%\Lute3\Lute3\lute.db` — back it up
if you care about your reading history. Note: the Korean language definition was added
inside `.venv\...\lute\db\language_defs\korean\`; if you ever recreate the venv, the
language is already saved in your Lute DB, so nothing is lost.
