<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="frontend/public/brand/tinboker-square-dark-512.png">
  <img src="frontend/public/brand/tinboker-square-light-512.png" alt="TinBoker logo" width="132" height="132">
</picture>

# 聽播客 ｜ TinBoker

**Taiwanese stock &amp; podcast intelligence.**
Browse TW/US stocks, explore relationship graphs, track market trends, and discover AI-summarized financial podcasts.

[![React](https://img.shields.io/badge/React-19-149ECA?style=flat-square&logo=react&logoColor=white)](https://react.dev)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.9-3178C6?style=flat-square&logo=typescript&logoColor=white)](https://www.typescriptlang.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org)
[![Vite](https://img.shields.io/badge/Vite-7-646CFF?style=flat-square&logo=vite&logoColor=white)](https://vite.dev)
[![Cloudflare Pages](https://img.shields.io/badge/Cloudflare-Pages-F38020?style=flat-square&logo=cloudflare&logoColor=white)](https://pages.cloudflare.com)

**Live:** [tinboker.com](https://tinboker.com) &nbsp;·&nbsp; **Dev:** [dev.tinboker.com](https://dev.tinboker.com) &nbsp;·&nbsp; **API Docs:** [api.tinboker.com/docs](https://api.tinboker.com/docs)

</div>

---

## What is TinBoker?

TinBoker (聽播客) is a financial intelligence platform for the Taiwanese market. It pairs a
real-time **stock dashboard** (TW + US markets) with an **AI content pipeline** that ingests
financial podcasts and news, derives transcripts, summaries, ticker sentiment, and an
entity/topic knowledge graph, then surfaces it through a Traditional-Chinese web UI.

This repository is a **monorepo** consolidating what used to be two separate projects —
the platform (`tinboker-platform`) and the content/agent pipelines (`tinboker-agents`) —
into one standalone repo.

| Tier | Path | What it is | Runs on |
|------|------|-----------|---------|
| **Web UI** | [`frontend/`](frontend/) | React 19 + Vite SPA (Traditional Chinese) | Cloudflare Pages → `tinboker.com` |
| **Platform API** | [`backend/`](backend/) | FastAPI app — stocks, search, graphs, auth, podcasts | Docker on Netcup VPS → `api.tinboker.com` |
| **Content pipelines** | [`pipelines/`](pipelines/) | Podcast + news ingestion → summaries, ticker sentiment, wiki graph | systemd on VPS, serves `/api/wiki` (:8003) |
| **MCP servers** | [`mcp-servers/`](mcp-servers/) | Agent tooling (stock translations, article authoring) | `uvx`, stdio |

---

## Features

- **Stock dashboard** — price charts and key statistics for TW + US markets
- **Relationship graph explorer** — companies, sectors, and events linked into an interactive graph
- **Podcast intelligence** — AI-summarized financial podcasts with per-episode ticker sentiment
- **News &amp; wiki** — ingested market news folded into an entity/topic knowledge base
- **Full-text search** with autocomplete and trending tickers/tags
- **Real-time price feed** over WebSocket (FinMind + Massive)
- **Google OAuth** authentication, watchlists, and an admin/config control plane
- **PWA** — installable, offline-aware, with light/dark theming

---

## Architecture

```
                         Browser  /  PWA
                              │
                              ▼
              Cloudflare Pages (static SPA)            ← frontend/  (React 19 + Vite)
                              │
                              ▼
              Cloudflare Proxy (DDoS + CDN cache)
                              │
                              ▼
              Netcup VPS — Caddy (reverse proxy + auto-HTTPS)
        ┌─────────────────────┼───────────────────────────────┐
        │                     │                                │
   :8000/:8001/:8002     :8003 (podcast)                  systemd timer
   Platform API          /api/wiki, /api/podcast          news ingestion
   (backend/)            (pipelines/services/podcast)      (pipelines/services/news)
        │                     │                                │
        └─────────────────────┴────────────────┬───────────────┘
                              │                 │
                       Docker Compose      Spotify RSS · Tavily/RSS news
                       ├── FastAPI               │
                       ├── Redis 7-alpine        ▼  transcribe → summarize → extract
                       └── Netdata          GCS (mp3, transcripts, summaries, slides)
                              │
                              ▼
                         GCP Services
                       ├── Cloud SQL (PostgreSQL)  — stock, user, ticker_insights, wiki
                       ├── Firestore               — podcast & episode documents
                       ├── Cloud Storage           — article / content files
                       └── Secret Manager          — credentials
```

> **Data direction:** the content pipelines *derive and write* content (Postgres + Firestore +
> GCS); the platform API *reads and serves* it to the web UI. Reads are consolidating onto the
> VPS Postgres + HTTP API — avoid adding new Firestore-direct read paths.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 19, TypeScript 5.9, Vite 7, Tailwind CSS 4, Shadcn UI |
| Charts | TradingView Lightweight Charts, D3.js, Nivo |
| Graph viz | React Flow 11, Dagre, ELK |
| State / routing | Zustand 5, React Router 7 |
| Validation | Zod 4 |
| Backend | FastAPI 0.104, Python 3.12, Pydantic v2 |
| ORM / cache | SQLAlchemy 2 (SQLite dev / PostgreSQL prod), Redis 7 (hiredis) |
| Auth | Google OAuth → JWT (python-jose) |
| Pipelines | uv workspaces, LangGraph content builder, Marp slides, Spotify/Tavily ingestion |
| Data APIs | Massive API (US stocks), FinMind (TW stocks), Firestore (podcasts) |
| Infra | Docker, Caddy, Netcup VPS, GitHub Actions, Cloudflare |

---

## Repository Layout

```
tinboker/
├── frontend/            React 19 + Vite web UI        → Cloudflare Pages (tinboker.com)
├── backend/             FastAPI platform API           → Docker on VPS (api.tinboker.com)
├── pipelines/           Content & agent pipelines (podcast + news ingestion, wiki builder)
├── mcp-servers/         MCP servers for AI tooling (stock-translations, article-authoring)
├── docs/                Domain references, workflows, data contracts, runbooks
├── .claude/             Claude Code subagents + skills (thin wrappers → docs/)
├── .codex/              Codex CLI agents + MCP config
├── .cursor/rules/       Cursor rules (auto-attached by file glob)
├── .agents/             Tool-neutral skill wrappers
├── .github/workflows/   CI/CD (backend, frontend, pipelines)
├── CLAUDE.md            Root AI-agent context  (AGENTS.md → symlink)
└── README.md
```

<details>
<summary><strong>backend/</strong> — FastAPI platform (31 routers, 30 services)</summary>

```
backend/src/
├── main.py          FastAPI app & lifespan
├── config.py        Settings (env + GCP Secret Manager)
├── routers/         31 API endpoint modules (stocks, search, graph, podcast, admin_*, …)
├── services/        30 business-logic modules (stock, finmind, massive, insight, …)
├── database/        ORM models & CRUD
├── models/ schemas/ Pydantic request/response models
├── auth/            Google OAuth + JWT
├── cache/           Redis client
├── middleware/      Request middleware
├── workers/         Background tasks & cron jobs
└── utils/           Shared helpers
```
</details>

<details>
<summary><strong>frontend/</strong> — React web UI (38 route-level pages)</summary>

```
frontend/src/
├── pages/           38 route-level React pages
├── components/      Reusable UI (charts, stock, graph, financial, industry, …)
├── services/        API client + business logic
├── store/           Zustand state stores
├── schemas/ validation/   Zod schemas for API responses
├── hooks/ lib/ utils/     Hooks and helpers
├── types/           TypeScript type definitions
└── assets/          SVG icon system (no emoji icons)
```
</details>

<details>
<summary><strong>pipelines/</strong> — content / agent backend (uv workspace)</summary>

```
pipelines/
├── services/
│   ├── podcast/     Spotify RSS → download → transcribe → summarize → wiki + GCS; serves /api/wiki (:8003)
│   └── news/        Tavily/RSS news → resolve tickers → ingest (systemd timer)
├── libs/shared/     secrets (GSM), GCS client, config, wiki_builder (Postgres-backed)
├── scripts/         seeding & ops scripts
└── docs/            wiki schema, content-api roadmap, data-consolidation plan, MIGRATION runbook
```
</details>

---

## Local Development

**Prerequisites:** Python 3.12+ with [`uv`](https://docs.astral.sh/uv/), Node 20+, Docker (for Redis).

### Backend — platform API

```bash
cd backend
cp .env.example .env          # fill in API keys
uv sync                       # install Python deps
docker compose up -d redis    # start Redis
python -m src.main            # → localhost:5174  (docs at /docs)
```

### Frontend — web UI

```bash
cd frontend
cp .env.example .env.local    # set VITE_API_BASE_URL=http://localhost:5174
npm install
npm run dev                   # → localhost:5173
```

### Pipelines — content ingestion

```bash
cd pipelines
uv sync                                          # install workspace deps
cd services/podcast && python main.py --config podcasts_tw.json
```

> Pipelines are infra/content-only — **no UI lives here.** See [`pipelines/AGENTS.md`](pipelines/AGENTS.md).

---

## Environments

| Environment | Frontend | Backend | Trigger |
|-------------|----------|---------|---------|
| Production | [tinboker.com](https://tinboker.com) | [api.tinboker.com](https://api.tinboker.com) `:8000` | `v*` tag on `main` |
| Staging | [staging.tinboker.com](https://staging.tinboker.com) | [staging-api.tinboker.com](https://staging-api.tinboker.com) `:8002` | merge to `main` |
| Dev | [dev.tinboker.com](https://dev.tinboker.com) | [dev-api.tinboker.com](https://dev-api.tinboker.com) `:8001` | merge to `develop` |
| Local | localhost:5173 | localhost:5174 | manual |

VPS: `152.53.136.182` (Netcup RS 1000 G11, Debian 13) · reverse proxy: Caddy (auto-HTTPS).

---

## CI/CD

| Pipeline | Trigger | Effect |
|----------|---------|--------|
| `backend-ci.yml` | PR → develop/main | Lint (ruff) + pytest |
| `backend-deploy.yml` / `backend-deploy-admin.yml` | Push → develop/main | Docker build → VPS deploy → Cloudflare purge |
| `frontend-ci.yml` | PR → develop/main | TypeScript check + ESLint |
| `frontend-deploy.yml` | Push → develop/main | Cloudflare Pages deploy |
| `pipelines-ci.yml` | PR → develop/main | Lint + pytest (uv workspace) |
| `pipelines-deploy.yml` | Push → develop/main | Deploy pipelines services to VPS |
| `backend-health-check.yml` | Cron (10 min) | Health check all envs |

Docker images: `ghcr.io/haoweichan/tinboker-backend:{tag}`. Deploys flow strictly through
Git → PR → CI/CD — never SSH/rsync to the VPS directly. See
[`docs/workflows/deploy-flow.md`](docs/workflows/deploy-flow.md).

---

## Testing

```bash
# Backend — all tests (or unit-only, or with coverage)
cd backend && pytest tests/ -v
cd backend && pytest tests/unit/ -v
cd backend && pytest tests/ -v --cov=src --cov-report=term-missing

# Pipelines — per-package (uv workspace)
cd pipelines && uv run --package tinboker-podcast pytest
cd pipelines && uv run --package tinboker-shared  pytest

# Frontend — type check + build, and lint
cd frontend && npm run build
cd frontend && npm run lint
```

End-to-end and environment-specific QA: [`docs/agents/qa-tester.md`](docs/agents/qa-tester.md).

---

## Working with AI agents

This repo is set up for AI coding tools across vendors. All configs are **thin wrappers** that
point at the tool-neutral domain docs in [`docs/agents/`](docs/agents/), so guidance stays in one
place:

- **Claude Code** — subagents in [`.claude/agents/`](.claude/agents/), skills in [`.claude/skills/`](.claude/skills/)
- **Codex CLI** — agents in [`.codex/agents/`](.codex/agents/)
- **Cursor** — rules in [`.cursor/rules/`](.cursor/rules/) (auto-attached by file glob)
- **Root context** — [`CLAUDE.md`](CLAUDE.md) (symlinked as `AGENTS.md`), plus
  [`backend/AGENTS.md`](backend/AGENTS.md), [`frontend/AGENTS.md`](frontend/AGENTS.md), and
  [`pipelines/AGENTS.md`](pipelines/AGENTS.md)

---

## Contributing

1. Branch from `develop`: `git checkout -b feat/your-feature develop`
2. Open a PR targeting `develop` — CI must pass
3. Merge to `develop` auto-deploys to dev; promote via `develop` → `main` (staging), then tag `v*` (production)

See [`CLAUDE.md`](CLAUDE.md) for agent guidelines and [`docs/infra-runbook.md`](docs/infra-runbook.md)
for the infrastructure runbook.
