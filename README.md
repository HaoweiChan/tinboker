# TinBoker Platform

Taiwanese stock & podcast intelligence platform. Browse stocks, listen to financial podcasts,
explore relationship graphs, and track market trends.

**Live:** [tinboker.com](https://tinboker.com) · **Dev:** [dev.tinboker.com](https://dev.tinboker.com)

---

## Architecture

```
Cloudflare Edge (DDoS + cache)
        │
        ▼
Netcup VPS — Caddy (reverse proxy + auto-HTTPS)
        ├── :8000  api.tinboker.com          ← production
        ├── :8001  dev-api.tinboker.com      ← dev
        └── :8002  staging-api.tinboker.com  ← staging
                │
                ▼
         Docker Compose
         ├── FastAPI (Python 3.12)
         ├── Redis 7-alpine
         └── Netdata (monitoring)
                │
                ▼
         GCP Services
         ├── Cloud SQL (PostgreSQL)   — stock & user data
         ├── Firestore                — podcast & episodes
         ├── Cloud Storage            — article content
         └── Secret Manager           — credentials
```

Frontend is deployed to **Cloudflare Pages** (static SPA, no server).

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 19, TypeScript 5.9, Vite 7, Tailwind CSS 4, Shadcn UI |
| Charts | TradingView Lightweight Charts, D3.js |
| Graph Viz | React Flow 11, Dagre, ELK |
| State | Zustand 5 |
| Routing | React Router 7 |
| Backend | FastAPI 0.104, Python 3.12, Pydantic v2 |
| ORM | SQLAlchemy (SQLite dev / PostgreSQL prod) |
| Cache | Redis 7 with hiredis |
| Auth | Google OAuth → JWT (python-jose) |
| Data APIs | Massive API (US stocks), FinMind (TW stocks) |
| Infrastructure | Docker, Caddy, Netcup VPS, GitHub Actions |
| CDN | Cloudflare Pages + Cloudflare proxy |

---

## Local Development

### Prerequisites

- Python 3.12+, `uv` (or pip)
- Node 20+, npm
- Docker (for Redis)

### Backend

```bash
cd backend
cp .env.example .env          # fill in API keys
uv sync                       # install Python deps
docker compose up -d redis    # start Redis
python -m src.main            # starts on localhost:5174
```

API docs available at `http://localhost:5174/docs`.

### Frontend

```bash
cd frontend
cp .env.example .env.local    # set VITE_API_BASE_URL=http://localhost:5174
npm install
npm run dev                   # starts on localhost:5173
```

---

## Project Structure

```
tinboker-platform/
├── backend/
│   ├── src/
│   │   ├── main.py           # FastAPI app & lifespan
│   │   ├── config.py         # Settings (env + GCP Secret Manager)
│   │   ├── routers/          # API endpoint handlers
│   │   ├── services/         # Business logic
│   │   ├── database/         # ORM models & CRUD
│   │   ├── models/           # Pydantic schemas
│   │   └── cache/            # Redis client
│   ├── tests/
│   │   ├── unit/             # pytest unit tests
│   │   ├── integration/      # API integration tests
│   │   └── performance/      # latency benchmarks
│   ├── deploy/               # Caddy config, systemd units
│   └── docker-compose*.yml   # per-environment compose files
│
├── frontend/
│   ├── src/
│   │   ├── pages/            # Route-level React pages (19 pages)
│   │   ├── components/       # Reusable UI components
│   │   ├── services/api/     # Axios API client functions
│   │   ├── store/            # Zustand state stores
│   │   ├── types/            # TypeScript type definitions
│   │   └── validation/       # Zod schemas for API responses
│   └── public/               # Static assets + PWA manifest
│
├── .github/workflows/        # CI/CD pipelines
├── openspecs/                # Feature specifications
├── MIGRATION.md              # Infrastructure runbook
├── QA_AGENT.md               # QA testing instructions
└── CLAUDE.md                 # AI agent instructions
```

---

## API Overview

| Prefix | Purpose |
|--------|---------|
| `GET /api/stocks` | Stock list with sorting |
| `GET /api/stocks/{ticker}` | Stock detail + price history |
| `GET /api/graphs` | Relationship graph list |
| `GET /api/news` | News/event articles |
| `GET /api/podcasts` | Podcast channels (Firestore) |
| `GET /api/episodes/{id}` | Episode detail |
| `GET /api/search` | Full-text search |
| `GET /api/search/suggest` | Search autocomplete |
| `POST /auth/login` | Google OAuth → JWT |
| `WS /ws/prices` | Real-time stock prices |

Full interactive docs: `https://api.tinboker.com/docs`

---

## CI/CD

| Pipeline | Trigger | Effect |
|----------|---------|--------|
| `backend-ci.yml` | PR to develop/main | Tests + lint |
| `backend-deploy.yml` | Push to develop/main | Docker build → VPS deploy |
| `frontend-ci.yml` | PR to develop/main | TypeScript + ESLint |
| `frontend-deploy.yml` | Push to develop/main | Cloudflare Pages deploy |
| `backend-health-check.yml` | Cron every 10 min | Health check all envs |

Docker images: `ghcr.io/haoweichan/tinboker-backend:{tag}`

---

## Environments

| Environment | Frontend URL | Backend URL | Branch |
|-------------|-------------|-------------|--------|
| Production | tinboker.com | api.tinboker.com | `main` |
| Dev | dev.tinboker.com | dev-api.tinboker.com | `develop` |
| Staging | `{branch}.tinboker-platform.pages.dev` | staging-api.tinboker.com | manual |
| Local | localhost:5173 | localhost:5174 | any |

---

## Testing

```bash
# Backend
cd backend && pytest tests/ -v

# Frontend type check
cd frontend && npm run build

# End-to-end QA
# See QA_AGENT.md for full environment test procedures
```

---

## Contributing

1. Branch from `develop`: `git checkout -b feat/your-feature develop`
2. Backend changes first, frontend after
3. Open PR to `develop` — CI must pass
4. Request review; merge triggers auto-deploy to dev
5. Promote to production by merging `develop` → `main`

See `CLAUDE.md` for AI agent guidelines and `MIGRATION.md` for infrastructure details.
