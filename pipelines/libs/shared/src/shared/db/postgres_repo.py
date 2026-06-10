"""Postgres-backed repository implementations for the consolidated content store.

Schema created by :func:`init_schema` (idempotent — uses ``CREATE TABLE IF NOT EXISTS``
via ``checkfirst=True``)::

    podcasts(name PK, spotify_show_link, description, thumbnail_url, language,
             created_at, updated_at)

    episodes(id PK, podcast_name FK→podcasts.name,
             episode_title, episode_number,
             created_time BIGINT, released_at_ms BIGINT,
             spotify_id, spotify_url, spotify_embed_url, spotify_release_date,
             spotify_description, spotify_duration_ms, spotify_images TEXT[],
             mp3_url, transcript_url, summary_url, summary_image_url,
             events_markdown_url, sentences_markdown_url, marp_markdown_url,
             ticker_marp_markdown_url, ticker_recommendations_url,
             summary_content, key_insights TEXT[], events_markdown_content,
             sentences_markdown_content, marp_markdown_content,
             ticker_marp_markdown_content, ticker_recommendations_content,
             related_tickers TEXT[], tags TEXT[],
             num_likes INT, number_click INT,
             created_at, updated_at)
        INDEX episodes(created_time DESC)
        INDEX episodes USING GIN(related_tickers)
        INDEX episodes USING GIN(tags)

    tickers(symbol PK, canonical, name, market, sector)

    ticker_insights(episode_id FK→episodes.id, ticker FK→tickers.symbol,
                    schema_version, bluf_thesis, time_horizon,
                    sentiment_label, sentiment_score,
                    reasons JSONB, risks JSONB,
                    podcaster, podcast_launch_time, created_at)
        PK (episode_id, ticker)
        INDEX ticker_insights(ticker)
        INDEX ticker_insights(podcast_launch_time)

    trending_tickers(ticker PK FK→tickers.symbol,
                     schema_version, count_30d, count_90d, count_all_time,
                     sentiment_label, sentiment_score,
                     last_mentioned, top_podcasters JSONB, top_episodes JSONB,
                     computed_at)
        INDEX trending_tickers(last_mentioned DESC)
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import insert as pg_insert

from .models import Episode, Podcast, Ticker, TickerInsight, TrendingTicker
from .repository import (
    EpisodeRepository,
    PodcastRepository,
    TickerInsightRepository,
    TickerRepository,
    TrendingTickerRepository,
)

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

metadata = sa.MetaData()

_Text = sa.Text


def _ts():
    return sa.DateTime(timezone=True)


def _now():
    return sa.func.now()

podcasts_table = sa.Table(
    "podcasts",
    metadata,
    sa.Column("name", _Text, primary_key=True),
    sa.Column("spotify_show_link", _Text),
    sa.Column("description", _Text),
    sa.Column("thumbnail_url", _Text),
    sa.Column("language", _Text, nullable=False, server_default="zh"),
    sa.Column("created_at", _ts(), nullable=False, server_default=_now()),
    sa.Column("updated_at", _ts(), nullable=False, server_default=_now()),
)

episodes_table = sa.Table(
    "episodes",
    metadata,
    sa.Column("id", _Text, primary_key=True),
    sa.Column(
        "podcast_name",
        _Text,
        sa.ForeignKey("podcasts.name", ondelete="RESTRICT", name="fk_episodes_podcast"),
        nullable=False,
    ),
    sa.Column("episode_title", _Text),
    sa.Column("episode_number", sa.Integer),
    sa.Column("created_time", sa.BigInteger),
    sa.Column("released_at_ms", sa.BigInteger),
    sa.Column("spotify_id", _Text),
    sa.Column("spotify_url", _Text),
    sa.Column("spotify_embed_url", _Text),
    sa.Column("spotify_release_date", _Text),
    sa.Column("spotify_description", _Text),
    sa.Column("spotify_duration_ms", sa.Integer),
    sa.Column("spotify_images", ARRAY(_Text), server_default="{}"),
    sa.Column("mp3_url", _Text),
    sa.Column("transcript_url", _Text),
    sa.Column("summary_url", _Text),
    sa.Column("summary_image_url", _Text),
    sa.Column("events_markdown_url", _Text),
    sa.Column("sentences_markdown_url", _Text),
    sa.Column("marp_markdown_url", _Text),
    sa.Column("ticker_marp_markdown_url", _Text),
    sa.Column("ticker_recommendations_url", _Text),
    sa.Column("summary_content", _Text),
    sa.Column("key_insights", ARRAY(_Text), server_default="{}"),
    sa.Column("events_markdown_content", _Text),
    sa.Column("sentences_markdown_content", _Text),
    sa.Column("marp_markdown_content", _Text),
    sa.Column("ticker_marp_markdown_content", _Text),
    sa.Column("ticker_recommendations_content", _Text),
    sa.Column("related_tickers", ARRAY(_Text), server_default="{}"),
    sa.Column("tags", ARRAY(_Text), server_default="{}"),
    sa.Column("num_likes", sa.Integer, nullable=False, server_default="0"),
    sa.Column("number_click", sa.Integer, nullable=False, server_default="0"),
    sa.Column("created_at", _ts(), nullable=False, server_default=_now()),
    sa.Column("updated_at", _ts(), nullable=False, server_default=_now()),
    sa.Index("ix_episodes_created_time", "created_time", postgresql_using="btree"),
    sa.Index("ix_episodes_related_tickers", "related_tickers", postgresql_using="gin"),
    sa.Index("ix_episodes_tags", "tags", postgresql_using="gin"),
    sa.Index("ix_episodes_podcast_name", "podcast_name"),
)

tickers_table = sa.Table(
    "tickers",
    metadata,
    sa.Column("symbol", _Text, primary_key=True),
    sa.Column("canonical", _Text),
    sa.Column("name", _Text),
    sa.Column("market", _Text),
    sa.Column("sector", _Text),
)

ticker_insights_table = sa.Table(
    "ticker_insights",
    metadata,
    sa.Column("episode_id", _Text, sa.ForeignKey("episodes.id", ondelete="CASCADE", name="fk_ti_episode"), primary_key=True),
    sa.Column("ticker", _Text, sa.ForeignKey("tickers.symbol", ondelete="RESTRICT", name="fk_ti_ticker"), primary_key=True),
    sa.Column("schema_version", sa.Integer, nullable=False, server_default="3"),
    sa.Column("bluf_thesis", _Text),
    sa.Column("time_horizon", _Text),
    sa.Column("sentiment_label", _Text),
    sa.Column("sentiment_score", sa.Float),
    sa.Column("reasons", JSONB, nullable=False, server_default="[]"),
    sa.Column("risks", JSONB, nullable=False, server_default="[]"),
    sa.Column("podcaster", _Text),
    sa.Column("podcast_launch_time", _Text),
    sa.Column("created_at", _ts(), nullable=False, server_default=_now()),
    sa.Index("ix_ti_ticker", "ticker"),
    sa.Index("ix_ti_podcaster", "podcaster"),
    sa.Index("ix_ti_podcast_launch_time", "podcast_launch_time"),
)

trending_tickers_table = sa.Table(
    "trending_tickers",
    metadata,
    sa.Column("ticker", _Text, sa.ForeignKey("tickers.symbol", ondelete="CASCADE", name="fk_tt_ticker"), primary_key=True),
    sa.Column("schema_version", sa.Integer, nullable=False, server_default="3"),
    sa.Column("count_30d", sa.Integer, nullable=False, server_default="0"),
    sa.Column("count_90d", sa.Integer, nullable=False, server_default="0"),
    sa.Column("count_all_time", sa.Integer, nullable=False, server_default="0"),
    sa.Column("sentiment_label", _Text),
    sa.Column("sentiment_score", sa.Float),
    sa.Column("last_mentioned", _Text),
    sa.Column("top_podcasters", JSONB, nullable=False, server_default="[]"),
    sa.Column("top_episodes", JSONB, nullable=False, server_default="[]"),
    sa.Column("computed_at", _ts()),
    sa.Index("ix_tt_last_mentioned", "last_mentioned"),
    sa.Index("ix_tt_count_30d", "count_30d"),
)


def init_schema(engine: sa.Engine) -> None:
    """Create all tables (idempotent — no-op if they already exist)."""
    metadata.create_all(engine, checkfirst=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)


def _row_to_episode(row: sa.Row) -> Episode:
    return Episode(
        id=row.id,
        podcast_name=row.podcast_name,
        episode_title=row.episode_title,
        episode_number=row.episode_number,
        created_time=row.created_time,
        released_at_ms=row.released_at_ms,
        spotify_id=row.spotify_id,
        spotify_url=row.spotify_url,
        spotify_embed_url=row.spotify_embed_url,
        spotify_release_date=row.spotify_release_date,
        spotify_description=row.spotify_description,
        spotify_duration_ms=row.spotify_duration_ms,
        spotify_images=list(row.spotify_images or []),
        mp3_url=row.mp3_url,
        transcript_url=row.transcript_url,
        summary_url=row.summary_url,
        summary_image_url=row.summary_image_url,
        events_markdown_url=row.events_markdown_url,
        sentences_markdown_url=row.sentences_markdown_url,
        marp_markdown_url=row.marp_markdown_url,
        ticker_marp_markdown_url=row.ticker_marp_markdown_url,
        ticker_insights_url=row.ticker_recommendations_url,
        summary_content=row.summary_content,
        key_insights=list(row.key_insights or []),
        events_markdown_content=row.events_markdown_content,
        sentences_markdown_content=row.sentences_markdown_content,
        marp_markdown_content=row.marp_markdown_content,
        ticker_marp_markdown_content=row.ticker_marp_markdown_content,
        ticker_insights_content=row.ticker_recommendations_content,
        related_tickers=list(row.related_tickers or []),
        tags=list(row.tags or []),
        num_likes=row.num_likes or 0,
        number_click=row.number_click or 0,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _row_to_podcast(row: sa.Row) -> Podcast:
    return Podcast(
        name=row.name,
        spotify_show_link=row.spotify_show_link,
        description=row.description,
        thumbnail_url=row.thumbnail_url,
        language=row.language or "zh",
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _row_to_ticker(row: sa.Row) -> Ticker:
    return Ticker(
        symbol=row.symbol,
        canonical=row.canonical,
        name=row.name,
        market=row.market,
        sector=row.sector,
    )


def _row_to_insight(row: sa.Row) -> TickerInsight:
    return TickerInsight(
        episode_id=row.episode_id,
        ticker=row.ticker,
        schema_version=row.schema_version or 3,
        bluf_thesis=row.bluf_thesis,
        time_horizon=row.time_horizon,
        sentiment_label=row.sentiment_label,
        sentiment_score=row.sentiment_score,
        reasons=list(row.reasons or []),
        risks=list(row.risks or []),
        podcaster=row.podcaster,
        podcast_launch_time=row.podcast_launch_time,
        created_at=row.created_at,
    )


def _row_to_trending(row: sa.Row) -> TrendingTicker:
    return TrendingTicker(
        ticker=row.ticker,
        schema_version=row.schema_version or 3,
        count_30d=row.count_30d or 0,
        count_90d=row.count_90d or 0,
        count_all_time=row.count_all_time or 0,
        sentiment_label=row.sentiment_label,
        sentiment_score=row.sentiment_score,
        last_mentioned=row.last_mentioned,
        top_podcasters=list(row.top_podcasters or []),
        top_episodes=list(row.top_episodes or []),
        computed_at=row.computed_at,
    )


# ---------------------------------------------------------------------------
# Postgres implementations
# ---------------------------------------------------------------------------


class PostgresEpisodeRepository(EpisodeRepository):
    def __init__(self, engine: sa.Engine) -> None:
        self._engine = engine

    def upsert(self, episode: Episode) -> Episode:
        now = datetime.now(timezone.utc)
        values = dict(
            id=episode.id,
            podcast_name=episode.podcast_name,
            episode_title=episode.episode_title,
            episode_number=episode.episode_number,
            created_time=episode.created_time,
            released_at_ms=episode.released_at_ms,
            spotify_id=episode.spotify_id,
            spotify_url=episode.spotify_url,
            spotify_embed_url=episode.spotify_embed_url,
            spotify_release_date=episode.spotify_release_date,
            spotify_description=episode.spotify_description,
            spotify_duration_ms=episode.spotify_duration_ms,
            spotify_images=episode.spotify_images or [],
            mp3_url=episode.mp3_url,
            transcript_url=episode.transcript_url,
            summary_url=episode.summary_url,
            summary_image_url=episode.summary_image_url,
            events_markdown_url=episode.events_markdown_url,
            sentences_markdown_url=episode.sentences_markdown_url,
            marp_markdown_url=episode.marp_markdown_url,
            ticker_marp_markdown_url=episode.ticker_marp_markdown_url,
            ticker_recommendations_url=episode.ticker_insights_url,
            summary_content=episode.summary_content,
            key_insights=episode.key_insights or [],
            events_markdown_content=episode.events_markdown_content,
            sentences_markdown_content=episode.sentences_markdown_content,
            marp_markdown_content=episode.marp_markdown_content,
            ticker_marp_markdown_content=episode.ticker_marp_markdown_content,
            ticker_recommendations_content=episode.ticker_insights_content,
            related_tickers=episode.related_tickers or [],
            tags=episode.tags or [],
            num_likes=episode.num_likes,
            number_click=episode.number_click,
            updated_at=now,
        )
        stmt = (
            pg_insert(episodes_table)
            .values(**values, created_at=now)
            .on_conflict_do_update(
                index_elements=["id"],
                set_={k: v for k, v in values.items() if k not in ("id", "podcast_name", "created_time")},
            )
        )
        with self._engine.begin() as conn:
            conn.execute(stmt)
        return self.get(episode.id) or episode  # type: ignore[return-value]

    def get(self, episode_id: str) -> Optional[Episode]:
        with self._engine.connect() as conn:
            row = conn.execute(
                sa.select(episodes_table).where(episodes_table.c.id == episode_id)
            ).first()
        return _row_to_episode(row) if row else None

    def list_recent(self, *, limit: int = 20, offset: int = 0) -> list[Episode]:
        stmt = (
            sa.select(episodes_table)
            .order_by(episodes_table.c.created_time.desc().nullslast())
            .limit(limit)
            .offset(offset)
        )
        with self._engine.connect() as conn:
            rows = conn.execute(stmt).fetchall()
        return [_row_to_episode(r) for r in rows]

    def list_by_podcast(
        self, podcast_name: str, *, limit: int = 20, offset: int = 0
    ) -> list[Episode]:
        stmt = (
            sa.select(episodes_table)
            .where(episodes_table.c.podcast_name == podcast_name)
            .order_by(episodes_table.c.created_time.desc().nullslast())
            .limit(limit)
            .offset(offset)
        )
        with self._engine.connect() as conn:
            rows = conn.execute(stmt).fetchall()
        return [_row_to_episode(r) for r in rows]

    def list_by_ticker(self, ticker: str, *, limit: int = 20) -> list[Episode]:
        stmt = (
            sa.select(episodes_table)
            .where(episodes_table.c.related_tickers.contains(sa.cast([ticker], ARRAY(_Text))))
            .order_by(episodes_table.c.created_time.desc().nullslast())
            .limit(limit)
        )
        with self._engine.connect() as conn:
            rows = conn.execute(stmt).fetchall()
        return [_row_to_episode(r) for r in rows]

    def list_by_tag(self, tag: str, *, limit: int = 20) -> list[Episode]:
        stmt = (
            sa.select(episodes_table)
            .where(episodes_table.c.tags.contains(sa.cast([tag], ARRAY(_Text))))
            .order_by(episodes_table.c.created_time.desc().nullslast())
            .limit(limit)
        )
        with self._engine.connect() as conn:
            rows = conn.execute(stmt).fetchall()
        return [_row_to_episode(r) for r in rows]

    def count(self) -> int:
        with self._engine.connect() as conn:
            return conn.execute(sa.select(sa.func.count()).select_from(episodes_table)).scalar() or 0

    def list_all_tags(self) -> list[tuple[str, int]]:
        stmt = sa.text(
            "SELECT tag, COUNT(*) AS cnt"
            " FROM episodes, UNNEST(tags) AS tag"
            " WHERE tag IS NOT NULL AND tag <> ''"
            " GROUP BY tag ORDER BY cnt DESC"
        )
        with self._engine.connect() as conn:
            rows = conn.execute(stmt).fetchall()
        return [(r[0], r[1]) for r in rows]


class PostgresPodcastRepository(PodcastRepository):
    def __init__(self, engine: sa.Engine) -> None:
        self._engine = engine

    def upsert(self, podcast: Podcast) -> Podcast:
        now = datetime.now(timezone.utc)
        values = dict(
            name=podcast.name,
            spotify_show_link=podcast.spotify_show_link,
            description=podcast.description,
            thumbnail_url=podcast.thumbnail_url,
            language=podcast.language or "zh",
            updated_at=now,
        )
        stmt = (
            pg_insert(podcasts_table)
            .values(**values, created_at=now)
            .on_conflict_do_update(
                index_elements=["name"],
                set_={k: v for k, v in values.items() if k != "name"},
            )
        )
        with self._engine.begin() as conn:
            conn.execute(stmt)
        return self.get(podcast.name) or podcast  # type: ignore[return-value]

    def get(self, name: str) -> Optional[Podcast]:
        with self._engine.connect() as conn:
            row = conn.execute(
                sa.select(podcasts_table).where(podcasts_table.c.name == name)
            ).first()
        return _row_to_podcast(row) if row else None

    def list_all(self) -> list[Podcast]:
        with self._engine.connect() as conn:
            rows = conn.execute(sa.select(podcasts_table).order_by(podcasts_table.c.name)).fetchall()
        return [_row_to_podcast(r) for r in rows]


class PostgresTickerRepository(TickerRepository):
    def __init__(self, engine: sa.Engine) -> None:
        self._engine = engine

    def upsert(self, ticker: Ticker) -> Ticker:
        stmt = (
            pg_insert(tickers_table)
            .values(symbol=ticker.symbol, canonical=ticker.canonical, name=ticker.name, market=ticker.market, sector=ticker.sector)
            .on_conflict_do_update(
                index_elements=["symbol"],
                set_=dict(canonical=ticker.canonical, name=ticker.name, market=ticker.market, sector=ticker.sector),
            )
        )
        with self._engine.begin() as conn:
            conn.execute(stmt)
        return ticker

    def get(self, symbol: str) -> Optional[Ticker]:
        with self._engine.connect() as conn:
            row = conn.execute(
                sa.select(tickers_table).where(tickers_table.c.symbol == symbol)
            ).first()
        return _row_to_ticker(row) if row else None

    def list_all(self) -> list[Ticker]:
        with self._engine.connect() as conn:
            rows = conn.execute(sa.select(tickers_table).order_by(tickers_table.c.symbol)).fetchall()
        return [_row_to_ticker(r) for r in rows]


class PostgresTickerInsightRepository(TickerInsightRepository):
    def __init__(self, engine: sa.Engine) -> None:
        self._engine = engine

    def upsert(self, insight: TickerInsight) -> TickerInsight:
        now = datetime.now(timezone.utc)
        values = dict(
            episode_id=insight.episode_id,
            ticker=insight.ticker,
            schema_version=insight.schema_version,
            bluf_thesis=insight.bluf_thesis,
            time_horizon=insight.time_horizon,
            sentiment_label=insight.sentiment_label,
            sentiment_score=insight.sentiment_score,
            reasons=insight.reasons or [],
            risks=insight.risks or [],
            podcaster=insight.podcaster,
            podcast_launch_time=insight.podcast_launch_time,
            created_at=insight.created_at or now,
        )
        stmt = (
            pg_insert(ticker_insights_table)
            .values(**values)
            .on_conflict_do_update(
                index_elements=["episode_id", "ticker"],
                set_={k: v for k, v in values.items() if k not in ("episode_id", "ticker", "created_at")},
            )
        )
        with self._engine.begin() as conn:
            conn.execute(stmt)
        return insight

    def get(self, episode_id: str, ticker: str) -> Optional[TickerInsight]:
        with self._engine.connect() as conn:
            row = conn.execute(
                sa.select(ticker_insights_table).where(
                    (ticker_insights_table.c.episode_id == episode_id)
                    & (ticker_insights_table.c.ticker == ticker)
                )
            ).first()
        return _row_to_insight(row) if row else None

    def list_by_ticker(
        self, ticker: str, *, start_date: Optional[str] = None, end_date: Optional[str] = None, limit: int = 100
    ) -> list[TickerInsight]:
        stmt = sa.select(ticker_insights_table).where(ticker_insights_table.c.ticker == ticker)
        if start_date:
            stmt = stmt.where(ticker_insights_table.c.podcast_launch_time >= start_date)
        if end_date:
            stmt = stmt.where(ticker_insights_table.c.podcast_launch_time <= end_date + "Z")
        stmt = stmt.order_by(ticker_insights_table.c.podcast_launch_time.desc().nullslast()).limit(limit)
        with self._engine.connect() as conn:
            rows = conn.execute(stmt).fetchall()
        return [_row_to_insight(r) for r in rows]

    def list_by_podcaster(
        self, podcaster: str, *, start_date: Optional[str] = None, end_date: Optional[str] = None, limit: int = 100
    ) -> list[TickerInsight]:
        stmt = sa.select(ticker_insights_table).where(ticker_insights_table.c.podcaster == podcaster)
        if start_date:
            stmt = stmt.where(ticker_insights_table.c.podcast_launch_time >= start_date)
        if end_date:
            stmt = stmt.where(ticker_insights_table.c.podcast_launch_time <= end_date + "Z")
        stmt = stmt.order_by(ticker_insights_table.c.podcast_launch_time.desc().nullslast()).limit(limit)
        with self._engine.connect() as conn:
            rows = conn.execute(stmt).fetchall()
        return [_row_to_insight(r) for r in rows]

    def list_by_episode(self, episode_id: str) -> list[TickerInsight]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                sa.select(ticker_insights_table).where(ticker_insights_table.c.episode_id == episode_id)
            ).fetchall()
        return [_row_to_insight(r) for r in rows]


class PostgresTrendingTickerRepository(TrendingTickerRepository):
    def __init__(self, engine: sa.Engine) -> None:
        self._engine = engine

    def upsert(self, trending: TrendingTicker) -> TrendingTicker:
        now = datetime.now(timezone.utc)
        values = dict(
            ticker=trending.ticker,
            schema_version=trending.schema_version,
            count_30d=trending.count_30d,
            count_90d=trending.count_90d,
            count_all_time=trending.count_all_time,
            sentiment_label=trending.sentiment_label,
            sentiment_score=trending.sentiment_score,
            last_mentioned=trending.last_mentioned,
            top_podcasters=trending.top_podcasters or [],
            top_episodes=trending.top_episodes or [],
            computed_at=trending.computed_at or now,
        )
        stmt = (
            pg_insert(trending_tickers_table)
            .values(**values)
            .on_conflict_do_update(
                index_elements=["ticker"],
                set_={k: v for k, v in values.items() if k != "ticker"},
            )
        )
        with self._engine.begin() as conn:
            conn.execute(stmt)
        return trending

    def get(self, ticker: str) -> Optional[TrendingTicker]:
        with self._engine.connect() as conn:
            row = conn.execute(
                sa.select(trending_tickers_table).where(trending_tickers_table.c.ticker == ticker)
            ).first()
        return _row_to_trending(row) if row else None

    def list_trending(self, *, days: int = 30, limit: int = 100) -> list[TrendingTicker]:
        col = {
            30: trending_tickers_table.c.count_30d,
            90: trending_tickers_table.c.count_90d,
        }.get(days, trending_tickers_table.c.count_all_time)
        stmt = sa.select(trending_tickers_table).order_by(col.desc()).limit(limit)
        with self._engine.connect() as conn:
            rows = conn.execute(stmt).fetchall()
        return [_row_to_trending(r) for r in rows]
