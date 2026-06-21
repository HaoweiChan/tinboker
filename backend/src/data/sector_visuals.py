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

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_DATA_FILE = Path(__file__).resolve().parent / "sector_visuals.json"


@lru_cache(maxsize=1)
def _visuals() -> dict[str, dict[str, str]]:
    """Load the visuals map (``{exposure_id: {icon_id, color_hex}}``)."""
    try:
        raw = json.loads(_DATA_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except Exception as exc:  # noqa: BLE001 — never let bad data break the page
        logger.warning("sector_visuals: could not load %s: %s", _DATA_FILE, exc)
        return {}
    out: dict[str, dict[str, str]] = {}
    for eid, v in (raw or {}).items():
        if not isinstance(v, dict):
            continue
        icon_id = v.get("icon_id")
        color_hex = v.get("color_hex")
        if icon_id or color_hex:
            out[str(eid)] = {
                "icon_id": str(icon_id) if icon_id else None,
                "color_hex": str(color_hex) if color_hex else None,
            }
    return out


def visual_for(exposure_id: str) -> Optional[dict[str, Optional[str]]]:
    """Return ``{"icon_id": ..., "color_hex": ...}`` for an exposure, or ``None``."""
    return _visuals().get(str(exposure_id or ""))
