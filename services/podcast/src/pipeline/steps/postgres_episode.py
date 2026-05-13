"""Step 5c: Mirror the episode record into Postgres on the VPS.

Runs after the Firestore upload. Upserts the same episode document into
``<schema>.episodes`` in a Postgres database (``EPISODE_DATABASE_URL``), so the
podcast catalog is consolidated alongside the wiki store and the legacy Firestore
copy. Best-effort — failures here never block the pipeline. When
``EPISODE_DATABASE_URL`` is unset, this step is a no-op.

The row shape matches ``services/podcast/scripts/dump_firestore_to_postgres.py``
(promoted/indexed columns + a ``doc`` JSONB with the full Firestore document), and
the primary key is the same Firestore-style episode id, so this writer and that
one-shot mirror are interchangeable / idempotent.
"""

from __future__ import annotations

import datetime as dt
import os

from ..config import PipelineConfig
from ..episode_data import EpisodeData
from ..service_container import ServiceContainer

_SCHEMA = os.getenv("EPISODE_DATABASE_SCHEMA", "firestore_mirror")

_DDL = f"""
CREATE SCHEMA IF NOT EXISTS "{_SCHEMA}";
CREATE TABLE IF NOT EXISTS "{_SCHEMA}".episodes (
    episode_id      text PRIMARY KEY,
    podcast_name    text,
    episode_number  integer,
    episode_title   text,
    created_time    timestamptz,
    num_likes       integer,
    number_click    integer,
    related_tickers jsonb,
    doc             jsonb NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_fm_episodes_created
    ON "{_SCHEMA}".episodes (created_time DESC);
CREATE INDEX IF NOT EXISTS ix_fm_episodes_podcast
    ON "{_SCHEMA}".episodes (podcast_name);
CREATE INDEX IF NOT EXISTS ix_fm_episodes_number
    ON "{_SCHEMA}".episodes (podcast_name, episode_number);
CREATE INDEX IF NOT EXISTS ix_fm_episodes_doc
    ON "{_SCHEMA}".episodes USING gin (doc);
"""

_UPSERT = f"""
INSERT INTO "{_SCHEMA}".episodes
    (episode_id, podcast_name, episode_number, episode_title, created_time,
     num_likes, number_click, related_tickers, doc)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (episode_id) DO UPDATE SET
    podcast_name    = EXCLUDED.podcast_name,
    episode_number  = EXCLUDED.episode_number,
    episode_title   = EXCLUDED.episode_title,
    created_time    = EXCLUDED.created_time,
    num_likes       = EXCLUDED.num_likes,
    number_click    = EXCLUDED.number_click,
    related_tickers = EXCLUDED.related_tickers,
    doc             = EXCLUDED.doc
"""


def _as_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def mirror_episode_to_postgres(
    config: PipelineConfig,
    services: ServiceContainer,
    episode_data: EpisodeData,
) -> None:
    """Upsert the episode into Postgres (best-effort; no-op without EPISODE_DATABASE_URL)."""
    if config.rerun_from not in (None, "download", "transcribe", "summarize", "upload"):
        return
    url = os.getenv("EPISODE_DATABASE_URL")
    if not url:
        return

    episode = getattr(episode_data, "episode", None)
    if episode is None:
        return  # the Firestore step builds it; nothing to mirror if it didn't run
    if not getattr(services, "firebase_service", None):
        print("  ⚠ Postgres episode mirror skipped — no firebase service to derive the episode id")
        return

    try:
        import psycopg
        from psycopg.types.json import Jsonb
    except ImportError:
        print("  ⚠ psycopg not available — skipping Postgres episode mirror")
        return

    try:
        podcast_name = episode_data.podcast_name or episode.podcast_name or ""
        episode_id = services.firebase_service._generate_episode_id(podcast_name, episode)
        doc = episode.to_firestore_dict()
        doc["episode_id"] = episode_id

        created = episode.created_time
        if isinstance(created, str):
            try:
                created = dt.datetime.fromisoformat(created.replace("Z", "+00:00"))
            except ValueError:
                created = None

        with psycopg.connect(url, autocommit=True) as conn, conn.cursor() as cur:
            cur.execute(_DDL)
            cur.execute(
                _UPSERT,
                (
                    episode_id,
                    podcast_name or None,
                    _as_int(episode.episode_number),
                    episode.episode_title,
                    created,
                    _as_int(episode.num_likes) or 0,
                    _as_int(episode.number_click) or 0,
                    Jsonb(list(episode.related_tickers or [])),
                    Jsonb(doc),
                ),
            )
        print(f"  ✓ Mirrored to Postgres: {_SCHEMA}.episodes/{episode_id}")
    except Exception as e:  # noqa: BLE001 — best-effort
        import traceback

        print(f"  ⚠ Postgres episode mirror failed (non-fatal): {e}")
        traceback.print_exc()
