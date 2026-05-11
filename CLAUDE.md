# CLAUDE.md — TinBoker Platform

This file is the root context for Claude Code agents. Sub-agents should also read
`backend/AGENTS.md` and `frontend/AGENTS.md` for domain-specific rules.

---

## Project Summary

TinBoker is a Taiwanese stock & podcast intelligence platform.

- **Frontend:** React 19 + TypeScript + Vite → Cloudflare Pages (`tinboker.com`)
- **Backend:** FastAPI (Python 3.12) → Docker on Netcup VPS (`api.tinboker.com`)
- **Database:** SQLite (dev) / Cloud SQL PostgreSQL (staging + prod)
- **Cache:** Redis 7-alpine on VPS
- **Auth:** Google OAuth → JWT
- **External APIs:** Massive API (US stocks), FinMind (TW stocks), GCP Firestore (podcasts)

---

## Repository Layout

```
tinboker-platform/
├── backend/            FastAPI app, Docker, deploy scripts
├── frontend/           React + Vite app
├── .github/workflows/  CI/CD pipelines (GitHub Actions)
├── openspecs/          Feature design docs
├── MIGRATION.md        VPS/infrastructure runbook
├── QA_REPORT.md        Latest QA audit with known bugs
└── QA_AGENT.md         QA agent instructions for all environments
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

| Env | Frontend | Backend API | Backend Port |
|-----|----------|-------------|--------------|
| Local | localhost:5173 | localhost:5174 | 5174 |
| Dev | dev.tinboker.com | dev-api.tinboker.com | 8001 |
| Staging | `{branch}.tinboker-platform.pages.dev` | staging-api.tinboker.com | 8002 |
| Production | tinboker.com | api.tinboker.com | 8000 |

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
- `develop` → dev + staging environments
- `main` → production

### Deploy Flow

1. Backend PR → CI builds `ghcr.io/haoweichan/tinboker-backend:pr-{N}`
2. Manually deploy PR image to staging to test
3. Frontend PR → Cloudflare preview URL auto-created
4. Merge backend PR to `develop` → auto-deploys to dev/staging
5. Merge frontend PR to `develop` → Cloudflare auto-deploys to dev
6. Merge `develop` → `main` to promote both to production

### Allowed Server Commands (read-only / inspection only)

```bash
curl https://api.tinboker.com/health                          # health check
ssh root@VPS "docker ps"                                      # container status
ssh root@VPS "docker logs tinboker-backend-prod --tail=50"    # logs
```

---

## Critical Known Issues (from QA_REPORT.md)

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

Run `QA_AGENT.md` instructions to reproduce any of these before fixing.

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
CORS_ORIGINS=http://localhost:5173,https://tinboker.com,https://dev.tinboker.com
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

See `QA_AGENT.md` for end-to-end and environment-specific QA procedures.

---

## GCP Dependencies

- **Secret Manager:** Holds all production secrets; `config_loader.py` fetches them at startup
- **Firestore:** `graphfolio-db` — podcast & episode data
- **Cloud Storage:** `graphfolio-articles` — article content files
- **Cloud SQL:** PostgreSQL at `34.14.119.47:5432`, db `podcast_db`
- **Service account JSON:** Deployed to VPS as `/app/gcp-service-account.json` (not in repo)

---

## Do Not

- Commit `.env` files, `gcp-service-account.json`, or any secrets
- Deploy directly to VPS via SSH (outside of CI/CD)
- Use `@app.on_event("startup")` — already deprecated; use lifespan pattern
- Add `continue-on-error: true` to CI test jobs
- Hardcode financial values (OHLC, P/E ratios) in frontend components
- Use `time.sleep()` in async code — use `await asyncio.sleep()`
