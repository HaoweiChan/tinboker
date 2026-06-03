"""HTTP client for the TinBoker platform config API (the followed-source registry).

The platform (tinboker-platform) owns the operator-maintained follow-list of podcast
shows and news feeds; this pulls the active rows at pipeline start so the agents no
longer depend on the local ``podcasts_*.json`` / ``feeds.json`` (kept as an offline
fallback).

Opt-in by design: a network call happens ONLY when ``TINBOKER_PLATFORM_API_URL`` is
set. When it is unset (tests, local dev, or a deploy that hasn't been switched over)
every function returns ``None`` immediately, so callers transparently fall back to the
committed local config. Read-only, short-timeout, stdlib-only — no new dependency on
``shared``.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


def platform_base_url() -> str | None:
    """The platform API base URL, or ``None`` when the platform pull is disabled."""
    base = os.environ.get("TINBOKER_PLATFORM_API_URL")
    return base.rstrip("/") if base else None


def fetch_sources(source_type: str, *, timeout: float = 10.0) -> list[dict[str, Any]] | None:
    """Return active sources of ``source_type`` (``"podcast"`` | ``"news"``).

    ``GET {base}/api/sources?type=<source_type>&active=true`` → the response's ``items``
    list. Returns ``None`` (never raises) when the pull is disabled or any error occurs,
    so the caller can fall back to local config.
    """
    base = platform_base_url()
    if not base:
        return None
    query = urllib.parse.urlencode({"type": source_type, "active": "true"})
    url = f"{base}/api/sources?{query}"
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if getattr(resp, "status", 200) != 200:
                return None
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
        print(
            f"Warning: platform /api/sources?type={source_type} unavailable "
            f"({exc}); falling back to local config"
        )
        return None
    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        return None
    return items
