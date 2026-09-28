# TinBoker backend

FastAPI API for TinBoker's stock data, search, content, accounts, billing, and
admin tools. The web app is in [`frontend/`](../frontend/); podcast and news
ingestion are in [`pipelines/`](../pipelines/).

## Runtime

- Python 3.12; dependencies are managed by `backend/pyproject.toml` and `uv.lock`.
- The deployed API runs in Docker on the Netcup VPS. Dev, staging, and production
  share one PostgreSQL instance (`podcast_db`); Redis caches API work. Content
  pipelines populate the PostgreSQL content store. Media files are served from
  the VPS disk through Caddy.
- Google OAuth signs users in; the backend issues JWTs. GCP is used for Secret
  Manager, not application data storage.
- Market data comes from Massive (US) and FinMind (TW).

The current deployment topology and environment variable reference are in
[`docs/infra-runbook.md`](../docs/infra-runbook.md). Follow the
[`deploy flow`](../docs/workflows/deploy-flow.md) for releases; do not deploy by
copying files or restarting VPS services manually.

## Local development

From the repository root:

```bash
cd backend
uv sync
docker compose up -d redis
uv run python -m src.main
```

The API defaults to `http://localhost:5174`; its health endpoint is `/health`
and its generated API reference is `/docs`. Local development defaults to SQLite
at `backend/data/tinboker.db`; the server initializes local tables on startup.
The checked-in compose file is for local Redis and optional local PostgreSQL,
not a deployment stack. If you need PostgreSQL locally, start both services with
`docker compose up -d` and configure `USE_POSTGRES` and a local connection in
`backend/.env`. Keep credentials out of git. Do not point a local cache or database
maintenance command at the shared VPS services.

## Checks

Run from `backend/`:

```bash
uv run pytest tests/ -v
ruff check src/
```

For an isolated test group or marker, see [`AGENTS.md`](AGENTS.md). API routes and
schemas are generated from the running app at `/docs`; use that reference when
checking a request or response rather than copying an old example.

## Where to look

| Area | Source |
|---|---|
| App lifespan and route registration | `src/main.py` |
| Settings and secret loading | `src/config.py`, `src/config_loader.py` |
| Database connection and models | `src/database/` |
| HTTP and WebSocket routes | `src/routers/` |
| Tests | `tests/` |
| Historical design notes and current doc pointers | [`docs/README.md`](docs/README.md) |

The older backend notes include designs for Cloud SQL, Firestore, GCS, and
previous hosting layouts. They are retained as migration history, not setup
instructions.
