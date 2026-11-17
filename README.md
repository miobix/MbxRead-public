# MbxRead

Personal Korean reading app: read texts, tap unknown words, translate them (DeepL),
hand-enrich the translation, save by **dictionary form (lemma)** so every
inflection highlights, and bulk-sync saved terms to Anki via AnkiConnect. FastAPI +
Postgres + kiwipiepy backend, Next.js frontend (static export), one server, phone access
via Tailscale.

## Daily use

**Runs in Docker.** `docker compose up -d --build` once (see "Run with Docker"). Both the
app and its Postgres have `restart: unless-stopped`, so they come back whenever Docker
Desktop starts; turn on "Start Docker Desktop when you sign in" in Docker Desktop's
settings and the app is just there at `http://localhost:8002`. Logs: `docker compose logs
-f mbxread`. After pulling changes: `docker compose up -d --build`.

`start.ps1` is for **development**: it rebuilds `web/` if the frontend source is newer
than the last build, starts the compose Postgres, then runs the server in a visible
console (tracebacks live) and opens your browser at `http://localhost:8002`. Stop the
compose app first (`docker compose stop mbxread`), since both want port 8002.

Keep Anki open if you want to sync terms.

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

## Run with Docker

```
cp .env.example .env      # then fill in your keys
docker compose up -d --build
```

- Open `http://localhost:8002`. One container serves the web UI and the API
  (`/api/health` for a check).
- Your data lives in Postgres (the `db` service, volume `mbxread-pg`), reachable from the
  host at `127.0.0.1:5433` for dev runs and tests. Set `TZ` in `.env` (e.g. `Asia/Seoul`):
  it decides which local day a read or a saved word counts for.
- **Coming from an old SQLite `reader.db`?** With the db up and empty, run once:
  `.venv\Scripts\python.exe -m scripts.sqlite_to_pg postgresql://mbxread:mbxread@127.0.0.1:5433/mbxread reader.db translate_cache.sqlite3`.
  It keeps ids (so Anki links survive), prints the target before writing, and refuses a
  database that already has data or a SQLite path that doesn't exist.
- **Anki sync** works when Anki runs on the same computer as Docker: compose points the
  server at `host.docker.internal:8765` (`ANKICONNECT_URL`). Docker Desktop (Windows/Mac)
  needs nothing else. On Linux, set AnkiConnect's `webBindAddress` to `0.0.0.0` (Anki →
  Tools → Add-ons → AnkiConnect → Config), since its default `127.0.0.1` refuses
  connections from containers.
- **Similar usage** (popover button) needs two more services that compose starts: `embed`
  (sentence embeddings, downloads ~2 GB of weights on first start) and `ollama` (local
  LLM). Pull its model once: `docker compose exec ollama ollama pull gemma4:e4b`. New
  library books are indexed in the background.
- Running locally instead: `pip install -r requirements-dev.txt` (runtime deps plus
  pytest) and `docker compose up -d db`. Tests need that db too (each test gets its own
  throwaway database). The image installs `requirements.txt` only.

## Importing texts

- **Paste or upload**: in the app, "+ Add" → paste text or upload a `.txt` file.
- **YouTube**: `.venv\Scripts\python import_tools\yt_subs.py "https://youtube.com/watch?v=..."`
  → creates a cleaned `.txt` (manual Korean subs preferred, auto-subs as fallback).
  Paste the result into the app.
- **PDF**: `.venv\Scripts\python import_tools\pdf_text.py book.pdf --pages 1-30` →
  `.txt`. Paste the result into the app.

## Fetching content

The Queue (`/queue`) pulls new candidates from your feeds with the "Fetch new
candidates" button (`POST /api/feeds/fetch`). Fetching is manual; there is no
scheduled job.

- **Queue candidate retention** (in `/settings`): how many days an unpromoted,
  undiscarded candidate sits in the Queue before a fetch auto-discards it (default
  7 days). Checked on every fetch.
- The time of the last fetch *attempt* is stored (`GET /api/settings` →
  `last_fetch_attempt`) and shown on the Queue page.

## Layout

```
server/                 FastAPI app (port 8002): API routes, Postgres schema, tokenizer
web/                    Next.js frontend, built to web/out and served by server/main.py
translate_svc/          DeepL translation + cache + krdict, imported as a library
import_tools/           yt_subs.py, pdf_text.py
docs/                   architecture/spec/decision docs — read docs/STATUS.md first if developing
scripts/sqlite_to_pg.py one-off copy of an old SQLite reader.db into Postgres
start.ps1               dev launcher: rebuilds web/ if stale, visible console, opens browser
Dockerfile              app image, API + web (see "Run with Docker"); .dockerignore is an allowlist
compose.yaml            app + Postgres + embed + ollama, .env, the route to desktop Anki: the daily launcher
requirements.txt        runtime deps (what the image installs)
requirements-dev.txt    + pytest, for local use
ANKI.md                 Anki sync setup and daily-use guide
.env                    your API keys (copy from .env.example)
```
