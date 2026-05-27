# CLAUDE.md — TinBoker Platform

This file is the root context for Claude Code agents. Sub-agents should also read
`backend/AGENTS.md` and `frontend/AGENTS.md` for domain-specific rules.

---

## Project Summary

TinBoker is a Taiwanese stock & podcast intelligence platform.

- **Frontend:** React 19 + TypeScript + Vite → Cloudflare Pages (`tinboker.com`)
- **Backend:** FastAPI (Python 3.12) → Docker on Netcup VPS (`api.tinboker.com`)
- **Database:** SQLite (dev) / Cloud SQL PostgreSQL (main + prod)
- **Cache:** Redis 7-alpine on VPS
- **Auth:** Google OAuth → JWT
- **External APIs:** Massive API (US stocks), FinMind (TW stocks), GCP Firestore (podcasts)

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

**Procedural workflows:**
- `docs/workflows/deploy-flow.md` — branch → env → tag pipeline
- `docs/workflows/qa-flow.md` — reproducing known bugs, dev-bypass flow
- `docs/workflows/firestore-data-change.md` — Firestore schema / data-contract changes

**Canonical data contract (cross-repo with tinboker-agents):**
- `docs/firestore-contract.md`

**Operational reference:**
- `docs/infra-runbook.md` — VPS, Caddy, GCP, Cloudflare, Docker, env vars (live ops)
- `docs/qa-report-2026-05-09.md` — dated bug catalog (BUG-1..15 + INFRA-1..4); verify status before relying on specific claims

**Code style / conventions (unchanged):**
- `backend/AGENTS.md` — Python style, key file map
- `frontend/AGENTS.md` — UI conventions, zh-TW localization, icon system

**Tool-specific entry points:**
- Claude Code subagents: `.claude/agents/<domain>.md` (delegate by domain)
- Claude Code skills: `.claude/skills/<workflow>/SKILL.md` (invoked by intent)
- Cursor rules: `.cursor/rules/<domain>.mdc` (auto-attached by file glob)
- Codex CLI / OpenCode / Aider: read this file (`AGENTS.md` is symlinked here)

---

## Repository Layout

```
tinboker-platform/
├── backend/            FastAPI app, Docker, deploy scripts
├── frontend/           React + Vite app
├── docs/               Domain references, workflows, firestore-contract
├── .claude/            Claude Code subagents + skills (thin wrappers)
├── .cursor/rules/      Cursor rules (thin wrappers)
└── .github/workflows/  CI/CD pipelines (GitHub Actions)
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

---

## Critical Known Issues (from docs/qa-report-2026-05-09.md)

Before adding features, be aware of these open bugs:

| ID | Severity | Summary | File |
|----|----------|---------|------|
| BUG-1 | CRITICAL | Search index never built (wrong startup hook) | `backend/src/routers/search.py:92` |
| BUG-2 | CRITICAL | Industry heatmap blank (stub data) | `frontend/src/services/mocks/sectorData.ts:69` |
| BUG-3 | CRITICAL | 18/51 unit tests failing | `tests/unit/test_graph_service.py` etc. |
| BUG-4 | CRITICAL | Backend CI never blocks PRs (`continue-on-error: true`) | `.github/workflows/backend-ci.yml:10` |
| BUG-5 | CRITICAL | Graph Gallery Zod validation errors on `marketCapTier` | `frontend/src/validation/schemas.ts:46` |
| BUG-7 | MEDIUM | Stock key statistics are fabricated (hardcoded values) | `frontend/src/pages/StockDashboard.tsx:211` |
| BUG-9 | MEDIUM | CORS origins include old domain `trendbrief.xyz` | `backend/src/config.py:104` |
| BUG-10 | MEDIUM | Recommendations endpoint 404 (wrong URL in frontend) | `frontend/src/services/recommendationService.ts` |

Run `docs/agents/qa-tester.md` instructions to reproduce any of these before fixing.

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
