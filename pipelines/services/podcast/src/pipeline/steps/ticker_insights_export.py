"""Step 5d: dual-write per-ticker insight documents to Firestore.

Writes ``ticker_insights/{episode_id}/tickers/{ticker}`` per the platform
contract in ``docs/firestore-contract.md`` § 4. During Phase B cutover this
step runs after the Postgres mirror so new episodes have both the legacy row
copy and the composite Firestore docs. Best-effort — failures are logged but do
not abort the rest of the pipeline.
"""

from __future__ import annotations

import os

from ..config import PipelineConfig
from ..episode_data import EpisodeData
from ..service_container import ServiceContainer


def _mirror_ticker_insights_to_postgres(episode_id: str, docs: dict) -> None:
    """Best-effort dual-write of the same ticker-insight docs into
    ``firestore_mirror.ticker_insights`` (Postgres). No-op without
    ``EPISODE_DATABASE_URL`` — mirrors the guard in ``pipeline.steps.postgres_episode``.
    """
    if not docs:
        return
    url = os.getenv("EPISODE_DATABASE_URL")
    if not url:
        return
    try:
        import psycopg
    except ImportError:
        print("  ⚠ psycopg not available — skipping Postgres ticker_insights mirror")
        return

    from src.podcast.exporters import postgres_mirror

    try:
        with psycopg.connect(url, autocommit=True) as conn, conn.cursor() as cur:
            cur.execute(postgres_mirror.DDL_TICKER_INSIGHTS)
            n = postgres_mirror.upsert_ticker_insights(cur, episode_id, docs)
        print(f"  ✓ Mirrored {n} ticker_insights docs to Postgres: {postgres_mirror.SCHEMA}.ticker_insights")
    except Exception as e:  # noqa: BLE001 — best-effort
        import traceback

        print(f"  ⚠ Postgres ticker_insights mirror failed (non-fatal): {e}")
        traceback.print_exc()


def export_ticker_insights(
    config: PipelineConfig,
    services: ServiceContainer,
    episode_data: EpisodeData,
) -> None:
    """Translate pipeline ticker insights into spec docs and persist them."""
    # Skip on the validate-only rerun mode and any future no-write modes.
    should_export = config.rerun_from in [
        None, "download", "transcribe", "summarize", "upload"
    ]
    if not should_export:
        return
    if not episode_data.summary_result:
        return
    if not services.firebase_service:
        return

    raw_payload = episode_data.summary_result.get("ticker_insights")
    if not raw_payload:
        return

    if not episode_data.episode_id:
        print("  ⚠ Ticker insights export skipped: missing episode_id")
        return

    from src.podcast.exporters.ticker_insights import (
        build_episode_insight_docs,
        write_episode_insights,
    )

    # The insight's mention date MUST equal the episode doc's released_at_ms — the
    # value /picks measures forward 7/30/90D returns from. Source it from the uploaded
    # PodcastEpisode, the same model + resolver that wrote released_at_ms, so the two
    # can never diverge. (The old `getattr(episode_data, "released_at_ms")` was dead:
    # the pipeline EpisodeData has no such field, so it silently fell through to
    # `created_time` — itself often unset on back-catalogue reprocessing — and then to
    # `_iso_utc(None)` → now(), collapsing whole back-catalogues onto the run date.)
    launch_time = None
    episode_model = getattr(episode_data, "episode", None)
    if episode_model is not None:
        launch_time = episode_model.resolved_publish_ms()
    if launch_time is None and episode_data.spotify_metadata:
        launch_time = episode_data.spotify_metadata.get("release_datetime")
    if launch_time is None:
        launch_time = episode_data.created_time

    docs = build_episode_insight_docs(
        raw_payload=raw_payload,
        episode_id=episode_data.episode_id,
        podcaster=episode_data.podcast_name or "",
        podcast_launch_time=launch_time,
    )
    if not docs:
        return

    try:
        written = write_episode_insights(
            services.firebase_service.db,
            episode_id=episode_data.episode_id,
            docs=docs,
        )
        print(f"  ✓ Wrote {written} ticker_insights docs for {episode_data.episode_id}")
    except Exception as e:
        import traceback

        print(f"  ⚠ Ticker insights export failed (non-fatal): {e}")
        traceback.print_exc()

    # Dual-write the same docs into the Postgres mirror (best-effort, independent of
    # the Firestore outcome above so a mirror-only reader stays fresh either way).
    _mirror_ticker_insights_to_postgres(episode_data.episode_id, docs)
