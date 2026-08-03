"""Shared Postgres DDL + upsert SQL for the ``firestore_mirror`` dual-write tables.

One definition, several writers, so the mirror schema can't drift between them:

* ``pipeline.steps.ticker_insights_export`` (live dual-write, per episode run)
* ``scripts/refresh_trending_tickers.py`` (live dual-write, hourly recompute)
* ``podcast.regen.orchestrator.commit`` (regen writes Firestore directly; this
  mirrors the same field updates onto ``episodes.doc``)
* ``scripts/dump_firestore_to_postgres.py`` (one-shot backfill)

Connects with ``EPISODE_DATABASE_URL`` (see ``secrets_bootstrap``). Every DDL
statement is ``IF NOT EXISTS`` so callers can run it on each write — cheap,
self-healing schema, no separate migration step. Same pattern as
``pipeline.steps.postgres_episode`` (the sibling ``episodes`` table owner).
"""

from __future__ import annotations

import os
from typing import Any

SCHEMA = os.getenv("EPISODE_DATABASE_SCHEMA", "firestore_mirror")

DDL_TICKER_INSIGHTS = f"""
CREATE SCHEMA IF NOT EXISTS "{SCHEMA}";
CREATE TABLE IF NOT EXISTS "{SCHEMA}".ticker_insights (
    episode_id text NOT NULL,
    ticker     text NOT NULL,
    doc        jsonb NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (episode_id, ticker)
);
"""

DDL_TRENDING_TICKERS = f"""
CREATE SCHEMA IF NOT EXISTS "{SCHEMA}";
CREATE TABLE IF NOT EXISTS "{SCHEMA}".trending_tickers (
    ticker     text PRIMARY KEY,
    doc        jsonb NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);
"""

# Extra indexes on the existing firestore_mirror.episodes table (owned/created by
# pipeline.steps.postgres_episode) that the backend queries against. No index on
# created_time here: doc->>'created_time' is an ISO string (PodcastEpisode.
# to_firestore_dict() / dump_firestore_to_postgres.py's _jsonable both emit
# .isoformat()), so a ::bigint cast would fail — order by the promoted
# `created_time timestamptz` column instead (already indexed, see
# pipeline.steps.postgres_episode's ix_fm_episodes_created).
DDL_EPISODES_MIRROR_INDEXES = f"""
CREATE INDEX IF NOT EXISTS ix_fm_episodes_doc_tags
    ON "{SCHEMA}".episodes USING gin ((doc->'tags'));
CREATE INDEX IF NOT EXISTS ix_fm_episodes_doc_related_tickers
    ON "{SCHEMA}".episodes USING gin ((doc->'related_tickers'));
"""

_UPSERT_TICKER_INSIGHT = f"""
INSERT INTO "{SCHEMA}".ticker_insights (episode_id, ticker, doc, updated_at)
VALUES (%s, %s, %s, now())
ON CONFLICT (episode_id, ticker) DO UPDATE SET
    doc = EXCLUDED.doc,
    updated_at = now()
"""

_UPSERT_TRENDING_TICKER = f"""
INSERT INTO "{SCHEMA}".trending_tickers (ticker, doc, updated_at)
VALUES (%s, %s, now())
ON CONFLICT (ticker) DO UPDATE SET
    doc = EXCLUDED.doc,
    updated_at = now()
"""

_DELETE_TRENDING_TICKERS_NOT_IN = f"""
DELETE FROM "{SCHEMA}".trending_tickers WHERE NOT (ticker = ANY(%s))
"""

_MERGE_EPISODE_DOC = f"""
UPDATE "{SCHEMA}".episodes
SET doc = doc || %s::jsonb
WHERE episode_id = %s
"""


def upsert_ticker_insights(cur, episode_id: str, docs: dict[str, dict[str, Any]]) -> int:
    """Upsert each ``(episode_id, ticker)`` doc. Caller runs ``DDL_TICKER_INSIGHTS``
    and owns the connection/commit."""
    from psycopg.types.json import Jsonb

    for ticker, doc in docs.items():
        cur.execute(_UPSERT_TICKER_INSIGHT, (episode_id, ticker, Jsonb(doc)))
    return len(docs)


def upsert_trending_tickers(cur, docs: dict[str, dict[str, Any]]) -> int:
    """Upsert each ticker's trending doc. Caller runs ``DDL_TRENDING_TICKERS`` and
    owns the connection/commit."""
    from psycopg.types.json import Jsonb

    for ticker, doc in docs.items():
        cur.execute(_UPSERT_TRENDING_TICKER, (ticker, Jsonb(doc)))
    return len(docs)


def prune_trending_tickers(cur, keep_tickers: list[str]) -> int:
    """Delete rows whose ticker fell out of the recomputed set. Returns rows deleted."""
    cur.execute(_DELETE_TRENDING_TICKERS_NOT_IN, (list(keep_tickers),))
    return cur.rowcount


def merge_episode_doc(cur, episode_id: str, fields: dict[str, Any]) -> bool:
    """Jsonb-merge ``fields`` onto an existing ``episodes.doc`` row (top-level keys
    only — matches the Firestore ``merge=True`` write this mirrors).

    Returns False when the row doesn't exist, so the caller never fabricates a
    partial doc for an episode the mirror never saw.
    """
    from psycopg.types.json import Jsonb

    cur.execute(_MERGE_EPISODE_DOC, (Jsonb(fields), episode_id))
    return cur.rowcount > 0
