"""Step 5: persist the episode record into Postgres — the canonical content store.

Since P4 (contract § 11.5) this is the ONLY episode write: the Firestore
``episodes/{id}`` doc write and the ``tags/{slug}/episodes`` /
``tickers/{t}/episodes`` fan-outs are gone (the fan-outs were pure derivations of
the doc's ``tags`` / ``related_tickers`` arrays, which the backend now queries
straight out of the mirror's JSONB — contract § 11.1). The schema is still named
``firestore_mirror`` so nothing downstream has to be renamed.

The row shape matches ``services/podcast/scripts/dump_firestore_to_postgres.py``
(promoted/indexed columns + a ``doc`` JSONB with the full document), and the PK
is the same Firestore-style episode id, so this writer and that one-shot import
stay interchangeable / idempotent.

NOT best-effort: a missing ``EPISODE_DATABASE_URL`` or any write failure raises
and fails the pipeline run for this episode. There is no second store to fall
back on, and the mirror is also the dedup authority (``get_episode_by_fields``
etc.) plus the backend notification producer's high-water mark.

Re-ingest semantics reproduce what Firestore's ``set(..., merge=True)`` used to
give for free — see ``_merge_onto_stored``.
"""

from __future__ import annotations

import datetime as dt
import os

import psycopg
from psycopg.types.json import Jsonb
from shared.db import libpq_url

from src.podcast.exporters.postgres_mirror import DDL_EPISODES_MIRROR_INDEXES
from src.podcast.exporters.postgres_mirror import SCHEMA as _SCHEMA

from ..config import PipelineConfig
from ..episode_data import EpisodeData
from ..service_container import ServiceContainer
from ..utils import create_episode_object

_DDL = f"""
CREATE SCHEMA IF NOT EXISTS "{_SCHEMA}";
CREATE TABLE IF NOT EXISTS "{_SCHEMA}".episodes (
    episode_id      text PRIMARY KEY,
    podcast_name    text,
    episode_number  integer,
    episode_title   text,
    created_time    timestamptz,
    first_seen_at   timestamptz NOT NULL DEFAULT now(),
    num_likes       integer,
    number_click    integer,
    related_tickers jsonb,
    doc             jsonb NOT NULL
);
ALTER TABLE "{_SCHEMA}".episodes
    ADD COLUMN IF NOT EXISTS first_seen_at timestamptz NOT NULL DEFAULT now();
CREATE INDEX IF NOT EXISTS ix_fm_episodes_created
    ON "{_SCHEMA}".episodes (created_time DESC);
CREATE INDEX IF NOT EXISTS ix_fm_episodes_first_seen
    ON "{_SCHEMA}".episodes (first_seen_at);
CREATE INDEX IF NOT EXISTS ix_fm_episodes_podcast
    ON "{_SCHEMA}".episodes (podcast_name);
CREATE INDEX IF NOT EXISTS ix_fm_episodes_number
    ON "{_SCHEMA}".episodes (podcast_name, episode_number);
CREATE INDEX IF NOT EXISTS ix_fm_episodes_doc
    ON "{_SCHEMA}".episodes USING gin (doc);
""" + DDL_EPISODES_MIRROR_INDEXES

_SELECT_STORED = f"""
SELECT doc FROM "{_SCHEMA}".episodes WHERE episode_id = %s FOR UPDATE
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
    num_likes       = EXCLUDED.num_likes,
    number_click    = EXCLUDED.number_click,
    related_tickers = EXCLUDED.related_tickers,
    doc             = EXCLUDED.doc
"""
# created_time is deliberately NOT in the DO UPDATE set — contract § 2.1: it's
# immutable after first write. A re-ingest of an already-stored episode must
# never advance it (the notification producer's high-water mark reads it).
# first_seen_at is likewise never inserted nor updated here: the DB default
# stamps it exactly once on the first insert, giving the backend notification
# producer a monotonic ingestion-order key (contract § 6.3). A re-ingest must
# never advance either. It is a COLUMN, not a doc field — `_merge_onto_stored`
# and the doc build must stay unaware of it.
# The `doc` column IS fully replaced, but `_merge_onto_stored` has already folded
# the stored document into the incoming one by then, so nothing is lost.

# Doc keys the platform owns and the pipeline must never clobber (contract § 2.3
# #3 for the modified_* quad; social_thread/social_cards[].image_url are written
# by the admin Social page; num_likes/number_click are user counters that
# ``create_episode_object`` always rebuilds as 0). A stored value survives unless
# this run produced a non-empty one of its own — so a genuine regeneration of the
# social cards still lands, while a run that produced none keeps the platform's.
_PLATFORM_OWNED_KEYS = (
    "modified_summary_url",
    "modified_summary_content",
    "modified_by",
    "modified_at",
    "social_thread",
    "social_cards",
    "retracted_at",
    "num_likes",
    "number_click",
)


def _as_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_datetime(value):
    if isinstance(value, str):
        try:
            return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return value


def _merge_onto_stored(incoming: dict, stored: dict) -> dict:
    """Fold ``incoming`` onto the stored document, Firestore ``merge=True``-style.

    1. Stored keys this run didn't produce survive (that's what ``merge=True``
       did; the plain ``doc = EXCLUDED.doc`` upsert alone would drop them).
    2. ``created_time`` is immutable once written (contract § 2.1).
    3. Platform-owned keys keep the stored value unless this run carries a
       non-empty replacement — see ``_PLATFORM_OWNED_KEYS``.
    4. An empty ``podcast_name`` never overwrites a stored one.
    """
    doc = {**stored, **incoming}
    # Key presence, not truthiness: a stored created_time of None/"" must still
    # win. Falling back to the incoming value would re-stamp it with ingestion
    # now(), lifting the episode over the notification producer's high-water mark
    # and re-firing "new episode" for the whole back-catalogue.
    doc["created_time"] = (
        stored["created_time"] if "created_time" in stored else incoming.get("created_time")
    )
    for key in _PLATFORM_OWNED_KEYS:
        if not incoming.get(key) and stored.get(key) is not None:
            doc[key] = stored[key]
    if not incoming.get("podcast_name") and stored.get("podcast_name"):
        doc["podcast_name"] = stored["podcast_name"]
    return doc


def persist_episode(
    config: PipelineConfig,
    services: ServiceContainer,
    episode_data: EpisodeData,
) -> None:
    """Build the episode document and upsert it into Postgres.

    Raises on a missing ``EPISODE_DATABASE_URL`` or any write failure so the run
    fails visibly instead of silently losing the episode. ``process_episode``'s
    outer try/except turns that into a failed episode, same as any other step.
    """
    if config.rerun_from not in (None, "download", "transcribe", "summarize", "upload"):
        return

    if not services.firebase_service:
        print("  ⚠ Warning: episode-id service not available, skipping episode persist")
        return
    if not episode_data.gcs_urls:
        print("  ⚠ Warning: GCS URLs not available, skipping episode persist")
        return

    episode_title = episode_data.api_data.get("title", "Untitled Episode")
    print(f"  📝 Persisting episode: {episode_title}")

    episode = create_episode_object(
        episode_data=episode_data,
        gcs_urls=episode_data.gcs_urls,
        spotify_metadata=episode_data.spotify_metadata,
        summary_result=episode_data.summary_result,
    )
    # Stamp the canonical tag list BEFORE building the doc dict, so
    # ``episodes.doc.tags`` (contract § 2.1: always present, may be empty) and any
    # later consumer of ``to_firestore_dict()`` see the same vocabulary-filtered
    # slugs. Single normalization boundary — see ``_normalize_tags``.
    from src.service.upload_to_firebase import _normalize_tags

    episode.tags = _normalize_tags(episode_data.tags)
    episode_data.episode = episode

    url = os.getenv("EPISODE_DATABASE_URL")
    if not url:
        raise RuntimeError(
            "EPISODE_DATABASE_URL is not set — cannot persist the episode. "
            "Postgres is the only content store since P4; check secrets_bootstrap."
        )

    podcast_name = episode_data.podcast_name or episode.podcast_name or ""
    episode_id = services.firebase_service._generate_episode_id(podcast_name, episode)
    doc = episode.to_firestore_dict()
    doc["episode_id"] = episode_id
    if not doc.get("podcast_name") and podcast_name:
        doc["podcast_name"] = podcast_name

    # DDL first, on its OWN autocommit connection. CREATE INDEX IF NOT EXISTS takes
    # a ShareLock held until commit, so running it inside the write transaction
    # below would have it queue behind (and deadlock with) the backend's
    # patch_episode_doc row lock and any concurrent persist.
    with psycopg.connect(libpq_url(url), autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(_DDL)

    with psycopg.connect(libpq_url(url)) as conn, conn.cursor() as cur:
        cur.execute(_SELECT_STORED, (episode_id,))
        stored = cur.fetchone()
        if stored:
            print(f"  🔄 Updating existing episode: {episode_id}")
            doc = _merge_onto_stored(doc, stored[0] or {})
        else:
            print(f"  ✨ Creating new episode: {episode_id}")
            doc.setdefault("retracted_at", None)
        cur.execute(
            _UPSERT,
            (
                episode_id,
                doc.get("podcast_name") or None,
                _as_int(doc.get("episode_number")),
                doc.get("episode_title"),
                _as_datetime(doc.get("created_time")),
                _as_int(doc.get("num_likes")) or 0,
                _as_int(doc.get("number_click")) or 0,
                Jsonb(list(doc.get("related_tickers") or [])),
                Jsonb(doc),
            ),
        )
    print(f"  ✓ Persisted episode: {_SCHEMA}.episodes/{episode_id}")
