"""
Article service — CRUD, marker extraction, and Redis caching.
"""

import re
import logging
import math
from typing import Optional
from datetime import datetime
from sqlalchemy.orm import Session
from src.database.models import Article, ArticleTag, ArticleTicker
from src.models.article import ArticleCreate, ArticleUpdate, ArticleResponse, ArticleListItem
from src.cache.redis_client import cache_delete, cache_delete_pattern

logger = logging.getLogger(__name__)

CACHE_TTL_ARTICLE = 3600       # 1 hour
CACHE_TTL_ARTICLE_LIST = 300   # 5 minutes

_TAG_RE = re.compile(r"\[.*?\]\(#tag:(.*?)\)")
_TICKER_RE = re.compile(r"\[.*?\]\(#ticker:(.*?)\)")
_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(text: str) -> str:
    """Generate a URL-safe slug from a title."""
    slug = _SLUG_RE.sub("-", text.lower()).strip("-")
    return slug[:200] if slug else "untitled"


def _estimate_read_minutes(text: str) -> int:
    """Rough CJK-aware reading-time estimate."""
    cjk = len(re.findall(r"[\u4e00-\u9fff\u3400-\u4dbf]", text))
    words = len(text.split())
    chars = cjk + words
    return max(1, math.ceil(chars / 400))


def _extract_tags(text: str) -> list[str]:
    return list(set(_TAG_RE.findall(text))) if text else []


def _extract_tickers(text: str) -> list[str]:
    return [t.upper() for t in set(_TICKER_RE.findall(text))] if text else []


class ArticleService:
    def __init__(self, session: Session):
        self.session = session

    def _sync_join_tables(self, article: Article, tags: list[str], tickers: list[str]) -> None:
        """Replace the article_tags and article_tickers rows for this article."""
        self.session.query(ArticleTag).filter_by(article_id=article.id).delete()
        self.session.query(ArticleTicker).filter_by(article_id=article.id).delete()
        for tag in set(tags):
            self.session.add(ArticleTag(article_id=article.id, tag=tag))
        for ticker in set(tickers):
            self.session.add(ArticleTicker(article_id=article.id, ticker=ticker))

    def create_article(self, data: ArticleCreate, author_id: str, author_name: str, author_avatar: Optional[str] = None) -> ArticleResponse:
        slug = data.slug or _slugify(data.title)
        existing = self.session.query(Article).filter_by(slug=slug).first()
        if existing:
            slug = f"{slug}-{int(datetime.utcnow().timestamp())}"

        body_tags = _extract_tags(data.body_content)
        body_tickers = _extract_tickers(data.body_content)
        merged_tags = list(set((data.tags or []) + body_tags))
        merged_tickers = list(set((data.tickers or []) + body_tickers))

        article = Article(
            slug=slug,
            title=data.title,
            subtitle=data.subtitle,
            author_id=author_id,
            author_name=author_name,
            author_avatar=author_avatar,
            status=data.status,
            cover_image_url=data.cover_image_url,
            body_content=data.body_content,
            key_points=data.key_points,
            tags=merged_tags,
            tickers=merged_tickers,
            read_minutes=_estimate_read_minutes(data.body_content),
            published_at=datetime.utcnow() if data.status == "published" else None,
        )
        self.session.add(article)
        self.session.flush()
        self._sync_join_tables(article, merged_tags, merged_tickers)
        self.session.commit()
        self.session.refresh(article)
        return ArticleResponse.model_validate(article)

    def update_article(self, article_id: int, data: ArticleUpdate) -> Optional[ArticleResponse]:
        article = self.session.query(Article).filter_by(id=article_id).first()
        if not article:
            return None

        update_fields = data.model_dump(exclude_unset=True)
        for field, value in update_fields.items():
            setattr(article, field, value)

        if data.body_content is not None:
            body_tags = _extract_tags(data.body_content)
            body_tickers = _extract_tickers(data.body_content)
            article.tags = list(set((article.tags or []) + body_tags))
            article.tickers = list(set((article.tickers or []) + body_tickers))
            article.read_minutes = _estimate_read_minutes(data.body_content)

        if data.status == "published" and not article.published_at:
            article.published_at = datetime.utcnow()

        self._sync_join_tables(article, article.tags or [], article.tickers or [])
        self.session.commit()
        self.session.refresh(article)
        return ArticleResponse.model_validate(article)

    def publish_article(self, article_id: int) -> Optional[ArticleResponse]:
        article = self.session.query(Article).filter_by(id=article_id).first()
        if not article:
            return None
        article.status = "published"
        if not article.published_at:
            article.published_at = datetime.utcnow()
        self.session.commit()
        self.session.refresh(article)
        return ArticleResponse.model_validate(article)

    def delete_article(self, article_id: int) -> bool:
        article = self.session.query(Article).filter_by(id=article_id).first()
        if not article:
            return False
        self.session.delete(article)
        self.session.commit()
        return True

    def get_article_by_slug(self, slug: str) -> Optional[ArticleResponse]:
        article = self.session.query(Article).filter_by(slug=slug).first()
        if not article:
            return None
        return ArticleResponse.model_validate(article)

    def get_article_by_id(self, article_id: int) -> Optional[ArticleResponse]:
        article = self.session.query(Article).filter_by(id=article_id).first()
        if not article:
            return None
        return ArticleResponse.model_validate(article)

    def list_articles(self, status: Optional[str] = None, limit: int = 50, offset: int = 0) -> list[ArticleListItem]:
        q = self.session.query(Article)
        if status:
            q = q.filter_by(status=status)
        q = q.order_by(Article.published_at.desc().nullslast(), Article.created_at.desc())
        articles = q.offset(offset).limit(limit).all()
        return [ArticleListItem.model_validate(a) for a in articles]

    def list_all_articles(self, limit: int = 50, offset: int = 0) -> list[ArticleListItem]:
        """List all articles regardless of status (for admin)."""
        q = self.session.query(Article).order_by(Article.updated_at.desc())
        articles = q.offset(offset).limit(limit).all()
        return [ArticleListItem.model_validate(a) for a in articles]

    def increment_view(self, article_id: int) -> None:
        article = self.session.query(Article).filter_by(id=article_id).first()
        if article:
            article.view_count = (article.view_count or 0) + 1
            self.session.commit()


async def invalidate_article_cache(slug: Optional[str] = None) -> None:
    """Bust Redis caches for articles."""
    await cache_delete_pattern("articles:list:*")
    if slug:
        await cache_delete(f"articles:{slug}")
