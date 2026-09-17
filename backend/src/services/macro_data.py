"""Macro series for the macro card: a registry, a keyless FRED fetch, a lazy refresh.

FRED serves any series as CSV without an API key
(``fredgraph.csv?id=DGS10&cosd=2025-01-01``). That is the whole integration — no SDK, no
key to rotate. Series ids here are OURS (what the macro extractor emits, what URLs
carry); ``fred`` is the mapping, so a source can change without breaking a stored mention.

Refresh is lazy: a read older than ``STALE_HOURS`` re-pulls that one series. ponytail:
no scheduler — add a loop only if a cold card's one extra second ever matters.
"""
from __future__ import annotations

import asyncio
import csv
import io
import logging
import math
from datetime import datetime, timedelta
from typing import Optional

import httpx

from src.database.models import MacroDaily
from src.database.postgres import get_session

logger = logging.getLogger(__name__)

FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv"
HISTORY_DAYS = 800          # pulled on every refresh; the card draws the tail of it
STALE_HOURS = 12

# freq: D daily · W weekly · M monthly — decides the card's span label and default points.
SERIES: dict[str, dict] = {
    "US10Y":       {"fred": "DGS10",        "name": "美債10年期殖利率",   "unit": "%",          "freq": "D"},
    "US2Y":        {"fred": "DGS2",         "name": "美債2年期殖利率",    "unit": "%",          "freq": "D"},
    "US30Y":       {"fred": "DGS30",        "name": "美債30年期殖利率",   "unit": "%",          "freq": "D"},
    "US_REAL10Y":  {"fred": "DFII10",       "name": "美國10年期實質利率", "unit": "%",          "freq": "D"},
    "FED_FUNDS":   {"fred": "DFF",          "name": "聯邦基金利率",       "unit": "%",          "freq": "D"},
    "WTI":         {"fred": "DCOILWTICO",   "name": "WTI原油",            "unit": " 美元/桶",   "freq": "D"},
    "BRENT":       {"fred": "DCOILBRENTEU", "name": "布蘭特原油",         "unit": " 美元/桶",   "freq": "D"},
    "DIESEL_US":   {"fred": "GASDESW",      "name": "美國柴油零售價",     "unit": " 美元/加侖", "freq": "W"},
    "GASOLINE_US": {"fred": "GASREGW",      "name": "美國汽油零售價",     "unit": " 美元/加侖", "freq": "W"},
    "DXY":         {"fred": "DTWEXBGS",     "name": "美元指數（廣義）",   "unit": "",           "freq": "D"},
    "USDJPY":      {"fred": "DEXJPUS",      "name": "美元兌日圓",         "unit": "",           "freq": "D"},
    "USDTWD":      {"fred": "DEXTAUS",      "name": "美元兌台幣",         "unit": "",           "freq": "D"},
    "VIX":         {"fred": "VIXCLS",       "name": "VIX",                "unit": "",           "freq": "D"},
    "US_CPI":      {"fred": "CPIAUCSL",     "name": "美國CPI指數",        "unit": "",           "freq": "M"},
    "US_UNEMP":    {"fred": "UNRATE",       "name": "美國失業率",         "unit": "%",          "freq": "M"},
}
DEFAULT_POINTS = {"D": 90, "W": 26, "M": 24}
SPAN_LABEL = {"D": "個交易日", "W": "週", "M": "個月"}


def parse_fred_csv(text: str) -> list[tuple[str, float]]:
    """``(date, value)`` rows. FRED marks a missing day with "." — skipped, not zero."""
    rows = []
    for rec in list(csv.reader(io.StringIO(text)))[1:]:
        if len(rec) < 2:
            continue
        try:
            v = float(rec[1])
        except ValueError:
            continue
        if math.isfinite(v):
            rows.append((rec[0], v))
    return rows


async def fetch_fred(fred_id: str, since: str) -> list[tuple[str, float]]:
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        resp = await client.get(FRED_CSV, params={"id": fred_id, "cosd": since})
        resp.raise_for_status()
    return parse_fred_csv(resp.text)


def _latest_write(series_id: str) -> Optional[datetime]:
    for db in get_session():
        row = (db.query(MacroDaily.created_at).filter(MacroDaily.series_id == series_id)
               .order_by(MacroDaily.created_at.desc()).first())
        return row[0] if row else None
    return None


def _replace(series_id: str, since: str, rows: list[tuple[str, float]]) -> None:
    """Swap the window in one transaction: FRED revises, and delete+insert is the upsert
    that behaves the same on Postgres and the SQLite test DB."""
    for db in get_session():
        db.query(MacroDaily).filter(MacroDaily.series_id == series_id, MacroDaily.date >= since).delete()
        db.add_all([MacroDaily(series_id=series_id, date=d, value=v) for d, v in rows])
        db.commit()


async def ensure_fresh(series_id: str, now: Optional[datetime] = None) -> None:
    """Re-pull the series when the last write is older than ``STALE_HOURS``. A fetch
    failure keeps whatever is stored — a day-old card beats a 502."""
    now = now or datetime.utcnow()
    last = await asyncio.to_thread(_latest_write, series_id)
    if last and now - last < timedelta(hours=STALE_HOURS):
        return
    since = (now - timedelta(days=HISTORY_DAYS)).strftime("%Y-%m-%d")
    try:
        rows = await fetch_fred(SERIES[series_id]["fred"], since)
    except Exception as e:  # noqa: BLE001
        logger.warning("macro: FRED fetch failed for %s: %s", series_id, e)
        return
    if rows:
        await asyncio.to_thread(_replace, series_id, since, rows)


def points(series_id: str, n: int) -> list[tuple[str, float]]:
    """The last ``n`` observations, oldest first. Sync — call under ``asyncio.to_thread``."""
    for db in get_session():
        rows = (db.query(MacroDaily.date, MacroDaily.value).filter(MacroDaily.series_id == series_id)
                .order_by(MacroDaily.date.desc()).limit(n).all())
        return [(d, v) for d, v in reversed(rows)]
    return []
