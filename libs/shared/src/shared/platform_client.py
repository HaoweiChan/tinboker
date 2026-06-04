"""HTTP client for the TinBoker platform config API.

The platform (tinboker-platform) owns operator-maintained config — the followed-source
registry (podcast shows + news feeds) and curated ticker aliases. This pulls them at
pipeline start so the agents don't depend on local files alone.

Opt-in by design: a network call happens ONLY when ``TINBOKER_PLATFORM_API_URL`` is
set. When it is unset (tests, local dev, or a deploy that hasn't been switched over)
every function returns ``None`` immediately, so callers fall back to the committed local
config. Read-only, short-timeout, stdlib-only — no new dependency on ``shared``.
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


def _get_items(path: str, *, timeout: float = 10.0, what: str = "data") -> list[dict[str, Any]] | None:
    """GET ``{base}{path}`` and return the response's ``items`` list, or ``None``.

    Returns ``None`` (never raises) when the pull is disabled (no base URL) or on any
    network/parse error, so callers can fall back to local config.
    """
    base = platform_base_url()
    if not base:
        return None
    url = f"{base}{path}"
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if getattr(resp, "status", 200) != 200:
                return None
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
        print(f"Warning: platform {what} unavailable ({exc}); falling back to local config")
        return None
    items = payload.get("items") if isinstance(payload, dict) else None
    return items if isinstance(items, list) else None


def fetch_sources(source_type: str, *, timeout: float = 10.0) -> list[dict[str, Any]] | None:
    """Active sources of ``source_type`` (``"podcast"`` | ``"news"``) from the platform.

    ``GET {base}/api/sources?type=<source_type>&active=true`` → the ``items`` list.
    """
    query = urllib.parse.urlencode({"type": source_type, "active": "true"})
    return _get_items(f"/api/sources?{query}", timeout=timeout, what=f"/api/sources?type={source_type}")


def fetch_translation_aliases(*, timeout: float = 10.0) -> list[dict[str, Any]] | None:
    """Translations that carry curated aliases, for the news alias index.

    ``GET {base}/api/stocks/translations/aliases`` → the ``items`` list, each with
    ``ticker``, ``market``, ``name_en``, ``name_zh_tw`` and ``aliases``.
    """
    return _get_items(
        "/api/stocks/translations/aliases", timeout=timeout, what="/api/stocks/translations/aliases"
    )
