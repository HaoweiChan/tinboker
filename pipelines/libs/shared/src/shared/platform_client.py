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

# Cloudflare's bot rules 403 the default `Python-urllib/x.y` User-Agent at the edge.
# Every request this module makes goes through _headers() so the identifying UA is
# set in exactly one place.
USER_AGENT = "tinboker-pipeline/1.0 (+https://tinboker.com)"


def _headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    return {"User-Agent": USER_AGENT, **(extra or {})}


def platform_base_url() -> str | None:
    """The platform API base URL, or ``None`` when the platform pull is disabled."""
    base = os.environ.get("TINBOKER_PLATFORM_API_URL")
    return base.rstrip("/") if base else None


def admin_base_url() -> str | None:
    """Where to send ``/api/admin/*`` calls.

    Production deliberately mounts no admin routers at all — see the
    ``if not settings.is_production`` guard in backend/src/main.py — so
    api.tinboker.com answers 404 for every admin path by design, not by accident. Every
    environment shares one database, so calling staging does exactly the same work to the
    same data while leaving that surface off the public host.

    Falls back to TINBOKER_PLATFORM_API_URL, which is right for local runs against a dev
    backend and wrong (harmlessly, as a 404) if it ever points at production.
    """
    base = os.environ.get("TINBOKER_ADMIN_API_URL") or os.environ.get("TINBOKER_PLATFORM_API_URL")
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
        req = urllib.request.Request(url, headers=_headers({"Accept": "application/json"}))
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


def trigger_threads_publish(
    *, limit: int = 5, dry_run: bool = False, timeout: float = 20.0
) -> dict[str, Any] | None:
    """Ask the platform to post recent episodes to Threads (post-ingest trigger).

    ``POST {base}/api/admin/threads/publish?dry_run=<bool>&limit=<n>`` with the
    ``TINBOKER_SOCIAL_TOKEN`` bearer token. Opt-in: fires only when BOTH
    ``TINBOKER_PLATFORM_API_URL`` and ``TINBOKER_SOCIAL_TOKEN`` are set. Returns the
    platform's JSON response, or ``None`` when disabled / on any error — never raises,
    so it cannot break ingestion. Idempotency + the recency window live on the platform
    side, so repeated/batched triggers are safe.
    """
    base = admin_base_url()
    token = os.environ.get("TINBOKER_SOCIAL_TOKEN")
    if not base or not token:
        return None
    query = urllib.parse.urlencode({"dry_run": str(bool(dry_run)).lower(), "limit": int(limit)})
    url = f"{base}/api/admin/threads/publish?{query}"
    try:
        req = urllib.request.Request(
            url, data=b"", method="POST",
            headers=_headers({"Authorization": f"Bearer {token}", "Accept": "application/json"}),
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if getattr(resp, "status", 200) >= 400:
                return None
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
        print(f"Warning: Threads publish trigger failed ({exc})")
        return None


def trigger_syndication(
    episode_id: str, *, platforms: str = "vocus,substack", publish_vocus: bool = False,
    publish_substack: bool = False, dry_run: bool = False, timeout: float = 60.0,
) -> dict[str, Any] | None:
    """Ask the platform to stage one episode on the long-form syndication targets.

    ``POST {base}/api/admin/threads/episodes/{id}/syndicate`` with the
    ``TINBOKER_SOCIAL_TOKEN`` bearer token, same opt-in rule as
    :func:`trigger_threads_publish`: nothing happens unless both env vars are set.

    Per-episode rather than "recent N" because this is not idempotent on the platform
    side — every call creates a new draft. The caller fires it once, on the episode it
    just ingested.

    ``publish_substack`` publishes to the Substack **web** only — the platform hard-wires
    ``send_email: false`` and offers no way to email subscribers, so this cannot send a
    newsletter no matter how it is called.

    A longer timeout than the Threads trigger: this renders a cover, uploads it, and
    talks to two APIs.
    """
    base = admin_base_url()
    token = os.environ.get("TINBOKER_SOCIAL_TOKEN")
    if not base or not token or not episode_id:
        return None
    query = urllib.parse.urlencode({
        "platforms": platforms,
        "dry_run": str(bool(dry_run)).lower(),
        "publish": str(bool(publish_vocus)).lower(),
        "publish_substack": str(bool(publish_substack)).lower(),
    })
    url = f"{base}/api/admin/threads/episodes/{urllib.parse.quote(episode_id)}/syndicate?{query}"
    try:
        req = urllib.request.Request(
            url, data=b"", method="POST",
            headers=_headers({"Authorization": f"Bearer {token}", "Accept": "application/json"}),
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if getattr(resp, "status", 200) >= 400:
                return None
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
        print(f"Warning: syndication trigger failed ({exc})")
        return None


def fetch_sectors_universe(*, timeout: float = 10.0) -> dict[str, Any] | None:
    """Get full compiled sectors/themes universe from platform API.

    GET {base}/api/sectors/universe -> returns {max_tickers, exposures}
    """
    base = platform_base_url()
    if not base:
        return None
    url = f"{base}/api/sectors/universe"
    try:
        req = urllib.request.Request(url, headers=_headers({"Accept": "application/json"}))
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if getattr(resp, "status", 200) != 200:
                return None
            payload = json.loads(resp.read().decode("utf-8"))
            if isinstance(payload, dict) and "exposures" in payload:
                return payload
    except Exception as exc:
        print(f"Warning: platform sectors universe unavailable ({exc}); falling back to local seed backup")
        return None
    return None

