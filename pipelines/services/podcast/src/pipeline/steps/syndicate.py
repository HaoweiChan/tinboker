"""Step 5f: stage the new episode's summary on 方格子 and Substack (best-effort).

Deliberately separate from the platform's own Threads/Facebook posting (which runs on
its own TW slot schedule, see ``SOCIAL_PUBLISH_SLOTS``): that fans short social copy out,
this one republishes the whole article. Different content, different platforms, different
enable switch — sharing one flag would mean turning on subscriber-facing posts to enable
a Threads post, or the reverse.

**Off by default**, behind ``SYNDICATE_AUTOPUBLISH``. Without it this is a no-op.

What "on" means, per platform:

- **方格子** — a draft, unless ``SYNDICATE_VOCUS_PUBLISH`` is also set. Publishing there is
  reversible and mails nobody, so auto-publishing is a reasonable choice; it is still
  opt-in because it puts writing in front of strangers without a human reading it first.
- **Substack** — a draft, unless ``SYNDICATE_SUBSTACK_PUBLISH`` is set. Publishing there
  goes to the **web only**: the publisher hard-wires ``send_email: false`` and exposes no
  parameter to change it, so no combination of flags can mail the subscriber list. A
  web-only post can be taken down; a newsletter cannot be recalled.

Unlike the Threads trigger this is **not idempotent on the platform side**: each call
creates new drafts. Two guards keep that from turning into duplicates:

- the platform records every syndicated episode in the shared ``social_posts`` ledger,
  so a second call for the same episode is refused there — including one from a
  *different environment*, which is how the three duplicate pairs on vocus happened
  (one copy carries an ``api.tinboker.com`` cover, its twin ``staging-api``);
- this step never fires on a rerun, where the whole back catalogue would go out again.

It also refuses episodes older than ``SYNDICATE_MAX_AGE_DAYS`` (7 by default; 0 turns
the gate off). Ingest pulls the last 10 episodes per show and walks backwards through
the archive, so ~50 of the ~60 episodes it touches each day are years old — every one a
first-time syndication the ledger has no reason to stop, and 44 posts a day on a
publication nobody asked to flood. Recency is the only thing separating "today's
episode" from "2021's".
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Optional

from ..config import PipelineConfig
from ..episode_data import EpisodeData
from ..service_container import ServiceContainer

_AUTOPUBLISH_ENV = "SYNDICATE_AUTOPUBLISH"
_VOCUS_PUBLISH_ENV = "SYNDICATE_VOCUS_PUBLISH"
_SUBSTACK_PUBLISH_ENV = "SYNDICATE_SUBSTACK_PUBLISH"
_MAX_AGE_ENV = "SYNDICATE_MAX_AGE_DAYS"
_DEFAULT_MAX_AGE_DAYS = 7
_TRUTHY = {"1", "true", "yes", "on"}


def _enabled(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in _TRUTHY


def _max_age_days() -> int:
    """Days of grace before an episode is too old to syndicate. 0 disables the gate."""
    try:
        return max(0, int(os.environ.get(_MAX_AGE_ENV, "").strip() or _DEFAULT_MAX_AGE_DAYS))
    except ValueError:
        return _DEFAULT_MAX_AGE_DAYS


def _released_ms(episode_data: EpisodeData) -> Optional[int]:
    """The episode's true publish time, in Unix ms.

    Same chain as ``ticker_insights_export``: the persisted model first (step 5 has
    already run, so it is there), then Spotify's release datetime, then the ingest
    timestamp. Deliberately no ``now()`` fallback — that would date every episode to
    the run and wave the whole back catalogue through the gate below.
    """
    episode = getattr(episode_data, "episode", None)
    if episode is not None:
        ms = episode.resolved_publish_ms()
        if ms:
            return ms
    for value in (
        (episode_data.spotify_metadata or {}).get("release_datetime"),
        episode_data.created_time,
    ):
        if isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            return int(value.timestamp() * 1000)
    return None


def trigger_syndicate(
    config: PipelineConfig,
    services: ServiceContainer,
    episode_data: EpisodeData,
) -> None:
    """Best-effort POST asking the platform to syndicate this episode's summary."""
    # Reruns/backfills re-process existing episodes; syndicating again would duplicate
    # posts, because the platform creates a fresh draft on every call.
    if config.rerun_from is not None:
        return

    max_age = _max_age_days()
    if max_age:
        released_ms = _released_ms(episode_data)
        if released_ms is None:
            # Unknown age is not "new". Publishing is public and irreversible; a wrong
            # skip costs one article that the admin Social page can still stage by hand.
            print("  ⏸ Syndication skipped: no publish time on this episode")
            return
        age_days = (datetime.now(timezone.utc).timestamp() * 1000 - released_ms) / 86_400_000
        if age_days > max_age:
            print(f"  ⏸ Syndication skipped: episode is {age_days:.0f} days old "
                  f"(> {_MAX_AGE_ENV}={max_age})")
            return

    summary_result = episode_data.summary_result or {}
    # The pipeline's summary_result carries the text as summary_text (see summarize.py /
    # gcs_upload.py); markdown_report/summary_content appear on other paths. Same
    # fallback chain as utils.build_podcast_episode — checking only one key here once
    # made this step silently skip every episode.
    summary_text = (
        summary_result.get("markdown_report")
        or summary_result.get("summary_content")
        or summary_result.get("summary_text")
        or ""
    )
    if not summary_text.strip():
        print("  ⚠ Syndication skipped: episode has no summary text")
        return

    episode_id = getattr(episode_data, "episode_id", None) or summary_result.get("episode_id")
    if not episode_id:
        print("  ⚠ Syndication skipped: no episode id on this run")
        return

    if not _enabled(_AUTOPUBLISH_ENV):
        print(f"  ⏸ Syndication off ({_AUTOPUBLISH_ENV} unset) — stage it from the admin Social page")
        return

    try:
        from shared.platform_client import trigger_syndication
        result = trigger_syndication(
            episode_id,
            publish_vocus=_enabled(_VOCUS_PUBLISH_ENV),
            publish_substack=_enabled(_SUBSTACK_PUBLISH_ENV),
        )
    except Exception as e:  # noqa: BLE001 — ingestion must not fail over syndication
        print(f"  ⚠ Syndication trigger skipped: {e}")
        return

    if not result:
        # None means "disabled or failed"; the client already printed the reason.
        return

    for name, outcome in (result.get("platforms") or {}).items():
        if outcome.get("posted"):
            print(f"  ✓ {name}: {outcome.get('url')}")
        else:
            # Reported per platform rather than as one pass/fail: one target failing
            # says nothing about the other, and a silent skip here means an episode
            # nobody notices was never published.
            print(f"  ⚠ {name} not staged: {outcome.get('reason', 'unknown')}")
