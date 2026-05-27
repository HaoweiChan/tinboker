# DevOps & infrastructure domain

Tool-neutral reference for any agent working on VPS, Docker, Caddy, Cloudflare, CI/CD workflows, Redis, monitoring (Netdata), env routing, or PWA service-worker infrastructure. For code style, defer to [`backend/AGENTS.md`](../../backend/AGENTS.md) and [`frontend/AGENTS.md`](../../frontend/AGENTS.md).

## Scope

Everything outside the application code: hosting, networking, containers, CI/CD pipelines, secrets, monitoring, caching, and deployment automation. Source of truth for the production architecture is [`infra-runbook.md`](../infra-runbook.md) — this doc surfaces the parts agents most need.

## Key files

| Concern | File |
|---|---|
| CI/CD workflows | [`.github/workflows/backend-ci.yml`](../../.github/workflows/backend-ci.yml), [`.github/workflows/backend-deploy.yml`](../../.github/workflows/backend-deploy.yml), [`.github/workflows/backend-deploy-admin.yml`](../../.github/workflows/backend-deploy-admin.yml), [`.github/workflows/backend-health-check.yml`](../../.github/workflows/backend-health-check.yml), [`.github/workflows/frontend-ci.yml`](../../.github/workflows/frontend-ci.yml), [`.github/workflows/frontend-deploy.yml`](../../.github/workflows/frontend-deploy.yml) |
| Docker images | [`backend/Dockerfile`](../../backend/Dockerfile) |
| Docker compose (single env) | [`backend/docker-compose.yml`](../../backend/docker-compose.yml), [`backend/docker-compose.dev.yml`](../../backend/docker-compose.dev.yml), [`backend/docker-compose.staging.yml`](../../backend/docker-compose.staging.yml), [`backend/docker-compose.prod.yml`](../../backend/docker-compose.prod.yml) |
| Docker compose (multi-env on VPS) | [`backend/docker-compose.multi.yml`](../../backend/docker-compose.multi.yml) |
| Backend config + secrets loader | [`backend/src/config.py`](../../backend/src/config.py), [`backend/src/config_loader.py`](../../backend/src/config_loader.py) |
| Full deploy runbook | [`infra-runbook.md`](../infra-runbook.md) |
| Caddy / firewall / DNS | Documented in [`infra-runbook.md`](../infra-runbook.md) Part 1 |

## Architecture (snapshot)

```
Users → Cloudflare Edge (cache + DDoS) → Netcup VPS (152.53.136.182)
                                              ↓
                                         Caddy (reverse proxy + auto-HTTPS)
                                              ↓
                              ┌───────────────┼───────────────┐
                           :8000           :8001           :8002
                          backend-        backend-        backend-
                           prod            dev            staging
                              └───────────────┼───────────────┘
                                         Redis :6379
                                              ↓
                                   Firestore (graphfolio-db)
                                   GCS (graphfolio-articles)
                                   PostgreSQL (podcast_db, read-only)
                                   GCP Secret Manager
```

- Frontend served by **Cloudflare Pages** project `tinboker-platform` at `tinboker.com` and `dev.tinboker.com`.
- Backend runs as **3 Docker containers** on the same VPS, one per environment, behind Caddy:
  - `tinboker-backend-prod` :8000 → `api.tinboker.com`
  - `tinboker-backend-dev` :8001 → `dev-api.tinboker.com`
  - `tinboker-backend-staging` :8002 → `staging-api.tinboker.com`
- **Shared services** (NOT duplicated): one `tinboker-redis` and one `netdata` container; all three backend services connect to the same Redis.

## Conventions

### Deployment

- **NEVER deploy via SSH/rsync.** All changes go Git → PR → CI/CD. See [`CLAUDE.md`](../../CLAUDE.md) "Deployment Rules" and [`../workflows/deploy-flow.md`](../workflows/deploy-flow.md).
- **Branch routing:** `develop` → dev; `main` → staging; `v*` tag on `main` → prod.
- **Health check after every deploy.** The deploy step calls `/health` and fails if it doesn't return 200 within ~15-60s. The cron-scheduled `backend-health-check.yml` re-checks every 10 min and can auto-restart individual unhealthy services.
- **Single-environment restart.** `docker compose -f docker-compose.multi.yml restart backend-prod` restarts only prod — dev/staging keep running.
- **Single-environment image update.** Setting `PROD_IMAGE_TAG` (or `DEV_`/`STAGING_`) and running `pull`+`up -d --no-deps backend-prod` only affects that service.

### Caching layers

1. **Cloudflare edge** — `GET /api/*` responses with `Cache-Control: public, s-maxage=3600` cache at 300+ POPs.
2. **Redis origin cache** — backend checks Redis before hitting the DB. Pattern: `cache_get` → compute → `cache_set` (see [`backend/AGENTS.md`](../../backend/AGENTS.md#caching-pattern)).
3. **Cache invalidation** purges BOTH Redis and Cloudflare via the Cloudflare API token.

### Episode-endpoint cache headers (specific values)

- `GET /api/podcast/{name}/episodes/{id}` → `Cache-Control: public, max-age=3600, s-maxage=3600` (1 hour).
- `GET /api/episodes/recent` → `Cache-Control: public, max-age=300` (5 min).

### Secrets

- Loaded at startup by `config_loader.py` from **GCP Secret Manager**, namespace: uppercased Python setting name.
- See [`infra-runbook.md`](../infra-runbook.md) Part 2.2 for the full list (`POSTGRES_PASSWORD`, `JWT_SECRET_KEY`, `ADMIN_PASSWORD`, `ADMIN_JWT_SECRET`, `ADMIN_EMAILS`, `FINMIND_API_KEY`, `MASSIVE_API_KEY`, `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ZONE_TAG`).
- Local dev falls back to `backend/.env` with a warning log.
- Never commit `gcp-service-account.json` or `.env*` files.

### CORS

- Origins set per-environment in `docker-compose.multi.yml`. Must include `tinboker.com`, `dev.tinboker.com`, `staging.tinboker.com`.
- **BUG-9 (medium, historical):** [`backend/src/config.py`](../../backend/src/config.py) had `trendbrief.xyz` (old domain) but not `tinboker.com`. Spot-check before infra changes. See [`../qa-report-2026-05-09.md`](../qa-report-2026-05-09.md) BUG-9.

### Monitoring

- **Netdata** runs on the VPS, accessible only via Caddy reverse proxy at `/netdata/*` (port 19999 not exposed externally).
- **Health endpoint** `/health` returns `{status, database, redis: {status, hit_count, miss_count}, environment}`. Used by Docker healthcheck, GitHub Actions, and the admin dashboard.
- **Restart count** — `docker inspect --format '{{.RestartCount}}' <container>` should stay ≤ 3.

### PWA service worker

- Registered only in production builds (NOT in `import.meta.env.DEV`).
- Static assets: cache-first.
- API responses: network-first with cache fallback for offline.
- Update flow: when a new SW is waiting, show a non-intrusive UI; require user click to activate.

## Common pitfalls

- **BUG-4 (critical, historical):** `.github/workflows/backend-ci.yml` had `continue-on-error: true` on the test job + `pytest ... || echo "::warning::"` — broken code merged silently. Per [`CLAUDE.md`](../../CLAUDE.md) "Do Not" rules, never add either pattern back. Grep before merging CI changes: `grep -n "continue-on-error\||| echo" .github/workflows/backend-ci.yml` should return nothing.
- **BUG-9 (medium, historical):** CORS origins drift. When changing domains, audit `backend/src/config.py` AND `docker-compose.multi.yml` env vars.
- **BUG-11 (medium):** `/health` leaked Redis `connection_string`. In staging/prod, the response must omit it. Spot-check after infra changes.
- **INFRA-1:** Deploy uses `git reset --hard` + `git clean -fd` on the VPS. The `gcp-service-account.json` (not in git) is restored immediately after — if that restore step fails, the deploy bricks. Don't change the order.
- **INFRA-2:** VPS IP `152.53.136.182` is in plaintext in docs and also a CI secret. Don't echo it in new doc surfaces beyond what already exists.
- **INFRA-3:** No automated rollback on health-check failure. Record the previous image tag manually before each prod deploy (see deploy-flow workflow).
- **`@app.on_event("startup")` is deprecated.** Use the `lifespan` context manager pattern (see [`CLAUDE.md`](../../CLAUDE.md) "Do Not"). The init lives in [`backend/src/main.py`](../../backend/src/main.py).
- **SQLite has no volume mount** in `docker-compose.multi.yml`. Container rebuild = data loss. This is intentional for dev/staging (auto-init via `init_db()`); prod uses Postgres for persistence.

## External integrations

- **Netcup VPS** — 152.53.136.182, Debian 13, Germany. Root SSH (`root@152.53.136.182`).
- **Cloudflare** — DNS, edge cache, Pages, DDoS. SSL mode: Full (Caddy provides origin cert).
- **Caddy** — reverse proxy + auto-HTTPS. Config at `/etc/caddy/Caddyfile`.
- **Docker + Docker Compose** — multi-env stack via `docker-compose.multi.yml`.
- **GitHub Container Registry (GHCR)** — backend images at `ghcr.io/<owner>/tinboker-backend:<tag>`.
- **GCP Secret Manager** — runtime secrets.
- **Netdata** — VPS + container metrics.

## Cross-references

- Full deploy runbook: [`infra-runbook.md`](../infra-runbook.md)
- Branch → env → tag workflow: [`../workflows/deploy-flow.md`](../workflows/deploy-flow.md)
- Health check + bug repro flow: [`../workflows/qa-flow.md`](../workflows/qa-flow.md)
- Project-wide rules (deploy don'ts, allowed read-only server commands): [`CLAUDE.md`](../../CLAUDE.md)
- Bugs: BUG-4, BUG-9, BUG-11, INFRA-1..4 in [`../qa-report-2026-05-09.md`](../qa-report-2026-05-09.md)
