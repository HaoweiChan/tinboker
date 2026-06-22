# Deploy flow

Step-by-step procedure for shipping changes to dev, staging, and production. For full infrastructure context (architecture, secrets, Caddy config, cold-start), see [`infra-runbook.md`](../infra-runbook.md).

## Cardinal rule

**NEVER deploy directly to the VPS via SSH/rsync.** All changes go Git → PR → CI/CD. The VPS pulls code via `git reset --hard origin/<branch>` inside the deploy workflow; manual edits will be wiped on the next deploy.

## Branch → environment routing

| Trigger | Deploys to | Frontend URL | Backend URL |
|---|---|---|---|
| Merge to `develop` | Dev | `dev.tinboker.com` | `dev-api.tinboker.com` (:8001) |
| Merge to `main` | Staging | `staging.tinboker.com` | `staging-api.tinboker.com` (:8002) |
| `v*` tag on `main` | Production | `tinboker.com` | `api.tinboker.com` (:8000) |

Branch conventions:
- Features: `feat/<name>` from `develop`
- Bug fixes: `fix/<name>` from `develop`
- Hotfixes: `hotfix/<name>` from `main`
- **No `staging` branch** — staging is whatever is currently at the HEAD of `main`.

## Standard release pipeline (feature → prod)

1. Branch from `develop`: `git checkout -b feat/<name>`.
2. Open a PR → `develop`. CI builds an image (PR comment includes the GHCR tag) and a Cloudflare Pages preview URL.
3. Merge PR → `develop` → auto-deploys to `dev.tinboker.com` + `dev-api.tinboker.com`.
4. Verify on dev (see [Verification](#verification) below).
5. When dev is stable, open `develop → main`.
6. Merge to `main` → auto-deploys to staging.
7. Verify on staging.
8. Cut release: `git tag v1.x.0 && git push --tags`.
9. Tag push → auto-deploys to `tinboker.com` + `api.tinboker.com`.

## Hotfix pipeline

1. Branch from `main`: `git checkout -b hotfix/<name>`.
2. PR → `main`. Verify on staging.
3. Merge → staging deploys.
4. Tag and push → prod deploys.
5. Cherry-pick or merge `main` → `develop` so dev doesn't regress.

## CI/CD workflows that fire

| Workflow file | Trigger |
|---|---|
| [`.github/workflows/backend-ci.yml`](../../.github/workflows/backend-ci.yml) | PR to `develop` / `main` — pytest + ruff; must block on failure (BUG-4 history) |
| [`.github/workflows/frontend-ci.yml`](../../.github/workflows/frontend-ci.yml) | PR to `develop` / `main` — TypeScript build + ESLint |
| [`.github/workflows/backend-deploy.yml`](../../.github/workflows/backend-deploy.yml) | Push to `develop` / `main` / tag — builds + pushes to GHCR, SSHs to VPS, runs `docker compose ... up -d --no-deps backend-<env>` |
| [`.github/workflows/backend-deploy-admin.yml`](../../.github/workflows/backend-deploy-admin.yml) | Manual dispatch — admin/dev portal backend |
| [`.github/workflows/frontend-deploy.yml`](../../.github/workflows/frontend-deploy.yml) | Push to `develop` / `main` — deploys to Cloudflare Pages project `tinboker` |
| [`.github/workflows/backend-health-check.yml`](../../.github/workflows/backend-health-check.yml) | Cron every 10 min — hits `/health` per env; restarts the failing container only |

## Verification

After every deploy, in order:

1. **Health endpoint reaches `healthy` within 60s:**
   ```bash
   for i in $(seq 1 12); do
     STATUS=$(curl -s {API}/health | python3 -c "import sys,json; print(json.load(sys.stdin).get('status',''))" 2>/dev/null)
     echo "Attempt $i: $STATUS"
     [ "$STATUS" = "healthy" ] && break
     sleep 5
   done
   ```
2. **Container did not restart:** `ssh root@152.53.136.182 "docker inspect --format='{{.RestartCount}}' tinboker-backend-<env>"` is the same number as before the deploy (or 0).
3. **Image tag was applied:** the GHCR image for the merged commit is listed and the container is using it (`docker inspect --format='{{.Config.Image}}' ...`).
4. **Pre-prod additional check:** run the smoke suite from [`qa-flow.md`](./qa-flow.md) against the staging URL.
5. **Post-prod:** repeat steps 1–3 against `api.tinboker.com`, plus a manual sanity click on `tinboker.com` (landing, stock page, search).

## Allowed read-only VPS commands

These are safe to suggest/run for diagnostics — they DO NOT modify state:

```bash
curl https://api.tinboker.com/health                              # health check
ssh root@152.53.136.182 "docker ps"                               # container status
ssh root@152.53.136.182 "docker logs tinboker-backend-prod --tail=50"
ssh root@152.53.136.182 "docker inspect --format='{{.RestartCount}}' tinboker-backend-prod"
ssh root@152.53.136.182 "docker inspect --format='{{.Config.Image}}' tinboker-backend-prod"
```

Anything that writes (restart, pull, rebuild, file edit) goes through CI/CD or — in a true incident — through the manual redeploy block in [`infra-runbook.md`](../infra-runbook.md) "Useful commands" with the user's explicit approval.

## Rollback

There is no automated rollback. Before each prod deploy:

1. Note the previous image tag: `ssh root@152.53.136.182 "docker inspect tinboker-backend-prod --format='{{.Config.Image}}'"`.
2. If the new deploy is bad, manually roll back on the VPS:
   ```bash
   cd /app/backend
   PROD_IMAGE_TAG=<previous-tag> docker compose -f docker-compose.multi.yml pull backend-prod
   PROD_IMAGE_TAG=<previous-tag> docker compose -f docker-compose.multi.yml up -d --no-deps backend-prod
   ```

## Pre-merge-to-main checklist

Before opening or merging a `develop → main` PR:

- [ ] `pytest tests/ -v` passes locally (or in CI, with `continue-on-error` NOT set)
- [ ] `npm run build` passes locally
- [ ] `ruff check src/` clean
- [ ] `npm run lint` clean
- [ ] No new `continue-on-error: true` anywhere in `.github/workflows/`
- [ ] No new `time.sleep()` in async code (per [`CLAUDE.md`](../../CLAUDE.md) "Do Not")
- [ ] No new `@app.on_event("startup")` — use the lifespan pattern
- [ ] Search/heatmap/Zod regressions checked (BUG-1, BUG-2, BUG-5 in [`../issues.md`](../issues.md))
- [ ] CORS still includes `tinboker.com`, `dev.tinboker.com`, `staging.tinboker.com` (BUG-9 history)

## Cross-references

- Full deploy runbook: [`infra-runbook.md`](../infra-runbook.md)
- DevOps reference: [`../agents/devops-infra.md`](../agents/devops-infra.md)
- Verification suite: [`./qa-flow.md`](./qa-flow.md)
- Allowed server commands and "Do Not" list: [`CLAUDE.md`](../../CLAUDE.md)
