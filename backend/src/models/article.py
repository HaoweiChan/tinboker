"""
Article Pydantic models for request/response validation.
"""

from typing import Optional, Literal
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


ArticleStatus = Literal["draft", "pending_review", "published", "archived"]


class ArticleCreate(BaseModel):
    """Request body for creating an article."""
    title: str = Field(..., min_length=1, max_length=500)
    subtitle: Optional[str] = None
    slug: Optional[str] = Field(None, max_length=255)
    body_content: str = Field(default="")
    cover_image_url: Optional[str] = None
    key_points: Optional[list[str]] = None
    tags: Optional[list[str]] = None
    tickers: Optional[list[str]] = None
    status: ArticleStatus = "draft"


class ArticleUpdate(BaseModel):
    """Request body for updating an article (all fields optional)."""
    title: Optional[str] = Field(None, min_length=1, max_length=500)
    subtitle: Optional[str] = None
    slug: Optional[str] = Field(None, max_length=255)
    body_content: Optional[str] = None
    cover_image_url: Optional[str] = None
    key_points: Optional[list[str]] = None
    tags: Optional[list[str]] = None
    tickers: Optional[list[str]] = None
    status: Optional[ArticleStatus] = None


class ArticleResponse(BaseModel):
    """Public article response."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    title: str
    subtitle: Optional[str] = None
    author_id: str
    author_name: str
    author_avatar: Optional[str] = None
    status: str
    cover_image_url: Optional[str] = None
    body_content: str = ""
    key_points: Optional[list[str]] = None
    tags: Optional[list[str]] = None
    tickers: Optional[list[str]] = None
    read_minutes: Optional[int] = None
    view_count: int = 0
    published_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ArticleListItem(BaseModel):
    """Compact article for list views (no body)."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    title: str
    subtitle: Optional[str] = None
    author_name: str
    author_avatar: Optional[str] = None
    status: str
    cover_image_url: Optional[str] = None
    key_points: Optional[list[str]] = None
    tags: Optional[list[str]] = None
    tickers: Optional[list[str]] = None
    read_minutes: Optional[int] = None
    view_count: int = 0
    published_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
