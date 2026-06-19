"""Step 5e: trigger the platform to post the new episode to Threads (best-effort).

After the episode (with its social_cards + image URLs) is written to Firestore, ping the
platform's publish endpoint so the new episode fans out to Threads immediately. The
platform reads Firestore, composes the carousel + reply chain, and self-guards with its
idempotency ledger + recency window — so this trigger is safe to fire on every fresh run.

**Off by default.** The brand reviews + edits each episode's copy on the admin Social
page and publishes from there (per-episode, to Threads + Facebook). Auto-publish is
therefore opt-in behind ``SOCIAL_AUTOPUBLISH`` — without it, this step is a no-op and
nothing posts on ingest. Even when enabled it only fires on a fresh, full run (not
reruns/backfills) and only when the episode actually has social cards, and it additionally
needs TINBOKER_PLATFORM_API_URL + TINBOKER_SOCIAL_TOKEN. Any failure is logged without
aborting the pipeline.
"""

from __future__ import annotations

import os

from ..config import PipelineConfig
from ..episode_data import EpisodeData
from ..service_container import ServiceContainer

_AUTOPUBLISH_ENV = "SOCIAL_AUTOPUBLISH"
_TRUTHY = {"1", "true", "yes", "on"}


def _autopublish_enabled() -> bool:
    return os.environ.get(_AUTOPUBLISH_ENV, "").strip().lower() in _TRUTHY


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

    # Manual-publish is the default: the brand publishes from the admin Social page.
    if not _autopublish_enabled():
        print(f"  ⏸ Threads auto-publish off ({_AUTOPUBLISH_ENV} unset) — publish from the admin Social page")
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
