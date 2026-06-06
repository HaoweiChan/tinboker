"""Step 5e: trigger the platform to post the new episode to Threads (best-effort).

After the episode (with its social_cards + image URLs) is written to Firestore, ping the
platform's publish endpoint so the new episode fans out to Threads immediately. The
platform reads Firestore, composes the carousel + reply chain, and self-guards with its
idempotency ledger + recency window — so this trigger is safe to fire on every fresh run.

Only fires on a fresh, full run (not reruns/backfills) and only when the episode actually
has social cards. Opt-in + non-fatal: a no-op unless TINBOKER_PLATFORM_API_URL +
TINBOKER_SOCIAL_TOKEN are set, and any failure is logged without aborting the pipeline.
"""

from __future__ import annotations

from ..config import PipelineConfig
from ..episode_data import EpisodeData
from ..service_container import ServiceContainer


def trigger_social_publish(
    config: PipelineConfig,
    services: ServiceContainer,
    episode_data: EpisodeData,
) -> None:
    """Best-effort POST to the platform to publish the new episode to Threads."""
    # Reruns/backfills re-process existing episodes — don't re-fan them to Threads.
    if config.rerun_from is not None:
        return
    summary_result = episode_data.summary_result
    if not summary_result or not summary_result.get("social_cards"):
        return

    try:
        from shared.platform_client import trigger_threads_publish
        result = trigger_threads_publish(limit=5, dry_run=False)
    except Exception as e:
        print(f"  ⚠ Threads publish trigger skipped: {e}")
        return

    if result:
        print(
            f"  ✓ Threads publish triggered "
            f"(posted={result.get('posted_count', 0)}, dry_run={result.get('dry_run')})"
        )
