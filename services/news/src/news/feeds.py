"""Load the RSS feed list from ``feeds.json`` (git-committed, user-editable)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# feeds.json sits at the package root: services/news/feeds.json
DEFAULT_FEEDS_PATH = Path(__file__).resolve().parents[2] / "feeds.json"


def load_feeds(path: str | Path | None = None) -> list[dict[str, Any]]:
    """Return the enabled feed entries from ``feeds.json``.

    Each entry is a dict with ``name``, ``url`` and (optionally) ``region`` /
    ``enabled``. Entries with ``enabled: false`` are dropped.
    """
    feeds_path = Path(path) if path else DEFAULT_FEEDS_PATH
    data = json.loads(feeds_path.read_text(encoding="utf-8"))
    feeds = data.get("feeds", []) if isinstance(data, dict) else []
    return [f for f in feeds if isinstance(f, dict) and f.get("url") and f.get("enabled", True)]
