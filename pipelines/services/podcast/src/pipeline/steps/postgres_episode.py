"""Step 5c: Mirror the episode record into Postgres on the VPS.

Runs after the Firestore upload. Upserts the same episode document into
``<schema>.episodes`` in a Postgres database (``EPISODE_DATABASE_URL``), so the
podcast catalog is consolidated alongside the wiki store and the legacy Firestore
copy.

NOT best-effort: the mirror is the P2 dedup authority (``get_episode_by_fields``
etc. read only the mirror now) and the backend notification producer's
high-water mark reads it too, so a mirror write that silently failed would
leave both invisibly wrong. A missing ``EPISODE_DATABASE_URL`` or any write
failure raises and fails the pipeline run for this episode instead.

The row shape matches ``services/podcast/scripts/dump_firestore_to_postgres.py``
(promoted/indexed columns + a ``doc`` JSONB with the full Firestore document), and
the primary key is the same Firestore-style episode id, so this writer and that
one-shot mirror are interchangeable / idempotent. ``created_time`` is excluded
from the ON CONFLICT update (contract § 2.1: immutable after first write) so a
re-ingest can never advance it and re-fire "new episode" notifications.
"""

from __future__ import annotations

import datetime as dt
import os

import psycopg
from psycopg.types.json import Jsonb

from src.podcast.exporters.postgres_mirror import DDL_EPISODES_MIRROR_INDEXES
from src.podcast.exporters.postgres_mirror import SCHEMA as _SCHEMA

from ..config import PipelineConfig
from ..episode_data import EpisodeData
from ..service_container import ServiceContainer

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
""" + DDL_EPISODES_MIRROR_INDEXES

_UPSERT = f"""
INSERT INTO "{_SCHEMA}".episodes
    (episode_id, podcast_name, episode_number, episode_title, created_time,
     num_likes, number_click, related_tickers, doc)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (episode_id) DO UPDATE SET
    podcast_name    = EXCLUDED.podcast_name,
    episode_number  = EXCLUDED.episode_number,
    episode_title   = EXCLUDED.episode_title,
    num_likes       = EXCLUDED.num_likes,
    number_click    = EXCLUDED.number_click,
    related_tickers = EXCLUDED.related_tickers,
    doc             = EXCLUDED.doc
"""
# created_time is deliberately NOT in the DO UPDATE set — contract § 2.1: it's
# immutable after first write. A re-ingest of an already-mirrored episode must
# never advance it (the notification producer's high-water mark reads it).


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
    """Upsert the episode into Postgres.

    NOT best-effort (see module docstring) — raises on a missing
    ``EPISODE_DATABASE_URL`` or any write failure so the run fails visibly
    instead of leaving the dedup/notification-authoritative mirror silently
    stale. ``process_episode``'s outer try/except turns that into a failed
    episode, same as any other step's raised error.
    """
    if config.rerun_from not in (None, "download", "transcribe", "summarize", "upload"):
        return

    episode = getattr(episode_data, "episode", None)
    if episode is None:
        return  # the Firestore step builds it; nothing to mirror if it didn't run
    if not getattr(services, "firebase_service", None):
        print("  ⚠ Postgres episode mirror skipped — no firebase service to derive the episode id")
        return

    url = os.getenv("EPISODE_DATABASE_URL")
    if not url:
        raise RuntimeError(
            "EPISODE_DATABASE_URL is not set — cannot mirror episode to Postgres. "
            "The mirror is the P2 dedup/notification authority; check secrets_bootstrap."
        )

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
