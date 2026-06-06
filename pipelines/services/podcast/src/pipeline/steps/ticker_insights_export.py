"""Step 5d: Write per-ticker insight documents to Firestore.

Writes ``ticker_insights/{episode_id}/tickers/{ticker}`` per the platform
contract in ``docs/spec-from-platform.md`` § 4. Best-effort — failures are
logged but do not abort the rest of the pipeline.
"""

from __future__ import annotations

from ..config import PipelineConfig
from ..episode_data import EpisodeData
from ..service_container import ServiceContainer


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

    launch_time = None
    if episode_data.spotify_metadata:
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
