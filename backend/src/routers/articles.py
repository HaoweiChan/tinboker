"""
Public articles router — unauthenticated read endpoints.
"""

import json
import logging
from fastapi import APIRouter, HTTPException, Path, Query, Depends
from sqlalchemy.orm import Session
from src.database.postgres import get_session
from src.services.article_service import ArticleService, CACHE_TTL_ARTICLE, CACHE_TTL_ARTICLE_LIST
from src.models.article import ArticleResponse, ArticleListItem
from src.cache.redis_client import cache_get, cache_set
from src.cache.cdn_cache import cdn_cached, CacheProfile

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/articles", tags=["articles"])


@router.get("", response_model=list[ArticleListItem])
@cdn_cached(profile=CacheProfile.NEWS)
async def list_published_articles(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_session),
):
    """List published articles, newest first."""
    cache_key = f"articles:list:published:{offset}:{limit}"
    cached = await cache_get(cache_key)
    if cached:
        return json.loads(cached)
    svc = ArticleService(db)
    articles = svc.list_articles(status="published", limit=limit, offset=offset)
    result = [a.model_dump(mode="json") for a in articles]
    await cache_set(cache_key, json.dumps(result, default=str), CACHE_TTL_ARTICLE_LIST)
    return result


@router.get("/{slug}", response_model=ArticleResponse)
@cdn_cached(profile=CacheProfile.NEWS)
async def get_article_by_slug(
    slug: str = Path(..., description="Article URL slug"),
    db: Session = Depends(get_session),
):
    """Get a published article by slug."""
    cache_key = f"articles:{slug}"
    cached = await cache_get(cache_key)
    if cached:
        return json.loads(cached)
    svc = ArticleService(db)
    article = svc.get_article_by_slug(slug)
    if not article or article.status != "published":
        raise HTTPException(status_code=404, detail="Article not found")
    svc.increment_view(article.id)
    result = article.model_dump(mode="json")
    await cache_set(cache_key, json.dumps(result, default=str), CACHE_TTL_ARTICLE)
    return result
