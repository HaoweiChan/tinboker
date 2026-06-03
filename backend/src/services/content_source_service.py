"""
Service for managing content sources (followed podcast shows + news RSS feeds).
"""

import re
import logging
from typing import Optional, List, Tuple
from sqlalchemy import func
from sqlalchemy.orm import Session
from src.database.models import ContentSource
from src.schemas.content_source import (
    ContentSourceCreate,
    ContentSourceUpdate,
)

logger = logging.getLogger(__name__)


def slugify(name: str) -> str:
    """Derive a stable slug from a source name.

    Keeps unicode word characters (so CJK names like '財報狗' survive), lowercases
    ASCII, and collapses everything else to single hyphens. Returns 'source' as a
    last resort for names with no usable characters.
    """
    slug = re.sub(r"[^\w]+", "-", (name or "").strip(), flags=re.UNICODE)
    slug = slug.strip("-").lower()
    return slug or "source"


class ContentSourceService:
    """Service class for content-source CRUD operations."""

    def __init__(self, db: Session):
        self.db = db

    # ---------- reads ----------

    def get_by_id(self, source_id: int) -> Optional[ContentSource]:
        return self.db.query(ContentSource).filter(
            ContentSource.id == source_id
        ).first()

    def get_by_type_slug(self, source_type: str, slug: str) -> Optional[ContentSource]:
        return self.db.query(ContentSource).filter(
            ContentSource.source_type == source_type,
            ContentSource.slug == slug,
        ).first()

    def list_sources(
        self,
        source_type: Optional[str] = None,
        region: Optional[str] = None,
        language: Optional[str] = None,
        active: Optional[bool] = None,
        search: Optional[str] = None,
        page: int = 1,
        limit: int = 50,
    ) -> Tuple[List[ContentSource], int]:
        """List content sources with optional filters. Returns (items, total_count)."""
        query = self.db.query(ContentSource)
        if source_type:
            query = query.filter(ContentSource.source_type == source_type)
        if region:
            query = query.filter(ContentSource.region == region.upper())
        if language:
            query = query.filter(ContentSource.language == language)
        if active is not None:
            query = query.filter(ContentSource.active == active)
        if search:
            pattern = f"%{search}%"
            query = query.filter(
                (ContentSource.name.ilike(pattern)) |
                (ContentSource.slug.ilike(pattern)) |
                (ContentSource.feed_url.ilike(pattern))
            )
        total = query.count()
        offset = (page - 1) * limit
        items = (
            query.order_by(ContentSource.source_type, ContentSource.name)
            .offset(offset)
            .limit(limit)
            .all()
        )
        return items, total

    def list_active_public(self, source_type: Optional[str] = None) -> List[ContentSource]:
        """Active sources for the pipeline pull (GET /api/sources)."""
        query = self.db.query(ContentSource).filter(ContentSource.active.is_(True))
        if source_type:
            query = query.filter(ContentSource.source_type == source_type)
        return query.order_by(ContentSource.source_type, ContentSource.name).all()

    # ---------- writes ----------

    def _unique_slug(self, source_type: str, base: str, exclude_id: Optional[int] = None) -> str:
        """Return a slug unique within the given source_type, suffixing -2, -3, ... on collision."""
        candidate = base
        n = 1
        while True:
            existing = self.get_by_type_slug(source_type, candidate)
            if existing is None or existing.id == exclude_id:
                return candidate
            n += 1
            candidate = f"{base}-{n}"

    def create(
        self,
        data: ContentSourceCreate,
        updated_by: Optional[str] = None,
    ) -> ContentSource:
        base_slug = slugify(data.slug or data.name)
        slug = self._unique_slug(data.source_type, base_slug)
        source = ContentSource(
            source_type=data.source_type,
            name=data.name,
            slug=slug,
            feed_url=data.feed_url,
            region=data.region.upper() if data.region else None,
            language=data.language,
            spotify_url=data.spotify_url,
            lookback_days=data.lookback_days,
            max_episodes=data.max_episodes,
            transcript_service=data.transcript_service,
            transcript_model=data.transcript_model,
            active=data.active,
            extra=data.extra,
            last_updated_by=updated_by,
        )
        self.db.add(source)
        self.db.commit()
        self.db.refresh(source)
        logger.info("Created content source: %s/%s", source.source_type, source.slug)
        return source

    def update(
        self,
        source_id: int,
        data: ContentSourceUpdate,
        updated_by: Optional[str] = None,
    ) -> Optional[ContentSource]:
        source = self.get_by_id(source_id)
        if not source:
            return None
        update_data = data.model_dump(exclude_unset=True)
        if "region" in update_data and update_data["region"]:
            update_data["region"] = update_data["region"].upper()
        for field, value in update_data.items():
            setattr(source, field, value)
        source.last_updated_by = updated_by
        self.db.commit()
        self.db.refresh(source)
        logger.info("Updated content source: %s/%s", source.source_type, source.slug)
        return source

    def delete(self, source_id: int) -> bool:
        source = self.get_by_id(source_id)
        if not source:
            return False
        self.db.delete(source)
        self.db.commit()
        logger.info("Deleted content source ID: %s", source_id)
        return True

    def seed_from_config(self, entries: List[dict]) -> int:
        """Insert-only seed from a list of source dicts (idempotent on source_type+slug).

        Used at startup to populate the table from the current agents JSON config without
        ever overwriting operator edits. Returns the number of rows inserted.
        """
        inserted = 0
        for entry in entries:
            try:
                data = ContentSourceCreate(**entry)
            except Exception as e:  # skip malformed seed rows, don't crash startup
                logger.warning("seed_from_config: skip %r: %s", entry.get("name"), e)
                continue
            base_slug = slugify(data.slug or data.name)
            if self.get_by_type_slug(data.source_type, base_slug):
                continue  # already present — never overwrite
            try:
                self.create(data, updated_by="startup_seed")
                inserted += 1
            except Exception as e:
                logger.warning("seed_from_config: insert failed for %s: %s", data.name, e)
                self.db.rollback()
        return inserted

    def get_stats(self) -> dict:
        """Counts by type and active flag, for the admin header."""
        total = self.db.query(func.count(ContentSource.id)).scalar()
        by_type = self.db.query(
            ContentSource.source_type,
            func.count(ContentSource.id),
        ).group_by(ContentSource.source_type).all()
        active = self.db.query(func.count(ContentSource.id)).filter(
            ContentSource.active.is_(True)
        ).scalar()
        return {
            "total": total,
            "active": active,
            "by_type": {t: c for t, c in by_type},
        }
