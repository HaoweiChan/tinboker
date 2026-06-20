"""Serve-time lookup for "why this ticker belongs to a sector/theme".

The reasons are authored in the pipelines tier (Tavily discovery + an LLM
one-liner) and live on each member of the compiled
``pipelines/libs/shared/src/shared/data/sector_and_theme_universe.json``. Because
the backend does not depend on the pipelines package, that data is mirrored here as
a compact ``{exposure_id: {TICKER: reason}}`` map. Both the universe field and this
mirror are (re)written together by
``pipelines/libs/shared/scripts/generate_sector_reasons.py --apply``.

Lookups are case-insensitive on the ticker and tolerant of a market suffix
(``2330`` and ``2330.TW`` resolve to the same entry).
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

_DATA_FILE = Path(__file__).resolve().parent / "sector_reasons.json"


@lru_cache(maxsize=1)
def _reasons() -> dict[str, dict[str, str]]:
    """Load and index the reasons map (``{exposure_id: {BARE_TICKER: reason}}``)."""
    try:
        raw = json.loads(_DATA_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except Exception as exc:  # noqa: BLE001 — never let bad data break the page
        logger.warning("sector_reasons: could not load %s: %s", _DATA_FILE, exc)
        return {}
    out: dict[str, dict[str, str]] = {}
    for eid, members in (raw or {}).items():
        if not isinstance(members, dict):
            continue
        bucket = out.setdefault(str(eid), {})
        for ticker, reason in members.items():
            bare = str(ticker).strip().upper().split(".")[0]
            if bare and isinstance(reason, str) and reason.strip():
                bucket[bare] = reason.strip()
    return out


def reason_for(exposure_id: str, ticker: str) -> str | None:
    """Return the sector-relationship reason for a ticker, or ``None``."""
    bare = str(ticker or "").strip().upper().split(".")[0]
    if not bare:
        return None
    return _reasons().get(str(exposure_id), {}).get(bare)
