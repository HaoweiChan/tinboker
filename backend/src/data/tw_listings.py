"""Authoritative full TW listing seed, crawled from the official exchange ISIN lists.

``tw_listings.json`` is generated from the TWSE (上市) and TPEx (上櫃/興櫃) public ISIN
registries — https://isin.twse.com.tw/isin/C_public.jsp (strMode=2 / strMode=4) — filtered
to real equities, ETFs, preferred shares, the innovation board, TDRs, and REITs (warrants,
ETNs, and asset-backed securities are dropped). Each entry carries the official ticker,
Traditional-Chinese name, listing board, and industry.

This is the *static, reviewable* counterpart to the runtime FinMind seed: it makes the
``stock_translations`` table authoritative for the whole TW universe straight from the
exchange, with the names version-controlled in git rather than fetched at boot. Seeded as
``auto`` (machine-imported from the exchange) so admin-``approved`` rows always win; the
curated core in ``seed_data.py`` (also ``approved``) is never overwritten.

Refresh: re-run the crawler to regenerate ``tw_listings.json`` (listings change slowly —
new IPOs, delistings, renames). The loader degrades to an empty list if the file is absent.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_DATA_FILE = Path(__file__).resolve().parent / "tw_listings.json"


def _load() -> list[tuple[str, str, str | None, str | None, str]]:
    """Read tw_listings.json into (ticker, market, name_en, name_zh_tw, status) tuples."""
    if not _DATA_FILE.exists():
        logger.warning("tw_listings.json missing — TW exchange seed skipped")
        return []
    try:
        rows = json.loads(_DATA_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("tw_listings.json unreadable: %s", e)
        return []
    out: list[tuple[str, str, str | None, str | None, str]] = []
    for r in rows:
        ticker = (r.get("ticker") or "").strip().upper()
        name = (r.get("name") or "").strip()
        if not ticker or not name:
            continue
        # English name is left None — the exchange list is Chinese-only; Massive/agent
        # backfill can add English later. status="auto" lets approved rows win.
        out.append((ticker, "TW", None, name, "auto"))
    return out


# Full TW listing universe as backfill_translations()-compatible 5-tuples.
TW_LISTINGS: list[tuple[str, str, str | None, str | None, str]] = _load()
