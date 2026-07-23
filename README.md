# korean-reader

Personal Korean reading app: read texts, tap unknown words, translate them (DeepL or
Claude), hand-enrich the translation, save by **dictionary form (lemma)** so every
inflection highlights, and bulk-sync saved terms to Anki via AnkiConnect. FastAPI +
SQLite + kiwipiepy backend, Next.js frontend (static export), one server, phone access
via Tailscale.

This replaces the earlier Lute-based setup — Lute is fully retired.

## Daily use

Double-click `start.ps1`. It rebuilds `web/` if the frontend source is newer than the
last build, launches the server on **:8002**, and opens your browser at
`http://localhost:8002`. Keep Anki open if you want to sync terms.

Reading flow: open a book → tap an unknown word (or drag-select a phrase) → Translate
and/or look it up in the dictionary → edit the translation freely → pick a deck → Save.
Every inflection of that word's dictionary form highlights from then on. Tap a
highlighted word to edit it, mark it known, ignore it, or delete it.

## One-time setup

### 1. API keys → `.env`

Copy `.env.example` to `.env` and fill in:
- **DEEPL_API_KEY** — free at https://www.deepl.com/pro-api ("DeepL API Free", 500k
  chars/month).
- **KRDICT_API_KEY** — free at https://krdict.korean.go.kr/openApi/openApiInfo (instant,
  needs an account).
- **ANTHROPIC_API_KEY** — only if you want the Claude translation backend instead of
  DeepL; then set `TRANSLATOR=claude` (or switch backends anytime in the app's Settings
  page).

Restart the server after editing `.env`.

### 2. Anki sync (AnkiConnect)

See **`ANKI.md`** for the full setup and daily-use guide. Short version: Anki desktop
with the AnkiConnect add-on (code `2055492159`) installed and open; no CORS
configuration needed, since the sync call is server-to-server, not from the browser.

### 3. Phone access via Tailscale

Tailscale gives your phone a private, always-the-same address to this PC without
opening anything to the public internet.

1. **Install Tailscale on this PC**: https://tailscale.com/download, run the installer,
   sign in (any of Google/Microsoft/GitHub/email works — use the same account on your
   phone in the next step).
2. **Install Tailscale on your phone**: search "Tailscale" in the App Store / Play
   Store, sign in with the same account.
3. **Find this PC's Tailscale name**: open the Tailscale app/tray icon on the PC, or
   run `tailscale status` in a terminal — look for this machine's entry, something like
   `your-pc-name`. Its full address is `your-pc-name.<tailnet-name>.ts.net` (also
   visible in the admin console at https://login.tailscale.com/admin/machines).
4. **Windows Firewall**: the first time the server starts and binds to all interfaces
   (`--host 0.0.0.0`), Windows will prompt to allow it through the firewall — allow it
   for **Private networks**. If you miss the prompt, add an inbound rule for TCP 8002
   (Windows Defender Firewall → Advanced Settings → Inbound Rules → New Rule → Port →
   TCP 8002 → Allow).
5. **On your phone**, with Tailscale connected, open
   `http://<your-pc-name>.<tailnet-name>.ts.net:8002`.

Both devices need Tailscale running and signed into the same account for this to work;
neither the app nor port 8002 is ever exposed to the public internet.

## Importing texts

- **Paste or upload**: in the app, "+ Add" → paste text or upload a `.txt` file.
- **YouTube**: `.venv\Scripts\python import_tools\yt_subs.py "https://youtube.com/watch?v=..."`
  → creates a cleaned `.txt` (manual Korean subs preferred, auto-subs as fallback).
  Paste the result into the app.
- **PDF**: `.venv\Scripts\python import_tools\pdf_text.py book.pdf --pages 1-30` →
  `.txt`. Paste the result into the app.

## Automated content fetching (Task Scheduler)

The Queue (`/queue`) pulls new candidates from your feeds on demand via the "Fetch new
candidates" button (`POST /api/feeds/fetch`). To also run this automatically on a
schedule, register `scripts/fetch_feeds.ps1` as a Windows Task Scheduler action:

1. Open **Task Scheduler** → **Create Task…** (not "Create Basic Task" — you need the
   full dialog for the arguments below).
2. **General**: name it e.g. `korean-reader fetch feeds`.
3. **Triggers** → **New…**: Daily, pick a time (e.g. 6:00 AM), recur every 1 day.
4. **Actions** → **New…**: Program/script `powershell.exe`; arguments:
   `-ExecutionPolicy Bypass -File "C:\path\to\korean-reader\scripts\fetch_feeds.ps1"`
   (adjust the path to where you cloned this repo).
5. **Conditions**: uncheck "Start the task only if the computer is on AC power" if this
   machine should still fetch on battery.

The script assumes **the server is already running** — it just POSTs to the existing
`/api/feeds/fetch` endpoint on `localhost:8002`, exactly like the manual button. Its
result (or error) is appended to `scripts/fetch_feeds.log`; Task Scheduler's own run
history also shows failures, since the script exits non-zero on one.

Two related settings, editable in `/settings`:
- **Queue candidate retention** — how many days an unpromoted, undiscarded candidate
  sits in the Queue before the fetch job auto-discards it (default 7 days). Checked on
  every fetch call, scheduled or manual.
- The timestamp of the last fetch *attempt* (scheduled or manual) is tracked
  internally (`GET /api/settings` → `last_fetch_attempt`) and will be surfaced on the
  Queue page itself in a later pass.

## Switching translation backends

Settings page in the app (`/settings`) → Translator backend → DeepL or Claude. Every
translation is cached, so repeat lookups of the same text are free.

## Layout

```
server/                 FastAPI app (port 8002): API routes, sqlite (reader.db), tokenizer
web/                    Next.js frontend, built to web/out and served by server/main.py
translate_svc/          DeepL/Claude translation + cache + krdict, imported as a library
import_tools/           yt_subs.py, pdf_text.py
docs/                   architecture/spec/decision docs — read docs/STATUS.md first if developing
scripts/fetch_feeds.ps1 Task Scheduler action for automated feed fetching (see above)
start.ps1               rebuilds web/ if stale, launches the server, opens the browser
ANKI.md                 Anki sync setup and daily-use guide
.env                    your API keys (copy from .env.example)
reader.db               your books/pages/terms — never committed
translate_cache.sqlite3 translation cache — never committed
```
