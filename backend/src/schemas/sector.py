"""Pydantic response schemas for the sector/theme episode-discovery endpoint."""
from typing import Dict, List, Optional

from pydantic import BaseModel


class SectorResolvedTicker(BaseModel):
    ticker: str
    name: str
    name_en: Optional[str] = None
    market: str
    source: str
    # Short zh-TW explanation of how this ticker relates to the sector/theme
    # (Tavily-discovered, LLM-authored). Absent when no reason is on file.
    reason: Optional[str] = None


class EpisodesBySectorResponse(BaseModel):
    exposure_id: str
    display_name: str
    exposure_type: str
    # Display visuals (lucide icon name + accent color) from the compiled universe.
    icon_id: Optional[str] = None
    color_hex: Optional[str] = None
    resolved_tickers: List[SectorResolvedTicker]
    episodes: List[dict]
    total: int


class SectorListItem(BaseModel):
    exposure_id: str
    display_name: str
    exposure_type: str
    icon_id: Optional[str] = None
    color_hex: Optional[str] = None
    count: int


class SectorsListResponse(BaseModel):
    sectors: List[SectorListItem]


# ── Sector board (hot sectors) ───────────────────────────────────────────────

class SectorBoardMember(BaseModel):
    ticker: str
    name: str
    change_percent: Optional[float] = None
    series: List[float] = []


class SectorBoardItem(BaseModel):
    exposure_id: str
    display_name: str
    exposure_type: str
    icon_id: Optional[str] = None
    color_hex: Optional[str] = None
    episode_count: int
    heat: Optional[float] = None  # recency-weighted discussion (Σ 0.5^(age_days/H))
    avg_change: Optional[float] = None
    hotness: float
    members: List[SectorBoardMember]
    series: List[float] = []


class SectorBoardResponse(BaseModel):
    sectors: List[SectorBoardItem]


# ── Exposure performance (bubble chart, /topics) ─────────────────────────────
# One unified row for both themes and industries (split client-side by exposure_type):
# X = discussion heat, Y = avg member % change, bubble size = aggregate trading value.
# market_cap_twd is only meaningful for industries (TW-only via FinMind); null for themes.

class ExposurePerformanceItem(BaseModel):
    exposure_id: str
    exposure_type: str
    display_name: str
    color_hex: Optional[str] = None
    episode_count: int = 0
    heat: Optional[float] = None               # recency-weighted discussion (X axis)
    return_pct: Optional[float] = None         # avg member daily % change
    market_cap_twd: Optional[float] = None     # aggregate constituent market cap (industries only)
    trading_value_twd: Optional[float] = None  # aggregate constituent daily trade value (NT$)
    trading_value_windows_twd: Optional[Dict[str, float]] = None


class ExposurePerformanceResponse(BaseModel):
    exposures: List[ExposurePerformanceItem]
