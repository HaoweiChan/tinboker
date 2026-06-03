"""Load the RSS feed list from ``feeds.json`` (git-committed, user-editable)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# feeds.json sits at the package root: services/news/feeds.json
DEFAULT_FEEDS_PATH = Path(__file__).resolve().parents[2] / "feeds.json"


def _load_feeds_from_platform() -> list[dict[str, Any]] | None:
    """Pull active news feeds from the platform /api/sources.

    Returns None when the platform pull is disabled (TINBOKER_PLATFORM_API_URL unset)
    or unavailable, so the caller falls back to the committed feeds.json. Each feed
    carries ``lookback_days`` / ``max_episodes`` for date-window filtering downstream.
    """
    try:
        from shared.platform_client import fetch_sources

        items = fetch_sources("news")
        if not items:
            return None
        feeds = [
            {
                "name": s.get("name"),
                "url": s.get("feed_url"),
                "region": s.get("region"),
                "enabled": True,
                "lookback_days": s.get("lookback_days"),
                "max_episodes": s.get("max_episodes"),
            }
            for s in items
            if s.get("feed_url")
        ]
        if not feeds:
            return None
        print(f"Loaded {len(feeds)} active news feed(s) from platform /api/sources")
        return feeds
    except Exception as e:  # noqa: BLE001 — never let a config pull abort the run
        print(f"Warning: Could not load feeds from platform, falling back to feeds.json: {e}")
        return None


def load_feeds(path: str | Path | None = None) -> list[dict[str, Any]]:
    """Return the enabled feed entries — from the platform when available, else ``feeds.json``.

    Each entry is a dict with ``name``, ``url`` and (optionally) ``region`` /
    ``enabled`` / ``lookback_days`` / ``max_episodes``. Entries with ``enabled: false``
    are dropped. An explicit ``path`` always reads that file (used by tests); the
    platform pull is only attempted for the default (``path is None``) production call.
    """
    if path is None:
        platform_feeds = _load_feeds_from_platform()
        if platform_feeds is not None:
            return platform_feeds
    feeds_path = Path(path) if path else DEFAULT_FEEDS_PATH
    data = json.loads(feeds_path.read_text(encoding="utf-8"))
    feeds = data.get("feeds", []) if isinstance(data, dict) else []
    return [f for f in feeds if isinstance(f, dict) and f.get("url") and f.get("enabled", True)]
