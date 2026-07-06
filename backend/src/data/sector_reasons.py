"""Serve-time lookup for "why this ticker belongs to a sector/theme".

Reasons now live on ``tag_registry.members`` in Postgres. The loader keeps the old
single-entry cache behavior and is explicitly invalidated after taxonomy publishes
or admin member edits.

Lookups are case-insensitive on the ticker and tolerant of a market suffix
(``2330`` and ``2330.TW`` resolve to the same entry).
"""
from __future__ import annotations

import logging
from functools import lru_cache

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _reasons() -> dict[str, dict[str, str]]:
    """Load and index ``{exposure_id: {BARE_TICKER: reason}}`` from tag_registry."""
    from src.database import postgres
    from src.database.models import TagRegistry

    try:
        if postgres.SessionLocal is None:
            postgres.init_engine()
        db = postgres.SessionLocal()
        try:
            rows = (
                db.query(TagRegistry)
                .filter(TagRegistry.kind == "sector", TagRegistry.redirect_to.is_(None))
                .all()
            )
        finally:
            db.close()
    except Exception as exc:  # noqa: BLE001 - never let bad data break the page
        logger.warning("sector_reasons: could not query TagRegistry: %s", exc)
        return {}

    out: dict[str, dict[str, str]] = {}
    for row in rows:
        eid = str(row.exposure_id or "")
        if not eid:
            continue
        bucket = out.setdefault(str(eid), {})
        for member in row.members or []:
            ticker = (member or {}).get("ticker")
            reason = (member or {}).get("reason")
            bare = str(ticker or "").strip().upper().split(".")[0]
            if bare and isinstance(reason, str) and reason.strip():
                bucket[bare] = reason.strip()
    return out


def invalidate_reasons_cache() -> None:
    """Clear the registry-backed reasons cache after taxonomy writes."""
    _reasons.cache_clear()


def reason_for(exposure_id: str, ticker: str) -> str | None:
    """Return the sector-relationship reason for a ticker, or ``None``."""
    bare = str(ticker or "").strip().upper().split(".")[0]
    if not bare:
        return None
    return _reasons().get(str(exposure_id), {}).get(bare)
