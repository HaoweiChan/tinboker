# Infrastructure runbook

Operational reference for the TinBoker production infrastructure: VPS, Caddy, GCP, Cloudflare, Docker, databases, and env vars. This is the source of truth that [`agents/devops-infra.md`](./agents/devops-infra.md) and [`workflows/deploy-flow.md`](./workflows/deploy-flow.md) defer to.

> **History note:** the one-time monorepo migration parts of the original `MIGRATION.md` (create the repo, edit workflow files for the monorepo layout, re-point `/app` on the VPS to the new repo, post-migration verification checklist) have been removed — they describe work that's already done. If you need that history, see git commit `cc5355d` for the pre-trim version.

---

## Architecture

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

**Frontend:** Cloudflare Pages → `tinboker.com`, `dev.tinboker.com` (preview)
**Backend:** Docker containers on VPS → `api.tinboker.com` (prod), `dev-api.tinboker.com`, `staging-api.tinboker.com`

---

## Part 1 — One-time infrastructure (skip if already done)

### 1.1 VPS access

```
Host:  152.53.136.182   (Netcup RS 1000 G11, Debian 13, Germany)
User:  root
```

SSH in: `ssh root@152.53.136.182`

If setting up a fresh VPS, run this first:

```bash
# Firewall
apt install -y ufw fail2ban
ufw allow ssh
ufw allow http
ufw allow https
ufw enable

# Docker
curl -fsSL https://get.docker.com | sh

# Caddy
apt install -y debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudflare.com/public-key/caddy-stable.gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudflare.com/public-key/caddy-stable.list' | tee /etc/apt/sources.list.d/caddy-stable.list
apt update && apt install -y caddy
```

### 1.2 Caddy configuration

Write `/etc/caddy/Caddyfile`:

```
api.tinboker.com {
    encode gzip
    reverse_proxy localhost:8000
}

dev-api.tinboker.com {
    encode gzip
    reverse_proxy localhost:8001
}

staging-api.tinboker.com {
    encode gzip
    reverse_proxy localhost:8002
}

dev.tinboker.com {
    encode gzip
    handle /api/* {
        reverse_proxy localhost:8001
    }
    handle {
        root * /var/www/html-dev
        try_files {path} /index.html
        file_server
    }
}
```

Then reload: `systemctl reload caddy`

Caddy issues Let's Encrypt certs automatically — no cert setup required.

### 1.3 Cloudflare DNS records

In Cloudflare dashboard → DNS for `tinboker.com`:

| Type | Name | Content | Proxy |
|---|---|---|---|
| A | `api` | `152.53.136.182` | Proxied (orange) |
| A | `dev-api` | `152.53.136.182` | Proxied |
| A | `staging-api` | `152.53.136.182` | Proxied |
| A | `dev` | `152.53.136.182` | Proxied |
| CNAME | `@` (root) | `tinboker-platform.pages.dev` | Proxied |
| CNAME | `www` | `tinboker-platform.pages.dev` | Proxied |

SSL/TLS mode: **Full** (not Full Strict — Caddy uses Let's Encrypt, not Cloudflare origin cert)

### 1.4 Cloudflare cache rule

Dashboard → `tinboker.com` → Rules → Cache Rules → Create rule:

```
Name: Cache API GET responses
When: (starts_with(http.request.uri.path, "/api/") and http.request.method eq "GET")
Cache eligibility: Eligible for cache
Edge TTL: Use cache-control header
Browser TTL: Respect origin   # SET to respect_origin 2026-06-09 (was Override/86400) — do NOT revert; see caveat
```

**Caveat — dynamic endpoints must not be over-cached.** This rule makes *every* `GET /api/*`
edge-cacheable. Endpoints that send no `Cache-Control` header then inherit a long edge
default. `GET /api/search/suggest` (autocomplete) was observed serving `cf-cache-status: HIT`
with `cache-control: max-age=86400` (24h) — stale prices, missing new stocks. Two required
guards:

1. **Origin must declare intent.** Query-driven endpoints set a short header themselves
   (`/api/search` and `/api/search/suggest` → `public, s-maxage=60` via the `@cdn_cached`
   decorator in [`backend/src/routers/search.py`](../backend/src/routers/search.py)). With
   *Edge TTL: Use cache-control header*, the edge then honours the 60s — not the long default.
2. **Browser TTL must be "Respect origin", not "Override".** A *Browser TTL: Override* value
   rewrites the `max-age` sent to browsers regardless of origin — the source of the observed
   `max-age=86400` (which had drifted from the "1 hour" this doc previously listed). It surfaced
   as stale UI: 2330's ticker-insight cards stuck on the zh-TW "尚未完成繁中轉寫" fallback because
   browsers held a 24h-cached pre-translation response. **Resolved 2026-06-09** — Browser TTL was
   set `override_origin → respect_origin` via the Cloudflare Rulesets API (ruleset `3a79f70b…`,
   rule `c87f100f…` "Cache API GET requests"); the live `/api/*` header is now
   `public, s-maxage=3600, max-age=3600, stale-while-revalidate=7200` (origin's TRENDING profile
   passes through). Code cannot change this — it is a Cache-Rule setting requiring a token with
   `Cache Rules: Edit` + `Account Rulesets: Edit`. If you ever need a browser override for other
   `/api/*` routes, add a higher-priority rule that **bypasses cache** (or respects origin) for
   `starts_with(http.request.uri.path, "/api/search/")`.

**Post-deploy purge.** Backend deploys ([`backend-deploy.yml`](../.github/workflows/backend-deploy.yml),
[`backend-deploy-admin.yml`](../.github/workflows/backend-deploy-admin.yml)) purge the deployed
env's `/api/` edge cache once the container is healthy, so a deploy no longer serves pre-deploy
`/api/*` responses until TTL. Uses `CLOUDFLARE_API_TOKEN` + `CLOUDFLARE_ZONE_TAG` from GSM
(host-scoped purge of `{api_host}` — same method as the manual recipe in
[`CLAUDE.md`](../CLAUDE.md) — falling back to `purge_everything` on non-Enterprise plans).
Best-effort: a purge failure warns but does not fail the deploy.

### 1.5 Docker shared network

The backend containers join a shared network with the external PostgreSQL container:

```bash
ssh root@152.53.136.182
docker network create app_default 2>/dev/null || true
```

---

## Part 2 — GCP setup

### 2.1 Service account

The backend authenticates to GCP using a service account JSON key mounted into the
Docker container at `/app/gcp-service-account.json`.

- **GCP project:** `gen-lang-client-0901363254`
- **Key file on VPS:** `/app/backend/gcp-service-account.json` (not committed to git)

To get a new key if lost:
1. GCP Console → IAM & Admin → Service Accounts
2. Find the service account used by the backend
3. Keys tab → Add Key → JSON → download
4. Upload to VPS: `scp service-account-key.json root@152.53.136.182:/app/backend/gcp-service-account.json`

### 2.2 GCP Secret Manager — full secrets list

The backend fetches these secrets from Secret Manager **at runtime** (loaded by
`GCPSecretManagerSource` in `src/config_loader.py`). Secret name = uppercase of the
Python settings field name.

| Secret name in GSM | What it is | Required? |
|---|---|---|
| `POSTGRES_PASSWORD` | Password for Cloud SQL (podcast_db) | Yes (prod) |
| `JWT_SECRET_KEY` | Signing key for user auth tokens | Yes |
| `ADMIN_PASSWORD` | Password for admin UI login | Yes |
| `ADMIN_JWT_SECRET` | Signing key for admin tokens | Yes |
| `ADMIN_EMAILS` | Comma-separated admin email addresses | Yes |
| `FINMIND_API_KEY` | FinMind Taiwan stock data API | Yes |
| `MASSIVE_API_KEY` | Massive API (US market data) | Yes |
| `CLOUDFLARE_API_TOKEN` | Cloudflare API token (cache purge) | Optional |
| `CLOUDFLARE_ZONE_TAG` | Cloudflare zone ID for tinboker.com | Optional |

**Setting a secret:**

```bash
# Create new
echo -n "your-secret-value" | gcloud secrets create SECRET_NAME \
  --data-file=- --project=gen-lang-client-0901363254

# Update existing
echo -n "your-secret-value" | gcloud secrets versions add SECRET_NAME \
  --data-file=- --project=gen-lang-client-0901363254
```

### 2.3 GCP secrets used by GitHub Actions CI (stored in Secret Manager, not as GH secrets)

These are fetched by the workflow via `gcloud secrets versions access`:

| Secret name in GSM | Used for |
|---|---|
| `VPS_HOST` | SSH target (`152.53.136.182`) |
| `VPS_USER` | SSH user (`root`) |
| `VPS_SSH_KEY` | SSH private key for deploy |
| `GHCR_TOKEN` | GitHub Container Registry login token |
| `GOOGLE_CLIENT_ID` | Injected as `VITE_GOOGLE_CLIENT_ID` at frontend build time |

### 2.4 GitHub Actions secrets (stored directly in repo settings)

Settings → Secrets and variables → Actions → New repository secret:

| Secret | Where to get it |
|---|---|
| `GCP_SA_KEY` | GCP Console → IAM → Service Accounts → your SA → Keys → Add Key → JSON. Paste the entire JSON content. |
| `CLOUDFLARE_API_TOKEN` | Cloudflare → My Profile → API Tokens → Create Token → "Edit Cloudflare Workers" template, scoped to tinboker.com |
| `CLOUDFLARE_ACCOUNT_ID` | Cloudflare dashboard → right sidebar when on tinboker.com overview |

> `VPS_HOST`, `VPS_USER`, `VPS_SSH_KEY`, `GHCR_TOKEN` are **not** stored as GitHub secrets —
> they are fetched from GCP Secret Manager at workflow runtime using `GCP_SA_KEY`.

---

## Part 3 — Cloudflare Pages

### 3.1 Rename project (zero downtime, if migrating from a different project name)

1. Cloudflare → Workers & Pages → existing project
2. Settings → General → Project name → rename to `tinboker`
3. Your `pages.dev` preview subdomain changes to `tinboker-platform.pages.dev`
4. Update the CNAME root record in DNS (Part 1.3) to `tinboker-platform.pages.dev`
5. The custom domain `tinboker.com` stays connected automatically

### 3.2 Connect a fresh repo to Cloudflare Pages

If creating fresh:
1. Workers & Pages → Create application → Pages → Connect to Git
2. Select `tinboker` repo
3. Build settings:
   - **Framework preset:** Vite
   - **Build command:** `npm ci && npm run build`
   - **Build output directory:** `dist`
   - **Root directory:** `frontend`
4. Environment variables → add: `VITE_GOOGLE_CLIENT_ID` = (from GCP Secret Manager `GOOGLE_CLIENT_ID`)

---

## Part 4 — Cold start (first time ever deploying on a fresh VPS)

If this is a brand new server with no running containers:

```bash
ssh root@152.53.136.182

# 1. Clone repo
git clone git@github.com:YOUR_USERNAME/tinboker.git /app
cd /app/backend

# 2. Place GCP service account key
scp local-machine:/path/to/gcp-service-account.json /app/backend/gcp-service-account.json

# 3. Create shared Docker network
docker network create app_default

# 4. Log in to GHCR
echo "YOUR_GHCR_TOKEN" | docker login ghcr.io -u YOUR_USERNAME --password-stdin

# 5. Pull all images
docker compose -f docker-compose.multi.yml pull

# 6. Start everything
docker compose -f docker-compose.multi.yml up -d

# 7. Wait and verify
sleep 30
curl http://localhost:8000/health
curl http://localhost:8001/health
curl http://localhost:8002/health

# 8. Register systemd services
bash deploy/setup-systemd.sh
```

---

## Part 5 — Database

### SQLite (default for dev/staging)

Auto-created at startup. No manual steps required. The app calls `init_db()` via the
FastAPI lifespan event in `src/main.py`. Tables are created with `CREATE TABLE IF NOT
EXISTS`, so re-running is safe.

Default path: `/app/backend/data/graphfolio.db` (inside the container).

> **Important:** `docker-compose.multi.yml` does not mount a volume for SQLite. Data is
> lost on container rebuild. For persistence, add a volume mount:
> ```yaml
> volumes:
>   - ./data:/app/data
> ```

### PostgreSQL — `podcast_db` (recommendations, read-only from backend)

The backend reads recommendation data from an external PostgreSQL instance managed by
a separate Docker Compose stack (`docker-db`). The backend connects using:

```
Host:     docker-db_postgres-1   (Docker internal DNS)
Port:     5432
DB:       podcast_db
User:     podcast_user
Password: stored in GCP Secret Manager as POSTGRES_PASSWORD
```

This database is managed by the podcast pipeline, not by this repo. The backend is
read-only. No migrations to run here.

### Firestore — `graphfolio-db`

Main application data (episodes, podcast metadata, user data). Managed by GCP — no
setup needed. The backend accesses it via the service account JSON key.

Database ID: `graphfolio-db` (set as `FIRESTORE_DATABASE_ID` env var in `docker-compose.multi.yml`).

---

## Part 6 — Environment variables reference

Variables set in `docker-compose.multi.yml` are passed directly to containers. Secrets
not listed here are loaded from GCP Secret Manager at runtime by `src/config_loader.py`.

| Variable | Value | Notes |
|---|---|---|
| `ENVIRONMENT` | `production` / `development` / `staging` | Controls DB enforcement, logging |
| `USE_POSTGRES` | `true` | Forces PostgreSQL; production auto-enables this |
| `REDIS_URL` | `redis://redis:6379/0` | Docker internal network |
| `GCP_PROJECT_ID` | `gen-lang-client-0901363254` | Enables Secret Manager |
| `GOOGLE_APPLICATION_CREDENTIALS` | `/app/gcp-service-account.json` | Mounted at runtime |
| `POSTGRES_HOST` | `docker-db_postgres-1` | External Docker network |
| `POSTGRES_DB` | `podcast_db` | Recommendation data |
| `POSTGRES_USER` | `podcast_user` | |
| `POSTGRES_PASSWORD` | loaded from GSM | |
| `FIRESTORE_DATABASE_ID` | `graphfolio-db` | Named Firestore instance |
| `CORS_ORIGINS` | `["https://tinboker.com",...]` | Set per environment in compose file |

For **local development** (not Docker), copy `backend/.env.example` to `backend/.env`
and fill in values. The app loads `.env` before falling back to Secret Manager.

---

## Useful commands

```bash
# SSH into VPS
ssh root@152.53.136.182

# View all running containers
docker ps

# Tail logs for a service
docker logs -f tinboker-backend-prod
docker logs -f tinboker-backend-dev
docker logs -f tinboker-backend-staging

# Restart a single service (no downtime for others)
cd /app/backend
docker compose -f docker-compose.multi.yml restart backend-prod

# Manual redeploy production without CI
cd /app/backend
git pull origin main
PROD_IMAGE_TAG=main docker compose -f docker-compose.multi.yml pull backend-prod
PROD_IMAGE_TAG=main docker compose -f docker-compose.multi.yml up -d --no-deps backend-prod

# Force-clear Redis cache
docker exec tinboker-redis redis-cli FLUSHALL

# Caddy logs
journalctl -u caddy -f

# Caddy reload after Caddyfile change
systemctl reload caddy
```

---

## Port reference

| Container | VPS Port | Public URL |
|---|---|---|
| backend-prod | 8000 | api.tinboker.com |
| backend-dev | 8001 | dev-api.tinboker.com |
| backend-staging | 8002 | staging-api.tinboker.com |
| Redis | 6379 (localhost only) | — |
| Netdata | 19999 (localhost only) | api.tinboker.com/netdata/ |
