"""Tags API router for tag-based episode discovery"""
from fastapi import APIRouter, HTTPException, Path, Query
from typing import List, Optional
from pydantic import BaseModel
from src.services.podcast import PodcastService

router = APIRouter(prefix="/api", tags=["tags"])

podcast_service = PodcastService()


class Tag(BaseModel):
    id: str
    name: str
    episode_count: int


class TagsResponse(BaseModel):
    tags: List[Tag]


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
        episodes_dict = [ep.dict() for ep in episodes]
        return EpisodesByTagResponse(tag=tag, episodes=episodes_dict, total=len(episodes_dict))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching episodes by tag: {str(e)}")
