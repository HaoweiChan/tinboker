# tinboker-agents — Development Guide

## Purpose & scope

`tinboker-agents` is the **content / infrastructure backend** for **TinBoker「聽播客」** —
a financial-podcast-summary product. It does three things:

1. **Ingest** — pull podcast episodes (Spotify RSS).
2. **Derive structured content** — transcribe, summarize, extract tickers + sentiment, build
   the entity / topic knowledge graph, generate slides + infographics.
3. **Serve it** — expose that content (and content-derived aggregates) over HTTP
   (`/api/podcast/*`, `/api/wiki/*` on the podcast service, port 8003) and a Postgres store, so
   the **TinBoker webui** can render it.

**The TinBoker webui (the React/Traditional-Chinese site) lives in a SEPARATE "platform" repo —
not here.** Do not build UI in this repo. User accounts, follows, saved episodes, comments,
notification preferences, and live market quotes (prices / `change` %) are the platform repo's
concern, not ours. When a frontend mockup is referenced, treat it as a spec for the data
contracts this repo must expose, and build/extend API endpoints — never React components.
Keep this repo functional/infra-only and content-agnostic.

## Repo overview

This monorepo uses **uv workspaces** to manage two Python packages:
- `services/podcast/` — podcast processing pipeline + the HTTP API (`/api/podcast`, `/api/wiki`)
- `libs/shared/` — shared utilities (secrets, GCS, config, `wiki_builder`)

> A third package, `services/knowledge_graph/` (Tavily news → entity/relation extraction → JSON
> graph store → SVG infographics, deployed to Cloud Run), was **retired in May 2026** — the Cloud
> Run service was unused and its output was never wired into `/api/wiki`. The last in-progress
> state is parked on the `archive/knowledge-graph-refactor` branch. The wiki's entity/topic pages
> still exist — they come from the podcast pipeline's ticker/tag extraction (`ingest_episode`),
> not from the (now removed) news pipeline.

**Wiki content lives in a Postgres database on the VPS, not in this repo.** The `wiki_builder`
library (`libs/shared`) and the `/api/wiki` routes on the podcast service are content-agnostic
infra — see [docs/wiki-schema.md](docs/wiki-schema.md). A `wiki/` dir may exist locally as a
one-time migration source; it is gitignored and never committed.

## Module map

| Path | Purpose | Entry point | Key files |
|------|---------|-------------|-----------|
| [services/podcast/](services/podcast/) | Download → transcribe → summarize → Firestore; serves `/api/wiki` | [main.py](services/podcast/main.py) | [podcasts_to_download.json](services/podcast/podcasts_to_download.json) |
| [libs/shared/](libs/shared/) | Secrets, GCS, config, wiki_builder (Postgres-backed) | N/A (library) | [src/shared/](libs/shared/src/shared/) |
| Wiki content | Postgres DB on the VPS (`WIKI_DATABASE_URL`) | `/api/wiki` (podcast service) | [docs/wiki-schema.md](docs/wiki-schema.md) |

## Decision tree — which module to touch?

**Adding a new podcast source or tweaking download:**
- Modify [services/podcast/podcasts_to_download.json](services/podcast/podcasts_to_download.json)

**Tweaking summary/extraction prompts:**
- Content prompts: [services/podcast/src/podcast/content_builder/prompts/](services/podcast/src/podcast/content_builder/prompts/)

**Working on the wiki (content store):**
- Schema + API: [docs/wiki-schema.md](docs/wiki-schema.md)
- Library: [libs/shared/src/shared/wiki_builder/](libs/shared/src/shared/wiki_builder/) (`WikiRepository`, `ingest_episode`)
- HTTP routes: [services/podcast/src/routers/wiki.py](services/podcast/src/routers/wiki.py)
- Keep this layer content-agnostic — content metadata is opaque JSONB `frontmatter`

**Deploying to production:**
- See [docs/MIGRATION.md](docs/MIGRATION.md)
- podcast/ runs on Netcup VPS via systemd (also hosts the wiki Postgres)
- Plan to consolidate Firestore + GCS onto the VPS: [docs/data-consolidation-plan.md](docs/data-consolidation-plan.md)

## Conventions

**Dependencies:**
- Managed via uv workspaces; root `pyproject.toml` defines members
- Each service has its own `pyproject.toml`
- Shared library is a workspace dependency (`tinboker-shared`)
- Run `uv sync` from repo root to install all deps

**Testing:**
- Add tests in each module's `tests/` directory
- Run `pytest` from within the module directory, or use `uv run`
- Use mocks for external APIs (Spotify, Gemini, Firestore, GCS, AssemblyAI/Groq)

**Commits:**
- Keep module changes atomic; PR per feature or fix
- No generated artifacts in commits (infographics, cache, logs)

**Code organization:**
- Podcast pipeline: `services/podcast/src/podcast/` — cli, orchestrator, firestore_reprocessor
- Podcast internals: `services/podcast/src/pipeline/`, `src/service/`, `src/summarize/`
- Content builder: `services/podcast/src/podcast/content_builder/` — LangGraph pipeline
- Shared: `libs/shared/src/shared/` — secrets, gcs, config, wiki_builder

## Don't

- **Do not build UI here.** The TinBoker webui is a separate platform repo. This repo serves data, not React.
- **Do not run `pip install` from repo root.** Use `uv sync` instead.
- **Do not put generated artifacts under git.** Infographics, cached articles, logs go in `.gitignore`.
- **Do not commit wiki content.** The wiki lives in Postgres on the VPS; `wiki_builder` is infra only.
- **Do not own users/follows/comments/quotes.** Those belong to the platform repo; here, just expose stable IDs (episode/entity/topic slug, show name).
- **Do not bypass `secrets.bootstrap()`.** Always call it before reading env vars.

## Pipelines at a glance

### Podcast pipeline
```
Spotify RSS → services/podcast/download → transcribe → summarize
  → content_builder.run_pipeline() → markdown + slides
  → wiki_builder.ingest_episode() → Postgres (via WikiRepository)
  → Upload MP3, transcript, summary → GCS + Firestore
```

## Related docs

- **[README.md](README.md)** — repo overview, architecture, quickstart
- **[AGENTS.md](AGENTS.md)** — short purpose statement (cross-tool agents entry point)
- **[docs/wiki-schema.md](docs/wiki-schema.md)** — wiki Postgres schema + `/api/wiki` API
- **[docs/content-api-roadmap.md](docs/content-api-roadmap.md)** — what the TinBoker webui needs from this backend, and the plan to deliver it
- **[docs/MIGRATION.md](docs/MIGRATION.md)** — production deployment runbook
- **[docs/content/](docs/content/)** — content/feature notes; **[docs/legacy/](docs/legacy/)** — archived Dify configs
