"""Serve-time lookup for a sector/theme's display icon + accent color.

The visuals are authored in the pipelines tier (a curated icon_id/color_hex per
exposure) and live on every exposure of the compiled
``pipelines/libs/shared/src/shared/data/sector_and_theme_universe.json``. Because
the backend does not depend on the pipelines package, that data is mirrored here as
a compact ``{exposure_id: {"icon_id": ..., "color_hex": ...}}`` map. Both the
universe field and this mirror are (re)written together by
``pipelines/libs/shared/scripts/generate_sector_visuals.py --apply``.

``icon_id`` is a lucide-react icon name resolved to a component by the frontend
(SectorIcon.tsx). Exposures with no entry simply omit both fields; the frontend
then falls back to a stable hashed-hue chip.
"""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import Optional

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _visuals() -> dict[str, dict[str, str]]:
    """Load the visuals map (``{exposure_id: {icon_id, color_hex}}``) from database."""
    from src.database import postgres
    from src.database.models import TagRegistry
    try:
        if postgres.SessionLocal is None:
            postgres.init_engine()
        db = postgres.SessionLocal()
        try:
            rows = db.query(TagRegistry).filter(TagRegistry.kind == "sector").all()
            out: dict[str, dict[str, str]] = {}
            for r in rows:
                if r.exposure_id and (r.icon_id or r.color_hex):
                    out[r.exposure_id] = {
                        "icon_id": r.icon_id,
                        "color_hex": r.color_hex,
                    }
            return out
        finally:
            db.close()
    except Exception as exc:  # noqa: BLE001 — never let bad data break the page
        logger.warning("sector_visuals: could not query TagRegistry: %s", exc)
        return {}


def visual_for(exposure_id: str) -> Optional[dict[str, Optional[str]]]:
    """Return ``{"icon_id": ..., "color_hex": ...}`` for an exposure, or ``None``."""
    return _visuals().get(str(exposure_id or ""))
