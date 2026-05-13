# AGENTS.md

> Cross-tool agent entry point. The full guide is **[CLAUDE.md](CLAUDE.md)** — read it.

## What this repo is

`tinboker-agents` is the **content / infrastructure backend** for **TinBoker「聽播客」**, a
financial-podcast-summary product. It:

1. **Ingests** podcast episodes (Spotify RSS).
2. **Derives structured content** — transcribes, summarizes, extracts tickers + sentiment, builds
   the entity / topic knowledge graph, generates slides and infographics.
3. **Serves it** over HTTP (`/api/podcast/*`, `/api/wiki/*` on the podcast service, port 8003) and
   a Postgres store, so the TinBoker webui can render it.

## What this repo is NOT

- **Not the webui.** The TinBoker React/Traditional-Chinese site lives in a **separate "platform"
  repo**. Do not build UI here. If you're handed a frontend mockup, treat it as a spec for the
  data contracts this backend must expose — build/extend API endpoints, not React components.
- **Not the system of record for users / follows / saved episodes / comments / notification prefs**,
  or for **live market quotes** (prices, `change` %). Those belong to the platform repo. This repo
  exposes stable IDs (episode/entity/topic slug, show name) for the platform to reference.

## Layout (uv workspace)

- `services/podcast/` — podcast pipeline (download → transcribe → summarize → upload) **and** the
  HTTP API (`/api/podcast`, `/api/wiki`, `/api/episodes`); FastAPI `app.py`. Includes the LangGraph
  `content_builder` (`src/podcast/content_builder/`) and the Marp Flask service (`src/podcast/marp_service/`).
- `libs/shared/` — secrets bootstrap (GSM + dotenv), GCS client, config, `wiki_builder` (the
  content-agnostic `WikiRepository` over Postgres + `ingest_episode` + markdown views).

> A `services/knowledge_graph/` module (Tavily news → entity extraction → JSON graph store → SVG
> infographics, Cloud Run) was retired in May 2026 — unused, never wired into `/api/wiki`. WIP is
> parked on the `archive/knowledge-graph-refactor` branch.

## Key facts

- Wiki content (episode/entity/topic/supply-chain pages) is in **Postgres on the VPS**, written via
  `shared.wiki_builder` and the `/api/wiki` routes — never committed. Schema: [docs/wiki-schema.md](docs/wiki-schema.md).
- Deps via **uv workspaces** (`uv sync`); secrets via `secrets.bootstrap()` (Google Secret Manager).
- `services/podcast` runs on a Netcup VPS (systemd, port 8003) which also hosts the wiki Postgres.
  Deployment: [docs/MIGRATION.md](docs/MIGRATION.md). Data-consolidation plan (moving Firestore +
  GCS onto the VPS): [docs/data-consolidation-plan.md](docs/data-consolidation-plan.md).
- Roadmap of backend work the webui needs: [docs/content-api-roadmap.md](docs/content-api-roadmap.md).
