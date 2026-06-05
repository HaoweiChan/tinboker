"""
Pydantic schemas for content sources (followed podcast shows + news RSS feeds).
"""

from datetime import datetime
from typing import Optional, List, Literal, Any, Dict
from pydantic import BaseModel, Field

SourceType = Literal["podcast", "news"]


class ContentSourceBase(BaseModel):
    """Base content-source schema with common + type-specific fields."""
    source_type: SourceType = Field(..., description="podcast | news")
    name: str = Field(..., max_length=300, description="Display name of the show/feed")
    feed_url: str = Field(..., description="RSS/feed URL")
    region: Optional[str] = Field(None, max_length=10, description="News region: US, TW, ...")
    language: Optional[str] = Field(None, max_length=10, description="Podcast content language: zh-TW, en")
    spotify_url: Optional[str] = Field(None, description="Podcast Spotify show URL")
    cover_image_url: Optional[str] = Field(None, description="Podcast cover art URL (Spotify show thumbnail)")
    lookback_days: Optional[int] = Field(None, ge=1, description="Ingest window: only items newer than N days")
    max_episodes: Optional[int] = Field(None, ge=1, description="Optional cap: at most N most-recent items per run")
    transcript_service: Optional[str] = Field(None, max_length=20, description="groq | whisper | openai")
    transcript_model: Optional[str] = Field(None, max_length=50, description="STT model, e.g. whisper-large-v3")
    active: bool = True
    extra: Optional[Dict[str, Any]] = None


class ContentSourceCreate(ContentSourceBase):
    """Schema for creating a new content source. Slug is auto-derived from name."""
    slug: Optional[str] = Field(None, max_length=100, description="Optional explicit slug; auto-derived if omitted")


class ContentSourceUpdate(BaseModel):
    """Schema for updating an existing content source (all fields optional)."""
    name: Optional[str] = Field(None, max_length=300)
    feed_url: Optional[str] = None
    region: Optional[str] = Field(None, max_length=10)
    language: Optional[str] = Field(None, max_length=10)
    spotify_url: Optional[str] = None
    cover_image_url: Optional[str] = None
    lookback_days: Optional[int] = Field(None, ge=1)
    max_episodes: Optional[int] = Field(None, ge=1)
    transcript_service: Optional[str] = Field(None, max_length=20)
    transcript_model: Optional[str] = Field(None, max_length=50)
    active: Optional[bool] = None
    extra: Optional[Dict[str, Any]] = None


class ContentSourceResponse(ContentSourceBase):
    """Schema for a content-source admin response."""
    id: int
    slug: str
    last_updated_by: Optional[str] = None
    last_updated_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ContentSourceListResponse(BaseModel):
    """Schema for paginated content-source list."""
    total: int
    page: int
    limit: int
    items: List[ContentSourceResponse]


class ContentSourcePublic(BaseModel):
    """Minimal read-only shape the agents pipeline consumes when pulling the follow-list.

    The download step should select items published within `lookback_days`, optionally
    capped at `max_episodes` most-recent. Maps 1:1 to the agents repo's per-show config.
    """
    source_type: SourceType
    name: str
    slug: str
    feed_url: str
    region: Optional[str] = None
    language: Optional[str] = None
    spotify_url: Optional[str] = None
    lookback_days: Optional[int] = None
    max_episodes: Optional[int] = None
    transcript_service: Optional[str] = None
    transcript_model: Optional[str] = None

    class Config:
        from_attributes = True


class ContentSourcePublicListResponse(BaseModel):
    """Read-only follow-list response for the pipeline pull."""
    total: int
    items: List[ContentSourcePublic]


class SourceRunStatus(BaseModel):
    """Per-source ingest status derived from Firestore episodes (podcasts only in v1)."""
    name: str
    last_ingested_at: Optional[str] = None  # ISO 8601 UTC of the most recent episode
    episode_count: int = 0


class SourceRunStatusResponse(BaseModel):
    """Run-status keyed by source name; news sources have no entry in v1."""
    items: List[SourceRunStatus]
