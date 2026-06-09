# CLAUDE.md — TinBoker Monorepo

This file is the root context for Claude Code agents. Sub-agents should also read the
tier-specific guides — `backend/AGENTS.md`, `frontend/AGENTS.md`, and `pipelines/AGENTS.md` —
for domain rules.

---

## Project Summary

TinBoker (聽播客) is a Taiwanese stock & podcast intelligence platform. This repo is a **monorepo**
that consolidated the former `tinboker-platform` (web UI + API) and `tinboker-agents`
(content pipelines, now under `pipelines/`) into one standalone repo.

- **Frontend** (`frontend/`): React 19 + TypeScript + Vite → Cloudflare Pages (`tinboker.com`)
- **Backend** (`backend/`): FastAPI (Python 3.12) platform API → Docker on Netcup VPS (`api.tinboker.com`)
- **Pipelines** (`pipelines/`): content/agent tier — podcast + news ingestion → transcribe,
  summarize, extract ticker sentiment, build the wiki knowledge graph. uv workspace; the podcast
  service serves `/api/wiki` + `/api/podcast` on `:8003`; news runs as a systemd timer. **Infra/content-only — no UI here.**
- **MCP servers** (`mcp-servers/`): agent tooling — `stock-translations`, `article-authoring`
- **Database:** SQLite (dev) / Cloud SQL PostgreSQL (main + prod) — incl. the pipelines wiki store
- **Cache:** Redis 7-alpine on VPS
- **Auth:** Google OAuth → JWT
- **External APIs:** Massive API (US stocks), FinMind (TW stocks), GCP Firestore (podcasts), Spotify + Tavily (pipelines)

---

## Where AI tools should look first

**Domain reference docs (tool-neutral):**
- `docs/agents/podcast-domain.md` — episodes, podcasts, comments, recommendations, news
- `docs/agents/stock-data.md` — TW/US market data, charting, WebSocket prices, translations
- `docs/agents/search-discovery.md` — search, suggestions, trending, tags
- `docs/agents/graph-visuals.md` — knowledge graph, design system, PWA visuals
- `docs/agents/auth-admin.md` — auth, user, admin dashboard, dev portal
- `docs/agents/devops-infra.md` — VPS, Docker, Caddy, CI/CD, Redis, monitoring
- `docs/agents/qa-tester.md` — full QA suite (infra/API/UI/CI/security/perf) across L/D/S/P

**Content pipelines (the `pipelines/` tier — former `tinboker-agents`):**
- `pipelines/AGENTS.md` — purpose, module map, decision tree, conventions
- `pipelines/docs/wiki-schema.md` — wiki Postgres schema + `/api/wiki` API
- `pipelines/docs/content-api-roadmap.md` — what the web UI needs from the pipelines, and the plan
- `pipelines/docs/data-consolidation-plan.md` — Firestore/GCS → VPS Postgres consolidation

**Procedural workflows:**
- `docs/workflows/deploy-flow.md` — branch → env → tag pipeline
- `docs/workflows/qa-flow.md` — reproducing known bugs, dev-bypass flow
- `docs/workflows/firestore-data-change.md` — Firestore schema / data-contract changes

**Canonical data contract (shared between `backend/` and `pipelines/`):**
- `docs/firestore-contract.md`

**Operational reference:**
- `docs/infra-runbook.md` — VPS, Caddy, GCP, Cloudflare, Docker, env vars (live ops)
- `docs/qa-report-2026-05-09.md` — dated bug catalog (BUG-1..15 + INFRA-1..4); **historical** — several entries are since fixed, verify before relying on specific claims

**Code style / conventions (unchanged):**
- `backend/AGENTS.md` — Python style, key file map
- `frontend/AGENTS.md` — UI conventions, zh-TW localization, icon system
- `pipelines/AGENTS.md` — uv workspaces, content-builder conventions, "don't build UI here"

**Tool-specific entry points (all thin wrappers → `docs/agents/` + `pipelines/AGENTS.md`):**
- Claude Code subagents: `.claude/agents/<domain>.md` (delegate by domain)
- Claude Code skills: `.claude/skills/<workflow>/SKILL.md` (invoked by intent)
- Codex CLI agents: `.codex/agents/<domain>.toml` (+ `.codex/config.toml` for MCP servers)
- Cursor rules: `.cursor/rules/<domain>.mdc` (auto-attached by file glob)
- Tool-neutral skills: `.agents/skills/<workflow>/SKILL.md`
- Codex CLI / OpenCode / Aider: read this file (`AGENTS.md` is symlinked here)

---

## Repository Layout

```
tinboker/
├── frontend/           React 19 + Vite web UI → Cloudflare Pages
├── backend/            FastAPI platform API, Docker, deploy scripts
├── pipelines/          Content & agent pipelines (podcast + news ingestion, wiki builder; uv workspace)
├── mcp-servers/        MCP servers for AI tooling (stock-translations, article-authoring)
├── docs/               Domain references, workflows, firestore-contract, runbooks
├── .claude/            Claude Code subagents + skills (thin wrappers)
├── .codex/             Codex CLI agents + MCP config
├── .cursor/rules/      Cursor rules (thin wrappers)
├── .agents/            Tool-neutral skill wrappers
└── .github/workflows/  CI/CD pipelines (backend, frontend, pipelines)
```

---

## Quick Commands

### Backend

```bash
cd backend
uv sync                         # install deps (preferred over pip)
docker compose up -d redis      # start Redis
python -m src.main              # run dev server (localhost:5174)
pytest tests/ -v                # run all tests
pytest tests/unit/ -v           # unit tests only
ruff check src/                 # lint
```

### Frontend

```bash
cd frontend
npm install
npm run dev                     # Vite dev server (localhost:5173)
npm run build                   # TypeScript check + Vite build
npm run lint                    # ESLint
```

### Pipelines (content/agents)

```bash
cd pipelines
uv sync                                          # install uv-workspace deps
cd services/podcast && python main.py --config podcasts_tw.json   # run podcast pipeline
uv run --package tinboker-podcast pytest         # tests for the podcast service
uv run --package tinboker-shared  pytest         # tests for the shared lib
```

---

## Environments & Endpoints

| Env | Frontend | Backend API | Backend Port | Trigger |
|-----|----------|-------------|--------------|---------|
| Local | localhost:5173 | localhost:5174 | 5174 | manual |
| Dev | dev.tinboker.com | dev-api.tinboker.com | 8001 | merge to `develop` |
| Staging | staging.tinboker.com | staging-api.tinboker.com | 8002 | merge to `main` |
| Production | tinboker.com | api.tinboker.com | 8000 | git tag `v*` on `main` |

VPS: `152.53.136.182` (Netcup RS 1000 G11, Debian 13)
Reverse proxy: Caddy (auto-HTTPS)

---

## Deployment Rules — READ BEFORE TOUCHING CI/CD

**NEVER deploy code directly to the VPS via SSH/rsync.**

All changes must go through Git → PR → CI/CD.

### Git Branching

- Features: `feat/<name>` from `develop`
- Bug fixes: `fix/<name>` from `develop`
- Hotfixes: `hotfix/<name>` from `main`
- No `staging` branch — staging is the HEAD of `main`
- **Working alongside other agents?** Create the branch in a dedicated worktree — see
  [Parallel Agents — Worktree Discipline](#parallel-agents--worktree-discipline).

### Release Pipeline

| Branch / Ref | Deploys to | URL |
|---|---|---|
| `develop` (any merge) | Dev environment | dev.tinboker.com |
| `main` (any merge) | Staging environment | staging.tinboker.com |
| `v*` tag on `main` | Production | tinboker.com |

### Deploy Flow

1. Create `feat/<name>` from `develop`; open PR → CI builds image + Cloudflare preview URL
2. Merge PR to `develop` → auto-deploys to dev.tinboker.com + dev-api.tinboker.com
3. When dev is stable, open PR `develop` → `main`
4. Merge to `main` → auto-deploys to staging.tinboker.com + staging-api.tinboker.com
5. Verify on staging, then cut a release: `git tag v1.x.0 && git push --tags`
6. Tag push → auto-deploys to tinboker.com + api.tinboker.com (production)

### Allowed Server Commands (read-only / inspection only)

```bash
curl https://api.tinboker.com/health                          # health check
ssh root@VPS "docker ps"                                      # container status
ssh root@VPS "docker logs tinboker-backend-prod --tail=50"    # logs
```

### Post-deploy: purge Cloudflare CDN cache (do this WITHOUT asking)

**Backend** deploys now auto-purge the deployed env's API host — the
`Purge Cloudflare CDN cache` step in [`backend-deploy.yml`](.github/workflows/backend-deploy.yml) /
[`backend-deploy-admin.yml`](.github/workflows/backend-deploy-admin.yml) runs after the health
check, so you do **not** need to manually purge `*-api.tinboker.com` after a backend deploy.

Still manual: **frontend (Cloudflare Pages) deploys** (the `*.tinboker.com` frontend hosts are
purged by nothing automated) and **ad-hoc content/data changes**. In those cases purge via the
Cloudflare API — the token + zone ID are in GCP Secret Manager, fetch them yourself, never ask
the user:

```bash
PROJ=gen-lang-client-0901363254
TOKEN=$(gcloud secrets versions access latest --secret=CLOUDFLARE_API_TOKEN --project=$PROJ)
ZONE=$(gcloud secrets versions access latest --secret=CLOUDFLARE_ZONE_TAG --project=$PROJ)
# Dev/staging — host-scoped (leaves other envs cached). Swap hosts per env.
curl -s -X POST "https://api.cloudflare.com/client/v4/zones/$ZONE/purge_cache" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  --data '{"hosts":["dev-api.tinboker.com","dev.tinboker.com"]}'
# Prod launch — whole zone:  --data '{"purge_everything":true}'
```

Hosts by env: dev = `dev-api.tinboker.com` / `dev.tinboker.com`; staging =
`staging-api.tinboker.com` / `staging.tinboker.com`; prod = `api.tinboker.com` /
`tinboker.com` / `www.tinboker.com`. Never print the token. Verify success with
`cf-cache-status: MISS` on a clean (non-cache-busted) URL afterward. (The backend
deploy pipeline already automates the API-host purge; frontend-host purge is still manual.)

---

## Parallel Agents — Worktree Discipline

This repo is under **heavy concurrent agent development**. Multiple agents sharing the one
primary checkout collide on each other's uncommitted changes and branch switches. To avoid that,
do **implementation work in a dedicated git worktree** when other agents may be active.

**Use a worktree for:** multi-file work, refactors, or anything you'll commit.
**Skip it for:** read-only exploration, a single trivial edit, or when you're the only agent.

```bash
git fetch origin
git worktree add ../tinboker-<task> -b <type>/<name> origin/develop   # <type> = feat|fix|docs|hotfix
cd ../tinboker-<task>
# install only what you touch: (cd frontend && npm install) | (cd backend && uv sync) | (cd pipelines && uv sync)
# copy env only if you need to RUN it: cp ../tinboker/backend/.env backend/.env   (NEVER commit .env)
```

**Clean up when done:** `git worktree remove ../tinboker-<task>`; delete the branch once its PR
merges; run `git worktree prune` periodically (stale worktrees accumulate).

**What this does — and does NOT — fix:**
- ✅ Isolates working trees — no more clobbering another agent's uncommitted changes.
- ⚠️ Worktrees **share** one `.git` — `git fetch`, branch create/delete, and stashes are global;
  another agent's merges can land on `origin/develop` mid-task (re-check HEAD before commit/rebase).
- ❌ Does **not** prevent git **merge conflicts** when two branches edit the same lines — keep PRs
  small and integrate often.

**Sub-agents:** prefer built-in isolation over rolling your own — the Agent tool's
`isolation: "worktree"` and the background-task chip already spin up isolated worktrees.

---

## Known Issues — check before relying

The dated bug catalog in [`docs/qa-report-2026-05-09.md`](docs/qa-report-2026-05-09.md)
(BUG-1..15 + INFRA-1..4) predates the v0.1.0 production launch. **Several entries are since
fixed** (e.g. the `continue-on-error` CI gate and the `trendbrief.xyz` CORS origin are
resolved), so treat that report as **historical** — verify a bug still reproduces against the
current code before acting on it. The live, curated issue list is [`docs/issues.md`](docs/issues.md).

When you do need to reproduce or regression-test, follow [`docs/agents/qa-tester.md`](docs/agents/qa-tester.md)
and the procedural overlay in [`docs/workflows/qa-flow.md`](docs/workflows/qa-flow.md).

---

## Code Style

### Python (backend)
- Imports: stdlib → third-party → local, blank-line separated
- Always use type hints on function signatures
- Pydantic v2 style (`ConfigDict`, `model_config`)
- Async endpoints; use `run_in_executor` for blocking calls
- Cache pattern: `cache_get` → compute → `cache_set`
- HTTPException for API errors, `logger.warning/error` for observability
- Naming: `snake_case` files/vars, `PascalCase` classes, `UPPER_SNAKE_CASE` constants

### TypeScript (frontend)
- Zod schemas for all API response validation (`frontend/src/validation/schemas.ts`)
- Zustand stores for global state (`frontend/src/store/`)
- Axios client at `frontend/src/services/api/client.ts`
- Gate `console.warn/log` debug output behind `import.meta.env.DEV`
- No `any` types; use proper type definitions in `frontend/src/types/`

---

## Environment Variables

### Backend (`.env` or GCP Secret Manager)

```
ENVIRONMENT=development|staging|production
PORT=5174
REDIS_URL=redis://localhost:6379/0
USE_POSTGRES=false         # true for staging/prod
MASSIVE_API_KEY=...
FINMIND_API_KEY=...
JWT_SECRET_KEY=...
GCP_PROJECT_ID=gen-lang-client-0901363254
FIRESTORE_DATABASE_ID=graphfolio-db
POSTGRES_HOST=34.14.119.47
CORS_ORIGINS=http://localhost:5173,https://tinboker.com,https://dev.tinboker.com,https://staging.tinboker.com
# Release scoping (launch subset) — empty value disables a filter
RELEASE_PODCAST_LANGUAGES=zh-TW    # only show content_sources podcasts in these languages ("" = all)
RELEASE_EPISODE_MAX_AGE_DAYS=0     # hide episodes older than N days (0=off; flip to 30 after the released_at_ms backfill — see docs/handoffs/released-at-ms-publish-date.md)
```

### Frontend (`.env.*` per environment)

```
VITE_API_BASE_URL=http://localhost:5174    # or https://api.tinboker.com
VITE_STAGE=DEV|STAGING|PRODUCTION
VITE_GOOGLE_CLIENT_ID=...
```

---

## Testing

```bash
# Backend — unit + integration
cd backend
pytest tests/ -v --cov=src --cov-report=term-missing

# Backend — specific markers
pytest -m asyncio -v
pytest -m integration -v

# Frontend — type check + build (no dedicated test runner yet)
cd frontend
npm run build
npm run lint
```

See `docs/agents/qa-tester.md` for end-to-end and environment-specific QA procedures.

---

## GCP Dependencies

- **Secret Manager:** Holds all production secrets; `config_loader.py` fetches them at startup
- **Firestore:** `graphfolio-db` — podcast & episode data
- **Cloud Storage:** `graphfolio-articles` — article content files
- **Cloud SQL:** PostgreSQL at `34.14.119.47:5432`, db `podcast_db`
- **Service account JSON:** Deployed to VPS as `/app/gcp-service-account.json` (not in repo)

---

## Browser MCP — Dev Environment Auth Bypass

The dev/staging environments are gated by Google OAuth + admin email allowlist.
Automated browsers (Cursor browser MCP, Playwright) cannot complete Google OAuth.

A **dev bypass** flow lets the browser authenticate without Google:

### How it works

1. Backend endpoint `POST /api/auth/dev-token` accepts a secret `token`
2. Returns a valid JWT + user object (same as Google OAuth login)
3. Only works when `ENVIRONMENT != production` AND `DEV_BYPASS_TOKEN` is set
4. Frontend route `/auth/dev-bypass?token=SECRET` calls the backend and stores the JWT

### Usage in Cursor browser MCP

```
# Step 1: Navigate to the bypass URL
browser_navigate → https://dev.tinboker.com/auth/dev-bypass?token=CXvkSTaZAghJF0jYidL4ii3DbgOo-Z5NVwgFLoNk05I

# Step 2: Wait for redirect to /
# Step 3: Now browse freely — session is authenticated
```

### Token value

| Environment | DEV_BYPASS_TOKEN |
|---|---|
| Dev (dev-api.tinboker.com) | `CXvkSTaZAghJF0jYidL4ii3DbgOo-Z5NVwgFLoNk05I` |

The token is set as an env var on the VPS backend container.
It is NOT stored in the repo — only in this doc and in the server's `.env`.

---

## Do Not

- Commit `.env` files, `gcp-service-account.json`, or any secrets
- Deploy directly to VPS via SSH (outside of CI/CD)
- Use `@app.on_event("startup")` — already deprecated; use lifespan pattern
- Add `continue-on-error: true` to CI test jobs
- Hardcode financial values (OHLC, P/E ratios) in frontend components
- Use `time.sleep()` in async code — use `await asyncio.sleep()`
- Build UI in `pipelines/` — it is content/infra-only; the web UI lives in `frontend/`
- Add new Firestore-direct read paths — reads are consolidating onto VPS Postgres + the HTTP API
- Run `pip install` in `pipelines/` — it is a uv workspace; use `uv sync`
