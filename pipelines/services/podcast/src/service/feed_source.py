"""Resolve which feed to read for a show — canonical RSS first, mirror fallback.

Both the orchestrator (nightly / ad-hoc runs) and the episode watcher
(10-minute polling) call :func:`fetch_feed_episodes` so a single place decides
the source. A show is read from its canonical RSS feed when one is known —
either an explicit ``rss_url`` on the show dict (future platform field) or the
name→URL map in ``rss_feeds.json`` — otherwise it falls back to the legacy
``podcasttomp3.com`` mirror.

RSS is preferred because the mirror lags real publication by hours, which is why
fresh episodes were not appearing within the watcher's 10-minute cycle. The
mirror remains the fallback so a transient RSS failure cannot stall ingestion
for a show that has no known RSS URL.

Override with ``PODCAST_FEED_SOURCE=mirror`` to force the legacy path for every
show (operational escape hatch).
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

# Imported as a module (not by-name) so test patches of
# ``download_podcasts.fetch_episodes`` / ``extract_podcast_id`` reach this caller
# regardless of import timing.
from src.service import download_podcasts
from src.service.rss_feed import fetch_episodes_from_rss

# services/podcast/rss_feeds.json  (this file is services/podcast/src/service/feed_source.py)
_RSS_FEEDS_PATH = Path(__file__).resolve().parents[2] / "rss_feeds.json"


@lru_cache(maxsize=1)
def _rss_feed_map() -> dict:
    """Canonical-RSS map: show name -> RSS URL. Empty dict when the file is absent."""
    try:
        with open(_RSS_FEEDS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception as e:  # noqa: BLE001 — a malformed map must not break ingestion
        print(f"Warning: could not load {_RSS_FEEDS_PATH.name}: {e}")
        return {}


def resolve_rss_url(show: dict) -> Optional[str]:
    """Return the canonical RSS URL for *show*, or None if none is known."""
    explicit = show.get("rss_url") or show.get("rss_feed_url")
    if explicit:
        return explicit
    return _rss_feed_map().get(show.get("name"))


def fetch_feed_episodes(show: dict) -> list[dict]:
    """Return the show's episodes (newest-first), preferring its canonical RSS.

    Falls back to the podcasttomp3 mirror when no RSS URL is known, when
    ``PODCAST_FEED_SOURCE=mirror`` is set, or when an RSS fetch yields nothing.
    """
    force_mirror = os.environ.get("PODCAST_FEED_SOURCE", "rss").lower() == "mirror"
    rss_url = None if force_mirror else resolve_rss_url(show)

    if rss_url:
        episodes = fetch_episodes_from_rss(rss_url)
        if episodes:
            return episodes
        print(
            f"RSS feed returned no episodes for {show.get('name')}; "
            f"falling back to mirror"
        )

    link = show.get("link") or ""
    if not link:
        return []
    try:
        return download_podcasts.fetch_episodes(download_podcasts.extract_podcast_id(link))
    except ValueError as e:
        print(f"Cannot resolve mirror feed for {show.get('name')}: {e}")
        return []
