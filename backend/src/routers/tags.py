"""Tags API router for tag-based episode discovery"""
import asyncio
import json
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.cache.redis_client import cache_get, cache_set
from src.data.sector_reasons import reason_for
from src.database.postgres import get_session
from src.schemas.sector import (
    EpisodesBySectorResponse,
    ExposurePerformanceItem,
    ExposurePerformanceResponse,
    HeatValidationResponse,
    SectorByTickerItem,
    SectorBoardItem,
    SectorBoardMember,
    SectorBoardResponse,
    SectorListItem,
    SectorResolvedTicker,
    SectorsByTickerResponse,
    SectorsListResponse,
)
from src.services.podcast import PodcastService
from src.services.translation_discovery import schedule_ticker_discovery
from src.tag_registry import (
    hidden_offvocab_slugs,
    hidden_sector_exposure_ids,
    served_sector_exposure_ids,
    registry_snapshot,
    seed_if_empty,
)

router = APIRouter(prefix="/api", tags=["tags"])

podcast_service = PodcastService()


class Tag(BaseModel):
    id: str
    name: str
    episode_count: int


class TagsResponse(BaseModel):
    tags: List[Tag]


class TagRegistryEntry(BaseModel):
    slug: str
    display_zh: str
    tier: str


class TagRegistryResponse(BaseModel):
    tags: List[TagRegistryEntry]
    # Normalized slugs of admin-hidden OFF-VOCAB tags. The frontend drops these from
    # episode tag chips so a hidden junk tag (e.g. "TaiwanStocks") stops surfacing there.
    hidden_slugs: List[str] = []


class EpisodePreview(BaseModel):
    id: str
    title: str
    podcast_name: str
    released_at_ms: Optional[int] = None
    key_insights: List[str] = []
    related_tickers: List[str] = []


class TrendingTag(BaseModel):
    id: str
    name: str
    scoped_count: int
    weekly_counts: List[int] = []
    recent_episodes: List[EpisodePreview] = []


class TrendingTagsResponse(BaseModel):
    tags: List[TrendingTag]


class EpisodesByTagResponse(BaseModel):
    tag: str
    episodes: List[dict]
    total: int


@router.get("/tags/registry", response_model=TagRegistryResponse)
async def get_tag_registry(db: Session = Depends(get_session)):
    """Return the tag registry with display names and quality tiers.

    Fetched by the frontend to build topic labels dynamically.
    """
    seed_if_empty(db)
    return TagRegistryResponse(
        tags=[TagRegistryEntry(**e) for e in registry_snapshot(db)],
        hidden_slugs=sorted(hidden_offvocab_slugs(db)),
    )


@router.get("/tags", response_model=TagsResponse)
async def get_tags():
    """Get list of available tags/topics with episode counts from Firestore"""
    try:
        tags = await podcast_service.get_all_tags()
        return TagsResponse(tags=[Tag(**tag) for tag in tags])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching tags: {str(e)}")


@router.get("/tags/trending", response_model=TrendingTagsResponse)
async def get_trending_tags(
    weeks: int = Query(default=6, ge=2, le=12, description="Number of weeks for sparkline data"),
    preview_count: int = Query(default=3, ge=1, le=5, description="Episode previews per tag"),
):
    """Get trending tags with scoped counts, weekly sparkline data, and episode previews."""
    try:
        tags = await podcast_service.get_trending_tags(weeks=weeks, preview_count=preview_count)
        return TrendingTagsResponse(tags=[TrendingTag(**t) for t in tags])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching trending tags: {str(e)}")


@router.get("/episodes/by-tag/{tag}", response_model=EpisodesByTagResponse)
async def get_episodes_by_tag(
    tag: str = Path(..., description="Tag name or ID"),
    limit: int = Query(default=50, ge=1, le=200, description="Maximum number of episodes to return"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
    include_content: bool = Query(default=False, description="Include heavy content fields"),
):
    """Get episodes with a specific tag from Firestore subcollections"""
    try:
        episodes = await podcast_service.get_episodes_by_tag(
            tag=tag, limit=limit, offset=offset, enrich_content=include_content,
        )
        # On-ingest discovery: surface any newly-mentioned ticker as a pending stub +
        # autofill its name (non-blocking, throttled — see translation_discovery). The
        # recent-episodes feed already does this; the topic page reaches tickers the
        # feed may not, so without this their names never resolve.
        schedule_ticker_discovery(episodes)
        episodes_dict = [ep.dict() for ep in episodes]
        return EpisodesByTagResponse(tag=tag, episodes=episodes_dict, total=len(episodes_dict))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching episodes by tag: {str(e)}")


@router.get("/sectors", response_model=SectorsListResponse)
async def list_sectors(db: Session = Depends(get_session)):
    """List all sector/theme exposures that have at least one episode, sorted by episode count.

    Returns a directory of sectors and themes so the frontend /topics page can render
    a browsable sectors listing.  Sectors are only reachable from episode detail pages
    without this endpoint.  Admin-hidden sectors (registry tier='hidden') are excluded.
    """
    try:
        sectors = await podcast_service.list_sectors()
        served = served_sector_exposure_ids(db)
        if served is None:  # bootstrap window: registry empty — fall back to blocklist
            hidden = hidden_sector_exposure_ids(db)
            visible = [s for s in sectors if s.get("exposure_id") not in hidden]
        else:
            visible = [s for s in sectors if s.get("exposure_id") in served]
        return SectorsListResponse(sectors=[SectorListItem(**s) for s in visible])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching sectors: {str(e)}")


@router.get("/sectors/board", response_model=SectorBoardResponse)
async def get_sector_board(db: Session = Depends(get_session)):
    """Return a ranked hot-sectors board with price performance.

    Each sector entry includes its constituent tickers' daily % change,
    an avg_change aggregate, and a blended hotness score (0..1).  Sorted
    by hotness DESC so the most price-active, most-mentioned sectors float
    to the top.  Intended as a richer replacement for the vague tag ranking
    shown on /topics.  Admin-hidden sectors (registry tier='hidden') are excluded
    here (cheap per-request filter) so curation takes effect without busting the
    warm board cache.
    """
    try:
        sectors = await podcast_service.sector_board()
        served = served_sector_exposure_ids(db)
        if served is None:  # bootstrap window: registry empty — fall back to blocklist
            hidden = hidden_sector_exposure_ids(db)
            sectors = [s for s in sectors if s.get("exposure_id") not in hidden]
        else:
            sectors = [s for s in sectors if s.get("exposure_id") in served]
        return SectorBoardResponse(
            sectors=[
                SectorBoardItem(
                    **{k: v for k, v in s.items() if k != "members"},
                    members=[SectorBoardMember(**m) for m in s["members"]],
                )
                for s in sectors
            ]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching sector board: {str(e)}")


@router.get("/sectors/by-ticker/{ticker}", response_model=SectorsByTickerResponse)
async def get_sectors_by_ticker(
    ticker: str = Path(..., description="Stock ticker symbol"),
):
    """Return visible sector/theme memberships for a ticker from the live registry."""
    normalized_ticker = ticker.strip().upper()
    cache_key = f"sectors:by-ticker:v1:{normalized_ticker}"
    if not normalized_ticker:
        return SectorsByTickerResponse(items=[])

    try:
        cached = await cache_get(cache_key)
        if cached:
            return SectorsByTickerResponse(**json.loads(cached))
    except Exception:
        pass

    try:
        idx = await asyncio.to_thread(PodcastService._sector_membership_index)
        exposure_ids = idx.get("ticker_to_sectors", {}).get(normalized_ticker, set())
        meta = idx.get("meta", {})
        items: list[SectorByTickerItem] = []
        for exposure_id in exposure_ids:
            sector_meta = meta.get(exposure_id)
            if not sector_meta:
                continue
            items.append(
                SectorByTickerItem(
                    exposure_id=exposure_id,
                    exposure_type=sector_meta.get("exposure_type") or "theme",
                    display_name=sector_meta.get("display_name") or exposure_id,
                    icon_id=sector_meta.get("icon_id"),
                    color_hex=sector_meta.get("color_hex"),
                    group=sector_meta.get("group"),
                    reason=reason_for(exposure_id, normalized_ticker) or "",
                    description=sector_meta.get("description"),
                )
            )

        def _sort_key(item: SectorByTickerItem) -> tuple[int, str]:
            if item.exposure_type == "industry":
                rank = 0
            elif item.exposure_type == "theme":
                rank = 1
            else:
                rank = 2
            return (rank, item.display_name)

        response = SectorsByTickerResponse(items=sorted(items, key=_sort_key))
        try:
            await cache_set(cache_key, json.dumps(response.model_dump(), ensure_ascii=False), 3600)
        except Exception:
            pass
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching sectors by ticker: {str(e)}")


@router.get("/sectors/performance", response_model=ExposurePerformanceResponse)
async def get_exposures_performance(db: Session = Depends(get_session)):
    """Unified theme + industry performance for the /topics bubble charts.

    One row per exposure (the frontend splits by exposure_type): discussion heat (X),
    average member daily % change (Y), aggregate constituent trading value by window
    (bubble size), plus market cap for industries only. Admin-hidden exposures are excluded
    (cheap per-request filter, same as the board).
    """
    try:
        items = await podcast_service.exposures_performance()
        served = await asyncio.to_thread(served_sector_exposure_ids, db)
        if served is None:  # bootstrap window: registry empty — fall back to blocklist
            hidden = await asyncio.to_thread(hidden_sector_exposure_ids, db)
            items = [i for i in items if i.get("exposure_id") not in hidden]
        else:
            items = [i for i in items if i.get("exposure_id") in served]
        return ExposurePerformanceResponse(
            exposures=[ExposurePerformanceItem(**i) for i in items]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching exposure performance: {str(e)}")


@router.get("/sectors/heat-validation", response_model=HeatValidationResponse)
async def get_heat_validation():
    """Point-in-time backtest of discussion heat as a forward-return predictor.

    Powers the /topics validation panel: heat recomputed as of past dates, quantized
    against the forward 7/30/90-day member return — correcting the live bubble chart,
    whose heat (X) and trailing return (Y) are both measured at request time.
    """
    try:
        return HeatValidationResponse(**await podcast_service.heat_return_validation())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error computing heat validation: {str(e)}")


@router.get("/episodes/by-sector/{exposure_id}", response_model=EpisodesBySectorResponse)
async def get_episodes_by_sector(
    exposure_id: str = Path(..., description="Sector or theme exposure ID (e.g. 'sector_passive_components')"),
    limit: int = Query(default=50, ge=1, le=200, description="Maximum number of episodes to return"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
):
    """Get episodes that mention a given sector or theme, plus aggregated representative tickers.

    Queries Firestore episodes where sector_exposure_ids array contains the given
    exposure_id. Returns the same episode list shape as GET /api/episodes/by-tag/{tag}.
    When no episodes match, returns 200 with empty lists (never 404).
    """
    try:
        result = await podcast_service.get_episodes_by_sector(
            exposure_id=exposure_id, limit=limit, offset=offset,
        )
        return EpisodesBySectorResponse(
            exposure_id=result["exposure_id"],
            display_name=result["display_name"],
            exposure_type=result["exposure_type"],
            icon_id=result.get("icon_id"),
            color_hex=result.get("color_hex"),
            description=result.get("description"),
            resolved_tickers=[SectorResolvedTicker(**t) for t in result["resolved_tickers"]],
            episodes=result["episodes"],
            total=result["total"],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching episodes by sector: {str(e)}")


@router.get("/sectors/universe")
async def get_sectors_universe(db: Session = Depends(get_session)):
    """Return the compiled universe mapping of all visible sectors/themes with their display names,
    exposure types, icons, colors, aliases, and members directly from the tag_registry table.
    """
    try:
        from src.database.models import TagRegistry
        rows = (
            db.query(TagRegistry)
            .filter(TagRegistry.kind == "sector", TagRegistry.redirect_to.is_(None))
            .all()
        )
        exposures = []
        for r in rows:
            exposures.append({
                "exposure_id": r.exposure_id,
                "exposure_type": r.exposure_type or "theme",
                "display_name": r.display_zh,
                "icon_id": r.icon_id,
                "color_hex": r.color_hex,
                "description": r.description,
                "aliases": r.aliases or [],
                "members": r.members or [],
                "parent_id": r.parent_id,
            })
        return {
            "max_tickers": 10,
            "exposures": exposures
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error compiling sectors universe: {str(e)}")
