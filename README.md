# MbxRead

A Korean reading app: read real texts, tap unknown words, translate them, build structured
flashcards saved by **dictionary form** (so every inflection highlights), and sync them to
Anki. FastAPI + Postgres + kiwipiepy backend, Next.js frontend, local language models, all
in Docker compose.

- **What it does and how it works:** [docs/FEATURES.md](docs/FEATURES.md) (screenshots,
  diagrams, design notes)
- **Try it without installing:** [live demo](https://miobix.github.io/MbxRead-public/)
  (static, sample texts)

## Quick start

Needs Docker (Docker Desktop on Windows/Mac) and git.

```
git clone https://github.com/miobix/MbxRead-public.git
cd MbxRead-public
cp .env.example .env      # fill in the keys you have (see Configuration)
docker compose up -d --build
```

Open `http://localhost:8002`. Check health at `/api/health`; logs with
`docker compose logs -f mbxread`. After pulling changes, run `docker compose up -d --build`
again. Every service has `restart: unless-stopped`, so the app comes back whenever Docker
starts.

## Configuration (`.env`)

| Variable | Needed for | |
|---|---|---|
| `DEEPL_API_KEY` | Translate | Free at https://www.deepl.com/pro-api (500k chars/month) |
| `KRDICT_API_KEY` | Dictionary, examples | Free at https://krdict.korean.go.kr/openApi/openApiInfo |
| `TZ` | Stats | Your IANA time zone (e.g. `Asia/Seoul`): which day a read counts for |
| `POSTGRES_PASSWORD` | optional | Default `mbxread`; the db listens on `127.0.0.1` only |
| `ALLOWED_HOSTS` | Phone access | Extra host names the app answers to, comma-separated |
| `BACKUP_DIR` | optional | Where nightly dumps go (default `./backups`) |

Without keys the app still runs: Translate says the DeepL key is missing, and Dictionary
comes back empty. Restart after editing: `docker compose up -d`.

## Optional parts

- **Anki sync:** Anki desktop with the AnkiConnect add-on (code `2055492159`), open on the
  same computer. Compose reaches it at `host.docker.internal:8765`. On Linux, set
  AnkiConnect's `webBindAddress` to `0.0.0.0` (its default refuses containers). Full
  guide: [ANKI.md](ANKI.md).
- **Similar usage** (find a word's other uses by sense, and a local LLM's explanation):
  compose starts `embed` (downloads ~2 GB of bge-m3 weights on first start) and `ollama`.
  Pull the LLM once: `docker compose exec ollama ollama pull gemma4:e4b`. Library texts are
  indexed in the background. Without these the rest of the app works normally.
- **Phone access:** the app has no login, so it is published on `127.0.0.1` only. Use
  Tailscale to reach it from your own devices: install it on the computer and the phone
  (same account), run `tailscale serve --bg --http=8002 localhost:8002` once on the
  computer, add the computer's Tailscale names to `.env`
  (`ALLOWED_HOSTS=<computer-name>,<computer-name>.<tailnet>.ts.net`) and restart, then
  open `http://<computer-name>:8002` on the phone. Never use `tailscale funnel`: that
  makes it public.
- **Host and Origin checks:** the app answers only to `127.0.0.1`, `localhost` and
  `ALLOWED_HOSTS`, and refuses writes (POST/PUT/PATCH/DELETE) sent from any other site's
  page. A request with no `Origin` header (curl, scripts) still works.

## Backups and moving machines

The `backup` service writes `mbxread-<date>.dump` (`pg_dump -Fc`) daily into `BACKUP_DIR`
and keeps the newest 14 (`docker compose logs backup` shows each run).

To restore on a new machine: clone, copy `.env`, then

```
docker compose up -d --wait db
docker compose cp mbxread-2026-11-17.dump db:/tmp/restore.dump
docker compose exec db pg_restore -U mbxread -d mbxread --clean --if-exists /tmp/restore.dump
docker compose up -d --build
```

and pull the LLM again (see Optional parts).

## Development

```
python -m venv .venv
.venv/bin/pip install -r requirements-dev.txt     # Windows: .venv\Scripts\pip
docker compose up -d db                            # tests and dev runs use it (127.0.0.1:5433)
.venv/bin/python -m pytest server/tests -q         # offline: every external service is mocked
cd web && npm ci && npm run lint && npm run build
```

- Tests create a throwaway database per test, so they never touch your data.
- Dev server: stop the compose app (`docker compose stop mbxread`), then
  `uvicorn server.main:app --port 8002` from the repo root; it serves `web/out`. On
  Windows, `start.ps1` does that, rebuilding `web/` first if it's stale.
- `requirements.txt` is what the image installs; test-only deps go in
  `requirements-dev.txt`.
- Contributor docs live in `docs/`: start with `docs/STATUS.md`; `docs/README.md`
  explains what each doc is for.

## Terraform

`infra/` describes a second, disposable copy of the stack with Terraform and the Docker
provider (containers `mbxread-tf-*`, app on `http://127.0.0.1:18002`, empty database). It
never touches the compose stack.

```
cd infra
terraform init
terraform apply      # -var enable_models=true adds embed + ollama (downloads model weights)
terraform destroy
```

CI runs the same apply, health check and destroy on every pull request.

## Layout

```
server/          FastAPI app: API routes, Postgres schema, tokenizer, usage search
web/             Next.js frontend, built to web/out and served by the app
translate_svc/   DeepL, krdict and their caches, used as a library
import_tools/    YouTube subtitles and PDF text extraction (also usable as CLIs)
scripts/         one-off and eval scripts (demo data, usage eval, SQLite migration)
infra/           Terraform: the disposable stack, also run in CI
docs/            features, architecture, spec, decision log, status
compose.yaml     app + Postgres + embed + ollama + backup
Dockerfile       the app image (API + web); .dockerignore is an allowlist
```

## License

MIT, see [LICENSE](LICENSE). The Korean Wikipedia excerpt in the demo is CC BY-SA, credited
in the demo itself.
