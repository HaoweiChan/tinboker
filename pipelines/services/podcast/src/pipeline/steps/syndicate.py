"""Step 5f: stage the new episode's summary on 方格子 and Substack (best-effort).

Sibling of :mod:`social_publish`, and deliberately separate: that step fans short social
copy out to Threads/Facebook, this one republishes the whole article. Different content,
different platforms, different enable switch — sharing one flag would mean turning on
subscriber-facing posts to enable a Threads post, or the reverse.

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
creates new drafts. So it fires once, for the episode just ingested, and never on
reruns/backfills.
"""

from __future__ import annotations

import os

from ..config import PipelineConfig
from ..episode_data import EpisodeData
from ..service_container import ServiceContainer

_AUTOPUBLISH_ENV = "SYNDICATE_AUTOPUBLISH"
_VOCUS_PUBLISH_ENV = "SYNDICATE_VOCUS_PUBLISH"
_SUBSTACK_PUBLISH_ENV = "SYNDICATE_SUBSTACK_PUBLISH"
_TRUTHY = {"1", "true", "yes", "on"}


def _enabled(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in _TRUTHY


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
