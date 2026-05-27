# Ticker Insights Postgres — Handoff to tinboker-agents

**Date:** 2026-05-27
**From:** tinboker-platform
**To:** tinboker-agents (Podcast-Downloader / content-builder writers)
**Status:** action required before reads return data

---

## TL;DR

The Postgres container the platform was reading from (`docker-db_postgres-1`, hosted inside the Dify stack) is gone. We've spun up a dedicated `tinboker-postgres` container in the platform compose and renamed the table the platform reads from `ticker_recommendations` → `ticker_insights` (matching the naming you already use in `tinboker_wiki`). **Your writers need to repoint at the new DB and write to the new table name** before `/api/recommendations/*` and `/api/ticker-insights/*` will surface anything.

---

## What changed on the platform side

| Before | After |
|---|---|
| `POSTGRES_HOST=docker-db_postgres-1` (Dify container, gone since ~2026-04-25) | `POSTGRES_HOST=postgres` → service `tinboker-postgres` in `app_default` network |
| Plaintext `POSTGRES_PASSWORD` committed in `backend/docker-compose.*.yml` | Loaded from GSM secret `POSTGRES_PASSWORD`; backend reads via `config_loader.py`, Postgres container reads via CI-injected env (no disk) |
| Reads from table `ticker_recommendations` (in `podcast_db`) | Reads from table `ticker_insights` (in `podcast_db`) |
| `recommendation_db.py` Python module, separate `recommendation_postgres_*` Settings fields | Renamed to `insight_db.py`; shares main `settings.postgres_connection_string` |

Branch: `feat/postgres-restoration` (6 commits). Will deploy to dev once merged.

---

## Connection details for your writers

Once the platform branch is deployed to dev/staging/prod, the new container is reachable as:

| Setting | Value |
|---|---|
| Host (from within `app_default` docker network) | `postgres` (DNS) — same as how the backend reaches it |
| Host (from outside the docker network, on the VPS) | `127.0.0.1:5432` (port-published) |
| Database | `podcast_db` |
| User | `podcast_user` |
| Password | GSM secret `POSTGRES_PASSWORD` (project `gen-lang-client-0901363254`) |
| Image | `postgres:16-alpine` |
| Volume | `postgres-data` (persistent) |

If your writers run as containers on the same VPS, attach them to the `app_default` external network and use the service name `postgres`. If they run elsewhere (Podcast-Downloader cron on a different host), expose 5432 via SSH tunnel or extend the docker compose to publish externally — we currently bind to `127.0.0.1` only.

---

## Table schema you need to write to

```sql
CREATE TABLE ticker_insights (
    id                     SERIAL PRIMARY KEY,
    episode_id             TEXT,
    podcaster              TEXT,
    podcast_launch_time    TIMESTAMP,
    ticker                 TEXT NOT NULL,
    bluf_thesis            TEXT,
    time_horizon           TEXT,
    sentiment_score        DOUBLE PRECISION,
    sentiment              TEXT,
    reasons                JSONB,
    risks                  JSONB,
    created_at             TIMESTAMP DEFAULT NOW()
);

CREATE INDEX ON ticker_insights (ticker);
CREATE INDEX ON ticker_insights (podcast_launch_time DESC);
CREATE INDEX ON ticker_insights (podcaster);
```

This is the same column shape the platform's `insight_queries.py` reads — verbatim copy of what the legacy `ticker_recommendations` table had, just renamed. If your `tinboker_wiki.ticker_insights` schema is different, we should align before this lands (file an issue or ping the platform side).

---

## What the platform is doing

1. The `tinboker-postgres` service is in the compose files but **comes up empty**. The platform seeds its own `stock_translations` table via `backend/scripts/seed_translations.py` (81 rows) on first deploy.
2. The platform's `insight_queries.py` already issues `SELECT … FROM ticker_insights WHERE …` against this DB.
3. We expose nothing on the public internet — only via the existing FastAPI routers at `/api/recommendations/*` (soft-deprecated) and `/api/ticker-insights/*`.

---

## What we need you to do

1. **Confirm schema match** between platform's `ticker_insights` and the one your writers will produce (column names, types, JSONB shapes for `reasons` / `risks`).
2. **Repoint your writers** (Podcast-Downloader's content pipeline, content-builder, etc.) at `postgres:5432/podcast_db` as user `podcast_user` and write rows into `ticker_insights` instead of `ticker_recommendations`. Password from the same GSM secret.
3. **Decide on old-data migration:**
   - The old `docker-db_postgres-1.podcast_db.ticker_recommendations` (≈2.4k rows per `data-consolidation-plan.md`) is gone with the container. If you have a snapshot/backup of that DB volume, dump and reimport into the new `tinboker-postgres` as `ticker_insights`.
   - If no backup exists, just start fresh — the data was stale anyway (DB has been unreachable since 2026-04-25).
4. **Coordinate timing**: the platform branch deploys to dev first. We can leave a stub so reads return `[]` until your writers catch up, OR you can ship the schema migration on your side first and we deploy after.

---

## Network / firewall notes

- VPS: `152.53.136.182` (Netcup RS 1000 G11)
- Docker network: `app_default` (external)
- Existing containers on `app_default`: `tinboker-backend-{dev,staging,prod}`, `tinboker-redis`, `tinboker-netdata`, `tinboker-postgres` (new)
- Caddy reverse-proxies HTTP/HTTPS but **not** Postgres — no outside-VPS access by design

---

## Open questions for the agents team

1. Where do your writers currently run? (Cron on `Podcast-Downloader/`, or in a container on `app_default`?) — affects whether you can use service-name DNS or need a port mapping.
2. Do you want to keep writing to `tinboker_wiki` (your own Postgres) **and** also write to our `tinboker-postgres`, or consolidate to one?
3. What's the planned HTTP API timeline (per `tinboker-agents/docs/spec-from-platform.md` and the platform's project memory)? If the HTTP API ships within the next sprint, this Postgres handoff is short-lived — we can deprecate direct Postgres reads from the platform once the API is up.
4. Any column-shape divergence we should sort out before this lands?

---

## Platform-side commits for reference

```
12c5cee refactor(db): rename ticker_recommendations table to ticker_insights
a29f524 chore(ci): inject POSTGRES_PASSWORD via GSM, keep VPS disk clean
350bb49 refactor(db): consolidate insight DB onto main postgres connection
e45a509 chore(scripts): refresh seed_translations from prior SQLite snapshot
89d4694 chore(infra): add postgres service, rotate exposed VPS password
7d13738 refactor(db): rename recommendation_db module to insight_db
```

Branch: `tinboker-platform@feat/postgres-restoration`
Contact: Haowei (hwchan42@gmail.com)
