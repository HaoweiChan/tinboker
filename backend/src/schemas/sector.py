"""Pydantic response schemas for the sector/theme episode-discovery endpoint."""
from typing import List, Optional

from pydantic import BaseModel


class SectorResolvedTicker(BaseModel):
    ticker: str
    name: str
    name_en: Optional[str] = None
    market: str
    source: str


class EpisodesBySectorResponse(BaseModel):
    exposure_id: str
    display_name: str
    exposure_type: str
    resolved_tickers: List[SectorResolvedTicker]
    episodes: List[dict]
    total: int


class SectorListItem(BaseModel):
    exposure_id: str
    display_name: str
    exposure_type: str
    count: int


class SectorsListResponse(BaseModel):
    sectors: List[SectorListItem]


# ── Sector board (hot sectors) ───────────────────────────────────────────────

class SectorBoardMember(BaseModel):
    ticker: str
    name: str
    change_percent: Optional[float] = None


class SectorBoardItem(BaseModel):
    exposure_id: str
    display_name: str
    exposure_type: str
    episode_count: int
    avg_change: Optional[float] = None
    hotness: float
    members: List[SectorBoardMember]


class SectorBoardResponse(BaseModel):
    sectors: List[SectorBoardItem]
