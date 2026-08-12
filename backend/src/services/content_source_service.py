"""
Service for managing content sources (followed podcast shows + news RSS feeds).
"""

import json
import re
import logging
import urllib.parse
import urllib.request
from typing import Optional, List, Tuple
from sqlalchemy import func
from sqlalchemy.orm import Session
from src.database.models import ContentSource
from src.schemas.content_source import (
    ContentSourceCreate,
    ContentSourceUpdate,
)
from src.services.gcs_content import public_base, store_bytes

logger = logging.getLogger(__name__)

# Show artwork is mirrored into the articles media directory, next to the episode
# summary images. Covers are small (Spotify's oEmbed thumbnail is 640px); the cap is
# there to stop a redirect-to-something-huge, not because real covers approach it.
_COVER_BUCKET = "graphfolio-articles"
_COVER_MAX_BYTES = 4 * 1024 * 1024
# The extension decides how the media host serves the bytes back, so it is derived
# from the *response* content type and never from the URL. Anything not on this list
# (notably SVG, which would be a scriptable document on the media origin) is refused.
_COVER_EXT = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}


def slugify(name: str) -> str:
    """Derive a stable slug from a source name.

    Keeps unicode word characters (so CJK names like '財報狗' survive), lowercases
    ASCII, and collapses everything else to single hyphens. Returns 'source' as a
    last resort for names with no usable characters.
    """
    slug = re.sub(r"[^\w]+", "-", (name or "").strip(), flags=re.UNICODE)
    slug = slug.strip("-").lower()
    return slug or "source"


def _oembed_thumbnail(spotify_url: str, timeout: float) -> str:
    """The show's artwork URL from Spotify's public oEmbed endpoint (no auth)."""
    api = "https://open.spotify.com/oembed?url=" + urllib.parse.quote(spotify_url, safe="")
    with urllib.request.urlopen(api, timeout=timeout) as resp:
        return (json.load(resp).get("thumbnail_url") or "").strip()


def _fetch_image(url: str, timeout: float) -> Tuple[bytes, str]:
    """Download an image as ``(bytes, content_type)``.

    Reads one byte past the cap so the caller can tell "exactly at the limit" from
    "truncated", rather than silently storing a half image.
    """
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        ctype = (resp.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
        return resp.read(_COVER_MAX_BYTES + 1), ctype


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
            cover_image_url=data.cover_image_url,
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

    def mirror_podcast_covers(self, timeout: float = 8.0) -> int:
        """Mirror every podcast's show artwork into our own media store.

        Both cases run through this one pass, because the predicate is "the stored URL
        is not ours" rather than "the row has no cover":

          - ingest: a newly seeded source has no cover at all → resolve it from
            Spotify's public oEmbed (no auth), then store the bytes;
          - backfill: an existing row already has a cover somewhere off-site (Spotify's
            CDN, or the SoundOn URLs some seeded rows carry) → fetch that URL and
            re-host it. The stored URL is used as-is, so this does not assume Spotify.

        Idempotent: a row already pointing at the media host is skipped without any
        network call, so re-running on every boot costs nothing once mirrored.
        Best-effort — a show whose artwork cannot be fetched keeps whatever it had, and
        one bad source never aborts the pass. Returns the number of rows re-pointed.
        """
        rows = (
            self.db.query(ContentSource)
            .filter(ContentSource.source_type == "podcast")
            .all()
        )
        ours = public_base() + "/"
        updated = 0
        for src in rows:
            current = (src.cover_image_url or "").strip()
            if current.startswith(ours):
                continue  # already mirrored
            try:
                url = current or (
                    _oembed_thumbnail(src.spotify_url, timeout) if src.spotify_url else ""
                )
                # Only ever fetch https: the URL comes out of the database, and the
                # oEmbed response is a third party's JSON. This also drops the
                # nothing-to-mirror case (no cover and no Spotify link) without noise.
                if not url.startswith("https://"):
                    continue
                data, ctype = _fetch_image(url, timeout)
                ext = _COVER_EXT.get(ctype)
                if not ext or not data or len(data) > _COVER_MAX_BYTES:
                    logger.warning(
                        "cover mirror: %s — unusable artwork (%s, %d bytes)", src.name, ctype, len(data)
                    )
                    continue
                src.cover_image_url = store_bytes(_COVER_BUCKET, f"covers/{src.id}{ext}", data)
                updated += 1
            except Exception as e:
                logger.warning("cover mirror: %s failed: %s", src.name, e)
                continue
        if updated:
            self.db.commit()
            logger.info("Mirrored cover art for %d podcast source(s)", updated)
        return updated

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
