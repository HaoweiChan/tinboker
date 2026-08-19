# CLAUDE.md — TinBoker Monorepo

Router file: identity, hard rules, and pointers. Each topic's detail lives in exactly ONE
referenced file — when a trigger below matches your task, **read that file before acting;
do not work from memory of it**. If this file conflicts with a referenced doc, the doc is
newer — trust it and fix the pointer here (rules for editing this file:
`docs/ai-ops/40-maintenance-protocol.md`).

Note: the root `AGENTS.md` is a symlink to this file — non-Claude tools (Codex, Cursor,
Aider) that look for `AGENTS.md` read the same content Claude sessions do. There is no
separate AGENTS.md content to keep in sync anymore.

---

## What this is

TinBoker (聽播客) — Taiwanese stock & podcast intelligence platform. Monorepo:

- `frontend/` — React 19 + TypeScript + Vite → Cloudflare Pages (`tinboker.com`)
- `backend/` — FastAPI (Python 3.12) API → Docker on Netcup VPS (`api.tinboker.com`)
- `pipelines/` — content tier: podcast + news ingestion → transcribe, summarize, ticker
  sentiment, wiki graph. uv workspace; serves `/api/wiki` + `/api/podcast` on `:8003`.
  **Content/infra only — never build UI here.**
- `mcp-servers/` — agent tooling (`stock-translations`, `article-authoring`)
- Data: SQLite (dev) / Cloud SQL Postgres (staging+prod) · Redis cache · Firestore
  (`graphfolio-db`) · Google OAuth → JWT
- External APIs: Massive (US stocks), FinMind (TW stocks), Spotify + Tavily (pipelines)

## How to operate (AI sessions — read before working)

- `docs/ai-ops/10-model-dispatch.md` — **before spawning subagents or any repo-wide
  scan.** Core rule: the main conversation dispatches; bulk reading/search/research goes
  to subagents that return conclusions + `file:line` only.
- `docs/ai-ops/20-judgment-rubrics.md` — when unsure whether to escalate a model, declare
  done, ask the user, or change approach.
- `docs/ai-ops/30-delegation-templates.md` — copy-paste prompts for delegating search /
  implementation / refactor / research / review.
- `docs/ai-ops/40-maintenance-protocol.md` — **before editing this file or anything in
  `docs/ai-ops/`.**
- `docs/ai-ops/00-diagnosis.md` — why these rules exist; read once per long project.
- Never mark a task done without the evidence listed in rubric R2 (tests/build output,
  read-back, or health check). Self-review of your own diff is not verification.

## Read-first map (trigger → canonical file)

| Working on | Read first |
|---|---|
| Episodes, podcasts, comments, news content | `docs/agents/podcast-domain.md` |
| TW/US market data, charts, prices, translations | `docs/agents/stock-data.md` |
| Search, suggestions, trending, tags | `docs/agents/search-discovery.md` |
| Knowledge graph, design system, PWA visuals | `docs/agents/graph-visuals.md` |
| Auth, user, admin dashboard, dev portal | `docs/agents/auth-admin.md` |
| VPS, Docker, Caddy, CI/CD, Redis, env vars, cache TTLs, secrets | `docs/infra-runbook.md` (ops detail) + `docs/agents/devops-infra.md` (map) |
| Deploy / release / tag / rollback | `docs/workflows/deploy-flow.md` |
| QA, bug repro, smoke suite, browser dev-bypass | `docs/workflows/qa-flow.md` + `docs/agents/qa-tester.md` |
| Firestore schema or data change | `docs/workflows/firestore-data-change.md` + `docs/firestore-contract.md` (shared contract) |
| Anything under `pipelines/` | `pipelines/AGENTS.md` (+ `pipelines/docs/wiki-schema.md`) |
| Syndication to 方格子 / Substack (publishing, covers, account settings) | `docs/workflows/syndication-setup.md` |
| Parallel agents / git worktrees | `docs/workflows/parallel-agents.md` |
| Python style & backend file map | `backend/AGENTS.md` |
| UI conventions, zh-TW localization, icons, TS style | `frontend/AGENTS.md` |
| Product/engineering task tracking (TODO.md, TKB- IDs) | `docs/workflows/task-management.md` |

Tool wrappers (all thin pointers to the docs above): `.claude/agents/`, `.claude/skills/`,
`.codex/agents/`, `.cursor/rules/`, `.agents/skills/`.

## Quick commands

```bash
# backend
cd backend && uv sync && docker compose up -d redis
python -m src.main              # dev server localhost:5174
pytest tests/ -v                # tests (more invocations: backend/AGENTS.md)
ruff check src/                 # lint

# frontend
cd frontend && npm install
npm run dev                     # localhost:5173
npm run build && npm run lint   # required green before any merge

# pipelines (uv workspace — NEVER pip install here)
cd pipelines && uv sync
cd services/podcast && python main.py --config podcasts_tw.json
uv run --package tinboker-podcast pytest
```

## Environments

| Env | Frontend | API | Port | Deployed by |
|-----|----------|-----|------|-------------|
| Local | localhost:5173 | localhost:5174 | 5174 | manual |
| Dev | dev.tinboker.com | dev-api.tinboker.com | 8001 | merge to `develop` |
| Staging | staging.tinboker.com | staging-api.tinboker.com | 8002 | merge to `main` |
| Production | tinboker.com | api.tinboker.com | 8000 | tag `v*` on `main` |

VPS `152.53.136.182` (Netcup, Debian 13), Caddy reverse proxy.
GCP project `gen-lang-client-0901363254` (Secret Manager, Firestore `graphfolio-db`,
GCS `graphfolio-articles`, Cloud SQL `34.14.119.47:5432/podcast_db`).

## Deployment — non-negotiables

1. **Never deploy to the VPS via SSH/rsync.** Git → PR → CI/CD only. Read-only SSH
   (`docker ps`, `docker logs`) is allowed.
2. Branches: `feat|fix/<name>` from `develop`; `hotfix/<name>` from `main`; there is no
   staging branch (staging = HEAD of `main`).
3. `develop` → dev · `main` → staging · `v*` tag on `main` → production.
4. A release is not done until **both** CI runs are green AND
   `curl https://api.tinboker.com/health` returns `"status":"healthy"`.
5. Full step-by-step procedure, verification, CDN purge, and tag-rollback recipe:
   `docs/workflows/deploy-flow.md` — open it and follow it whenever releasing.

## Do Not (hard rules)

- Commit `.env` files, `gcp-service-account.json`, or secrets. **Never write a secret or
  token value into any repo file, doc, commit message, or chat transcript** — reference
  the GCP Secret Manager name instead.
- Deploy directly to the VPS outside CI/CD.
- Use `@app.on_event("startup")` (deprecated) — use the lifespan pattern.
- Add `continue-on-error: true` to CI test jobs.
- Hardcode financial values (OHLC, P/E) in frontend components.
- Use `time.sleep()` in async code — `await asyncio.sleep()`.
- Build UI in `pipelines/`.
- Add new Firestore-direct read paths — reads are consolidating onto VPS Postgres + HTTP API.
- Run `pip install` in `pipelines/` — uv workspace, use `uv sync`.
- Trust a "known issue" without reproducing it against current code first
  (`docs/workflows/qa-flow.md`).

## Style — one line each, detail in the tier guides

- Python: type-hinted, async endpoints, Pydantic v2, cache_get→compute→cache_set —
  `backend/AGENTS.md`.
- TypeScript: Zod-validated API responses, Zustand state, no `any` —
  `frontend/AGENTS.md` § Code conventions.
- **Repo artifacts are written in English**: commit messages, PR titles and bodies,
  issue titles and bodies, code comments, and docs. This holds regardless of the
  language the session is being conducted in — chat with the user may be zh-TW, the
  artifact still is not. User-facing product copy is the exception and stays zh-TW
  (`frontend/AGENTS.md` § Traditional Chinese (zh-TW) Localization; podcast summaries
  and social copy are zh-TW by design).

## Env vars & release scoping

Canonical env-var reference (backend + frontend + release-scoping flags
`RELEASE_PODCAST_LANGUAGES` / `RELEASE_EPISODE_MAX_AGE_DAYS`): `docs/infra-runbook.md`
Part 6. Never copy values here.
