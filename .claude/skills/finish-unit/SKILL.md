---
name: finish-unit
description: Close out one MbxRead roadmap unit - local gate (pytest, web build, web lint), docs, one commit, branch + PR titled "<summary> (unit N)", watch CI to green, and after the user merges, sync main and confirm the main run and the GHCR image. Use at the end of every unit, or when the user says the unit is done / "open the PR" / "it's merged".
---

# finish-unit

Rule 4 of `CLAUDE.md`, plus the CI that unit 3 added. The user merges; never merge yourself.

## 1. Local gate (all three, every time)

```bash
cd /c/Personal/MbxRead-public
.venv/Scripts/python.exe -m pytest server/tests -q
cd web && npm run build && npm run lint
```

`tsc` alone once missed a real react-hooks bug, so lint is not optional. If the unit touched the Dockerfile or compose, also build and smoke-test the container. Ports 8002 (app) and 5433 (db) belong to the live compose stack, so run a throwaway app + Postgres on a private network, app on 8012 (`compose run` would also start a second `db` on 5433 and collide):

```bash
PG=$(grep -o 'postgres:[^ ]*' compose.yaml)
docker compose build -q mbxread && docker network create mbxtest
docker run -d --rm --name mbxtest-db --network mbxtest -e POSTGRES_USER=mbxread -e POSTGRES_PASSWORD=mbxread $PG
sleep 6 && docker run -d --rm --name mbxtest --network mbxtest -p 8012:8002 -e TZ=Asia/Seoul \
  -e DATABASE_URL=postgresql://mbxread:mbxread@mbxtest-db:5432/mbxread mbxread
sleep 12; curl -s 127.0.0.1:8012/api/health; curl -s -o /dev/null -w "%{http_code}\n" 127.0.0.1:8012/
docker logs mbxtest 2>&1 | grep -c Traceback
docker rm -f mbxtest mbxtest-db && docker network rm mbxtest
```

Post Korean text from a Python script (`urllib`, `\u` escapes), not curl: Git Bash mangles Hangul on the command line.

## 2. Docs, in the same commit

- `docs/STATUS.md`: mark the unit done, the next one **next**, prune the finished unit's notes, update test count, ops facts and follow-ups. Rewrite in place.
- `docs/DECISIONS.md`: append `## <date> — Unit N: <title>` with decisions, what was verified and what was not. Never edit old entries.
- `docs/ARCHITECTURE.md` / `docs/SPEC.md`: amend whatever the unit changed. `README.md` / `ANKI.md` if user-facing.

## 3. Branch, commit, PR

Work on `unit-N-<slug>` (create it at the start of the unit). One commit, body listing the changes, ending with the attribution line from the system reminder.

```bash
git push -u origin unit-N-<slug>
gh pr create --base main --title "<summary> (unit N)" --body "..."   # What / Verified / Not verified, then the Claude Code line
gh pr checks <n> --watch --interval 20
```

Required checks on `main`: `test`, `web`, `image` (admins included, no direct pushes). Red check: read `gh run view <id> --log-failed`, fix on the branch, push again.

## 4. After the user says it's merged

```bash
git checkout main && git pull && git branch -d unit-N-<slug> && git fetch -p
gh run list --branch main --limit 1     # then: gh run watch <id> --exit-status
docker manifest inspect ghcr.io/miobix/mbxread:latest >/dev/null && echo public
```

The `image` job takes ~3-4 min on main (build + push of a ~600 MB image); say so if the user asks why it's slow.

## Gotchas

- Git Bash rewrites a leading `/` into `C:/Program Files/Git/`: write `gh api users/...`, not `gh api /users/...`.
- `gh` is logged in as the user (miobix); everything it does shows as them. The default token lacks `read:packages`, so check image visibility with `docker manifest inspect`, not the packages API.
- Doc-only fixes between units: commit locally on `main`, unpushed, and carry them into the next unit's branch (`main` is protected).
