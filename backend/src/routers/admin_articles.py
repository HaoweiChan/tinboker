"""
Admin articles router — authenticated write endpoints for article CRUD.
"""

import logging
from fastapi import APIRouter, HTTPException, Path, Query, Depends
from sqlalchemy.orm import Session
from src.database.postgres import get_session
from src.auth.admin_auth import AdminAccess, get_article_author_access
from src.config import settings
from src.services.article_service import ArticleService, invalidate_article_cache
from src.models.article import ArticleCreate, ArticleUpdate, ArticleResponse, ArticleListItem

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/articles", tags=["admin-articles"])


def _resolve_author(admin: AdminAccess) -> tuple[str, str, str | None]:
    """Resolve the byline for admin UI writes and article-token MCP writes."""
    if admin.user_id != "article-service":
        return admin.user_id or admin.email, admin.email.split("@")[0], None

    fallback_email = settings.admin_emails[0] if settings.admin_emails else admin.email
    author_id = settings.tinboker_article_author_id or fallback_email
    author_name = settings.tinboker_article_author_name or fallback_email.split("@")[0]
    return author_id, author_name, settings.tinboker_article_author_avatar


@router.get("", response_model=list[ArticleListItem])
async def list_all_articles(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    admin: AdminAccess = Depends(get_article_author_access),
    db: Session = Depends(get_session),
):
    """List all articles (any status) for admin management."""
    svc = ArticleService(db)
    return svc.list_all_articles(limit=limit, offset=offset)


@router.get("/{article_id}", response_model=ArticleResponse)
async def get_article(
    article_id: int = Path(...),
    admin: AdminAccess = Depends(get_article_author_access),
    db: Session = Depends(get_session),
):
    """Get any article by ID (admin view, any status)."""
    svc = ArticleService(db)
    article = svc.get_article_by_id(article_id)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    return article


@router.post("", response_model=ArticleResponse, status_code=201)
async def create_article(
    data: ArticleCreate,
    admin: AdminAccess = Depends(get_article_author_access),
    db: Session = Depends(get_session),
):
    """Create a new article draft."""
    svc = ArticleService(db)
    author_id, author_name, author_avatar = _resolve_author(admin)
    article = svc.create_article(
        data=data,
        author_id=author_id,
        author_name=author_name,
        author_avatar=author_avatar,
    )
    await invalidate_article_cache()
    return article


@router.patch("/{article_id}", response_model=ArticleResponse)
async def update_article(
    data: ArticleUpdate,
    article_id: int = Path(...),
    admin: AdminAccess = Depends(get_article_author_access),
    db: Session = Depends(get_session),
):
    """Update an existing article."""
    svc = ArticleService(db)
    old = svc.get_article_by_id(article_id)
    article = svc.update_article(article_id, data)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    await invalidate_article_cache(slug=old.slug if old else None)
    return article


@router.post("/{article_id}/publish", response_model=ArticleResponse)
async def publish_article(
    article_id: int = Path(...),
    admin: AdminAccess = Depends(get_article_author_access),
    db: Session = Depends(get_session),
):
    """Publish an article (sets status to published)."""
    svc = ArticleService(db)
    article = svc.publish_article(article_id)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    await invalidate_article_cache(slug=article.slug)
    return article


@router.post("/{article_id}/unpublish", response_model=ArticleResponse)
async def unpublish_article(
    article_id: int = Path(...),
    admin: AdminAccess = Depends(get_article_author_access),
    db: Session = Depends(get_session),
):
    """Revert a published article back to draft status."""
    svc = ArticleService(db)
    article = svc.unpublish_article(article_id)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    await invalidate_article_cache(slug=article.slug)
    return article


@router.delete("/{article_id}", status_code=204)
async def delete_article(
    article_id: int = Path(...),
    admin: AdminAccess = Depends(get_article_author_access),
    db: Session = Depends(get_session),
):
    """Delete an article."""
    svc = ArticleService(db)
    old = svc.get_article_by_id(article_id)
    if not svc.delete_article(article_id):
        raise HTTPException(status_code=404, detail="Article not found")
    await invalidate_article_cache(slug=old.slug if old else None)
