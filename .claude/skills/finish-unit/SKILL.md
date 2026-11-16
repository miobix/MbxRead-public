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

`tsc` alone once missed a real react-hooks bug, so lint is not optional. If the unit touched the Dockerfile or compose, also build and smoke-test the container. Port 8002 is the live tray app, so run it on 8012 in a throwaway project:

```bash
docker compose build
docker compose -p mbxtest run -d --name mbxtest -p 8012:8002 mbxread
curl -s localhost:8012/api/health; curl -s -o /dev/null -w "%{http_code}\n" localhost:8012/
docker rm -f mbxtest && docker compose -p mbxtest down -v
```

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
