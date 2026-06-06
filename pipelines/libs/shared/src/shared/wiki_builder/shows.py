"""Podcast show registry — the list of shows the pipeline monitors for new episodes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert

from .postgres_repo import podcast_shows


def _row_to_show(row: sa.Row) -> PodcastShow:
    return PodcastShow(
        slug=row.slug,
        name=row.name,
        rss_url=row.rss_url,
        spotify_url=row.spotify_url,
        episode_limit=row.episode_limit,
        active=row.active,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@dataclass
class PodcastShow:
    slug: str
    name: str
    rss_url: str
    spotify_url: str | None = None
    episode_limit: int = 10
    active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "slug": self.slug,
            "name": self.name,
            "rss_url": self.rss_url,
            "spotify_url": self.spotify_url,
            "episode_limit": self.episode_limit,
            "active": self.active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def to_pipeline_config(self) -> dict[str, Any]:
        """Return a dict matching the podcasts_tw.json entry shape."""
        return {
            "name": self.name,
            "link": self.rss_url,
            "limit": self.episode_limit,
            "spotify_show_link": self.spotify_url,
        }


class PostgresShowRepository:
    def __init__(self, engine: sa.Engine) -> None:
        self.engine = engine

    def list_shows(self, *, active_only: bool = False) -> list[PodcastShow]:
        query = sa.select(podcast_shows).order_by(podcast_shows.c.name)
        if active_only:
            query = query.where(podcast_shows.c.active.is_(True))
        with self.engine.connect() as conn:
            rows = conn.execute(query).all()
        return [_row_to_show(r) for r in rows]

    def get_show(self, slug: str) -> PodcastShow | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                sa.select(podcast_shows).where(podcast_shows.c.slug == slug)
            ).one_or_none()
        return _row_to_show(row) if row is not None else None

    def upsert_show(self, show: PodcastShow) -> PodcastShow:
        stmt = pg_insert(podcast_shows).values(
            slug=show.slug,
            name=show.name,
            rss_url=show.rss_url,
            spotify_url=show.spotify_url,
            episode_limit=show.episode_limit,
            active=show.active,
            updated_at=sa.func.now(),
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["slug"],
            set_={
                "name": stmt.excluded.name,
                "rss_url": stmt.excluded.rss_url,
                "spotify_url": stmt.excluded.spotify_url,
                "episode_limit": stmt.excluded.episode_limit,
                "active": stmt.excluded.active,
                "updated_at": sa.func.now(),
            },
        )
        with self.engine.begin() as conn:
            conn.execute(stmt)
            row = conn.execute(
                sa.select(podcast_shows).where(podcast_shows.c.slug == show.slug)
            ).one()
        return _row_to_show(row)

    def set_active(self, slug: str, active: bool) -> PodcastShow | None:
        with self.engine.begin() as conn:
            conn.execute(
                sa.update(podcast_shows)
                .where(podcast_shows.c.slug == slug)
                .values(active=active, updated_at=sa.func.now())
            )
            row = conn.execute(
                sa.select(podcast_shows).where(podcast_shows.c.slug == slug)
            ).one_or_none()
        return _row_to_show(row) if row is not None else None

    def delete_show(self, slug: str) -> bool:
        with self.engine.begin() as conn:
            result = conn.execute(
                sa.delete(podcast_shows).where(podcast_shows.c.slug == slug)
            )
        return result.rowcount > 0
