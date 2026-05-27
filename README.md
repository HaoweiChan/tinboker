# TinBoker Platform

Taiwanese stock and podcast intelligence platform. Browse TW/US stocks, explore relationship graphs, track market trends, and discover financial podcasts.

**Live:** [tinboker.com](https://tinboker.com) · **Dev:** [dev.tinboker.com](https://dev.tinboker.com) · **API Docs:** [api.tinboker.com/docs](https://api.tinboker.com/docs)

---

## Features

- Stock dashboard with price charts (TW + US markets)
- Relationship graph explorer linking companies, sectors, and events
- Financial podcast directory with episode playback (GCP Firestore)
- Full-text search with autocomplete
- Google OAuth authentication
- Real-time price feed over WebSocket
- Sector heatmaps and market trend views

---

## Architecture

```
Browser
   │
   ▼
Cloudflare Pages (static SPA)          ← React 19 + Vite
   │
   ▼
Cloudflare Proxy (DDoS + cache)
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
       ├── Redis 7-alpine (cache)
       └── Netdata (monitoring)
              │
              ▼
       GCP Services
       ├── Cloud SQL (PostgreSQL)   — stock & user data
       ├── Firestore                — podcast & episode data
       ├── Cloud Storage            — article content
       └── Secret Manager           — credentials
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 19, TypeScript 5.9, Vite 7, Tailwind CSS 4, Shadcn UI |
| Charts | TradingView Lightweight Charts, D3.js, Nivo |
| Graph Viz | React Flow 11, Dagre, ELK |
| State | Zustand 5 |
| Routing | React Router 7 |
| Validation | Zod 4 |
| Backend | FastAPI 0.104, Python 3.12, Pydantic v2 |
| ORM | SQLAlchemy 2 (SQLite dev / PostgreSQL prod) |
| Cache | Redis 7 with hiredis |
| Auth | Google OAuth → JWT (python-jose) |
| Data APIs | Massive API (US stocks), FinMind (TW stocks) |
| Infrastructure | Docker, Caddy, Netcup VPS, GitHub Actions |
| CDN | Cloudflare Pages + Cloudflare proxy |

---

## Local Development

### Prerequisites

- Python 3.12+, [`uv`](https://docs.astral.sh/uv/)
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

API docs: `http://localhost:5174/docs`

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
│   │   ├── routers/          # 26 API endpoint handlers
│   │   ├── services/         # Business logic (26 modules)
│   │   ├── database/         # ORM models & CRUD (16 modules)
│   │   ├── models/           # Pydantic request/response schemas
│   │   ├── cache/            # Redis client
│   │   └── workers/          # Background tasks & cron jobs
│   ├── tests/
│   │   ├── unit/             # pytest unit tests
│   │   ├── integration/      # API integration tests
│   │   └── performance/      # latency benchmarks
│   ├── deploy/               # Caddy config, systemd units
│   └── docker-compose*.yml   # per-environment compose files
│
├── frontend/
│   ├── src/
│   │   ├── pages/            # 31 route-level React pages
│   │   ├── components/       # Reusable UI components
│   │   ├── services/         # API client + business logic
│   │   ├── store/            # Zustand state stores
│   │   ├── types/            # TypeScript type definitions
│   │   └── validation/       # Zod schemas for API responses
│   └── public/               # Static assets + PWA manifest
│
├── .github/workflows/        # CI/CD pipelines
├── docs/                     # Domain references, workflows, infra runbook, QA suite, firestore-contract
└── CLAUDE.md                 # AI agent instructions
```

---

## API Overview

| Endpoint | Purpose |
|----------|---------|
| `GET /api/stocks` | Stock list with sorting/filtering |
| `GET /api/stocks/{ticker}` | Stock detail + price history |
| `GET /api/graphs` | Relationship graph list |
| `GET /api/news` | News and event articles |
| `GET /api/podcasts` | Podcast channels |
| `GET /api/episodes/{id}` | Episode detail |
| `GET /api/search` | Full-text search |
| `GET /api/search/suggest` | Search autocomplete |
| `POST /auth/login` | Google OAuth → JWT |
| `WS /ws/prices` | Real-time stock price feed |

Full interactive docs: [api.tinboker.com/docs](https://api.tinboker.com/docs)

---

## Environments

| Environment | Frontend | Backend | Branch / Trigger |
|-------------|----------|---------|-----------------|
| Production | [tinboker.com](https://tinboker.com) | [api.tinboker.com](https://api.tinboker.com) | `v*` tag on `main` |
| Staging | [staging.tinboker.com](https://staging.tinboker.com) | [staging-api.tinboker.com](https://staging-api.tinboker.com) | merge to `main` |
| Dev | [dev.tinboker.com](https://dev.tinboker.com) | [dev-api.tinboker.com](https://dev-api.tinboker.com) | merge to `develop` |
| Local | localhost:5173 | localhost:5174 | any |

---

## CI/CD

| Pipeline | Trigger | Effect |
|----------|---------|--------|
| `backend-ci.yml` | PR to develop/main | Lint (ruff) + pytest |
| `backend-deploy.yml` | Push to develop/main | Docker build → VPS deploy |
| `frontend-ci.yml` | PR to develop/main | TypeScript check + ESLint |
| `frontend-deploy.yml` | Push to develop/main | Cloudflare Pages deploy |
| `backend-health-check.yml` | Cron every 10 min | Health check all envs |

Docker images: `ghcr.io/haoweichan/tinboker-backend:{tag}`

---

## Testing

```bash
# Backend — all tests
cd backend && pytest tests/ -v

# Backend — unit tests only
cd backend && pytest tests/unit/ -v

# Backend — with coverage
cd backend && pytest tests/ -v --cov=src --cov-report=term-missing

# Frontend — type check + build
cd frontend && npm run build

# Frontend — lint
cd frontend && npm run lint

# End-to-end QA
# See docs/agents/qa-tester.md for full environment test procedures
```

---

## Contributing

1. Branch from `develop`: `git checkout -b feat/your-feature develop`
2. Make backend changes first, then frontend
3. Open a PR targeting `develop` — CI must pass
4. Request review; merge triggers auto-deploy to dev.tinboker.com
5. Promote to staging/production by merging `develop` → `main`, then tagging

See [CLAUDE.md](CLAUDE.md) for AI agent guidelines and [docs/infra-runbook.md](docs/infra-runbook.md) for the infrastructure runbook.
