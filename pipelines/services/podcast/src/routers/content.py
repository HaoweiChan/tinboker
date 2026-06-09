"""Postgres-backed content API — episodes, podcasts, ticker insights, trending, tags.

All routes here read from the ``tinboker_wiki`` Postgres tables populated by
Phase C.  They are intentionally read-only (no writes, no auth required except
the write-gated tag management stubs added later).

Route index:
  GET /api/podcast               list all podcasts
  GET /api/podcast/{name}        single podcast metadata
  GET /api/podcast/{name}/episodes  episodes for a podcast

  GET /api/episodes/recent       most-recent episodes (paginated)
  GET /api/episodes/by-ticker/{ticker}
  GET /api/episodes/by-tag/{tag}
  GET /api/episodes/{id}         full detail + inline ticker_insights

  GET /api/ticker-insights/by-ticker/{ticker}
  GET /api/ticker-insights/by-podcaster/{name}
  GET /api/ticker-insights/trending

  GET /api/tags                  all tags with episode counts
"""

from __future__ import annotations

import os
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel
from shared.db import (
    ContentRepositories,
    Episode,
    TickerInsight,
    TrendingTicker,
    get_repositories,
)

# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_repos: ContentRepositories | None = None


def _get_repos() -> ContentRepositories:
    global _repos
    if _repos is None:
        # Content tables live in tinboker_wiki (WIKI_DATABASE_URL), not podcast_db
        url = os.environ.get("WIKI_DATABASE_URL")
        _repos = get_repositories(database_url=url)
    return _repos


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class PodcastOut(BaseModel):
    name: str
    language: str = "zh"
    spotify_show_link: Optional[str] = None
    description: Optional[str] = None
    thumbnail_url: Optional[str] = None
    episode_count: Optional[int] = None


class EpisodeOut(BaseModel):
    id: str
    podcast_name: str
    episode_title: Optional[str] = None
    episode_number: Optional[int] = None
    created_time: Optional[int] = None
    released_at_ms: Optional[int] = None
    spotify_id: Optional[str] = None
    spotify_url: Optional[str] = None
    spotify_embed_url: Optional[str] = None
    spotify_release_date: Optional[str] = None
    spotify_description: Optional[str] = None
    spotify_duration_ms: Optional[int] = None
    spotify_images: list[str] = []
    mp3_url: Optional[str] = None
    transcript_url: Optional[str] = None
    summary_url: Optional[str] = None
    summary_image_url: Optional[str] = None
    events_markdown_url: Optional[str] = None
    sentences_markdown_url: Optional[str] = None
    marp_markdown_url: Optional[str] = None
    ticker_marp_markdown_url: Optional[str] = None
    ticker_recommendations_url: Optional[str] = None
    # Content fields — omitted from list endpoints unless include_content=true
    summary_content: Optional[str] = None
    key_insights: list[str] = []
    events_markdown_content: Optional[str] = None
    sentences_markdown_content: Optional[str] = None
    marp_markdown_content: Optional[str] = None
    ticker_marp_markdown_content: Optional[str] = None
    # Categorisation
    related_tickers: list[str] = []
    tags: list[str] = []
    # Engagement
    num_likes: int = 0
    number_click: int = 0
    # Inline ticker insights (detail endpoint only)
    ticker_insights: Optional[list[dict[str, Any]]] = None


class TickerInsightOut(BaseModel):
    schema_version: int = 2
    episode_id: str
    ticker: str
    podcaster: Optional[str] = None
    podcast_launch_time: Optional[str] = None
    bluf_thesis: Optional[str] = None
    time_horizon: Optional[str] = None
    sentiment_label: Optional[str] = None
    reasons: list[dict[str, Any]] = []
    risks: list[dict[str, Any]] = []
    # sentiment_score intentionally omitted — internal-only per spec § 4.2


class TrendingTickerOut(BaseModel):
    ticker: str
    schema_version: int = 2
    count_30d: int = 0
    count_90d: int = 0
    count_all_time: int = 0
    sentiment_label: Optional[str] = None
    last_mentioned: Optional[str] = None
    top_podcasters: list[dict[str, Any]] = []
    top_episodes: list[dict[str, Any]] = []
    computed_at: Optional[str] = None


class TagOut(BaseModel):
    tag: str
    count: int


# ---------------------------------------------------------------------------
# Converters
# ---------------------------------------------------------------------------

def _ep_out(ep: Episode, *, include_content: bool = True) -> EpisodeOut:
    return EpisodeOut(
        id=ep.id,
        podcast_name=ep.podcast_name,
        episode_title=ep.episode_title,
        episode_number=ep.episode_number,
        created_time=ep.created_time,
        released_at_ms=ep.released_at_ms,
        spotify_id=ep.spotify_id,
        spotify_url=ep.spotify_url,
        spotify_embed_url=ep.spotify_embed_url,
        spotify_release_date=ep.spotify_release_date,
        spotify_description=ep.spotify_description,
        spotify_duration_ms=ep.spotify_duration_ms,
        spotify_images=ep.spotify_images,
        mp3_url=ep.mp3_url,
        transcript_url=ep.transcript_url,
        summary_url=ep.summary_url,
        summary_image_url=ep.summary_image_url,
        events_markdown_url=ep.events_markdown_url,
        sentences_markdown_url=ep.sentences_markdown_url,
        marp_markdown_url=ep.marp_markdown_url,
        ticker_marp_markdown_url=ep.ticker_marp_markdown_url,
        ticker_recommendations_url=ep.ticker_recommendations_url,
        summary_content=ep.summary_content if include_content else None,
        key_insights=ep.key_insights if include_content else [],
        events_markdown_content=ep.events_markdown_content if include_content else None,
        sentences_markdown_content=ep.sentences_markdown_content if include_content else None,
        marp_markdown_content=ep.marp_markdown_content if include_content else None,
        ticker_marp_markdown_content=ep.ticker_marp_markdown_content if include_content else None,
        related_tickers=ep.related_tickers,
        tags=ep.tags,
        num_likes=ep.num_likes,
        number_click=ep.number_click,
    )


def _insight_out(ins: TickerInsight) -> TickerInsightOut:
    return TickerInsightOut(
        schema_version=ins.schema_version,
        episode_id=ins.episode_id,
        ticker=ins.ticker,
        podcaster=ins.podcaster,
        podcast_launch_time=ins.podcast_launch_time,
        bluf_thesis=ins.bluf_thesis,
        time_horizon=ins.time_horizon,
        sentiment_label=ins.sentiment_label,
        reasons=ins.reasons,
        risks=ins.risks,
    )


def _trending_out(t: TrendingTicker) -> TrendingTickerOut:
    return TrendingTickerOut(
        ticker=t.ticker,
        schema_version=t.schema_version,
        count_30d=t.count_30d,
        count_90d=t.count_90d,
        count_all_time=t.count_all_time,
        sentiment_label=t.sentiment_label,
        last_mentioned=t.last_mentioned,
        top_podcasters=t.top_podcasters,
        top_episodes=t.top_episodes,
        computed_at=t.computed_at.isoformat().replace("+00:00", "Z") if t.computed_at else None,
    )


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

podcast_router = APIRouter(prefix="/api/podcast", tags=["content-podcasts"])
episode_router = APIRouter(prefix="/api/episodes", tags=["content-episodes"])
insights_router = APIRouter(prefix="/api/ticker-insights", tags=["content-insights"])
tags_router = APIRouter(prefix="/api/tags", tags=["content-tags"])


# ---- Podcast routes -------------------------------------------------------

@podcast_router.get("", response_model=list[PodcastOut])
async def list_podcasts(response: Response):
    """All podcasts with episode counts."""
    repos = _get_repos()
    pods = repos.podcasts.list_all()
    # Episode count per podcast from the episode table
    out = []
    for p in pods:
        # list_by_podcast is cheap (index scan); count via limit trick
        # episode_count not fetched here — caller uses /episodes endpoint for the real list
        out.append(PodcastOut(
            name=p.name,
            language=p.language,
            spotify_show_link=p.spotify_show_link,
            description=p.description,
            thumbnail_url=p.thumbnail_url,
        ))
    response.headers["Cache-Control"] = "public, max-age=300"
    return out


@podcast_router.get("/{name}", response_model=PodcastOut)
async def get_podcast(name: str):
    """Single podcast metadata."""
    repos = _get_repos()
    p = repos.podcasts.get(name)
    if p is None:
        raise HTTPException(status_code=404, detail=f"Podcast '{name}' not found")
    return PodcastOut(
        name=p.name,
        language=p.language,
        spotify_show_link=p.spotify_show_link,
        description=p.description,
        thumbnail_url=p.thumbnail_url,
    )


@podcast_router.get("/{name}/episodes", response_model=list[EpisodeOut])
async def list_podcast_episodes(
    name: str,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    include_content: bool = Query(False),
):
    """Episodes for a specific podcast, newest first."""
    repos = _get_repos()
    if repos.podcasts.get(name) is None:
        raise HTTPException(status_code=404, detail=f"Podcast '{name}' not found")
    eps = repos.episodes.list_by_podcast(name, limit=limit, offset=offset)
    return [_ep_out(e, include_content=include_content) for e in eps]


# ---- Episode routes -------------------------------------------------------

@episode_router.get("/recent", response_model=list[EpisodeOut])
async def list_recent_episodes(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    include_content: bool = Query(False),
):
    """Most-recent episodes across all podcasts."""
    repos = _get_repos()
    eps = repos.episodes.list_recent(limit=limit, offset=offset)
    return [_ep_out(e, include_content=include_content) for e in eps]


@episode_router.get("/by-ticker/{ticker}", response_model=list[EpisodeOut])
async def list_episodes_by_ticker(
    ticker: str,
    limit: int = Query(20, ge=1, le=100),
    include_content: bool = Query(False),
):
    """Episodes that mention a specific ticker symbol."""
    repos = _get_repos()
    eps = repos.episodes.list_by_ticker(ticker.upper(), limit=limit)
    return [_ep_out(e, include_content=include_content) for e in eps]


@episode_router.get("/by-tag/{tag}", response_model=list[EpisodeOut])
async def list_episodes_by_tag(
    tag: str,
    limit: int = Query(20, ge=1, le=100),
    include_content: bool = Query(False),
):
    """Episodes with a specific tag."""
    repos = _get_repos()
    eps = repos.episodes.list_by_tag(tag, limit=limit)
    return [_ep_out(e, include_content=include_content) for e in eps]


@episode_router.get("/{episode_id}", response_model=EpisodeOut)
async def get_episode(episode_id: str):
    """Full episode detail including inline ticker_insights."""
    repos = _get_repos()
    ep = repos.episodes.get(episode_id)
    if ep is None:
        raise HTTPException(status_code=404, detail=f"Episode '{episode_id}' not found")
    out = _ep_out(ep, include_content=True)
    # Inline ticker insights
    insights = repos.ticker_insights.list_by_episode(episode_id)
    out.ticker_insights = [
        {
            "ticker": i.ticker,
            "bluf_thesis": i.bluf_thesis,
            "time_horizon": i.time_horizon,
            "sentiment_label": i.sentiment_label,
            "reasons": i.reasons,
            "risks": i.risks,
            "podcaster": i.podcaster,
            "podcast_launch_time": i.podcast_launch_time,
        }
        for i in insights
    ]
    return out


# ---- Ticker insight routes ------------------------------------------------

@insights_router.get("/by-ticker/{ticker}", response_model=list[TickerInsightOut])
async def list_insights_by_ticker(
    ticker: str,
    start_date: Optional[str] = Query(None, description="YYYY-MM-DD filter (inclusive)"),
    end_date: Optional[str] = Query(None, description="YYYY-MM-DD filter (inclusive)"),
    limit: int = Query(100, ge=1, le=500),
):
    """Ticker insights for a symbol, newest first."""
    repos = _get_repos()
    insights = repos.ticker_insights.list_by_ticker(
        ticker.upper(), start_date=start_date, end_date=end_date, limit=limit
    )
    return [_insight_out(i) for i in insights]


@insights_router.get("/by-podcaster/{podcaster}", response_model=list[TickerInsightOut])
async def list_insights_by_podcaster(
    podcaster: str,
    start_date: Optional[str] = Query(None, description="YYYY-MM-DD filter (inclusive)"),
    end_date: Optional[str] = Query(None, description="YYYY-MM-DD filter (inclusive)"),
    limit: int = Query(100, ge=1, le=500),
):
    """Ticker insights authored by a specific podcaster, newest first."""
    repos = _get_repos()
    insights = repos.ticker_insights.list_by_podcaster(
        podcaster, start_date=start_date, end_date=end_date, limit=limit
    )
    return [_insight_out(i) for i in insights]


@insights_router.get("/trending", response_model=list[TrendingTickerOut])
async def list_trending(
    days: int = Query(30, description="Window: 30, 90, or 0 for all-time"),
    limit: int = Query(100, ge=1, le=500),
    response: Response = None,
):
    """Pre-aggregated trending tickers, sorted by mention count in the requested window."""
    repos = _get_repos()
    tickers = repos.trending_tickers.list_trending(days=days, limit=limit)
    if response is not None:
        response.headers["Cache-Control"] = "public, max-age=300"
    return [_trending_out(t) for t in tickers]


# ---- Tags route -----------------------------------------------------------

@tags_router.get("", response_model=list[TagOut])
async def list_tags(response: Response):
    """All episode tags with mention counts, sorted by count descending."""
    repos = _get_repos()
    tags = repos.episodes.list_all_tags()
    response.headers["Cache-Control"] = "public, max-age=300"
    return [TagOut(tag=t, count=c) for t, c in tags]
