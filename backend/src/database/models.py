"""
SQLAlchemy ORM models for the TinBoker database.
"""

from datetime import datetime
from sqlalchemy import Column, Float, ForeignKey, Integer, String, Text, DateTime, Boolean, JSON, Index, UniqueConstraint
from src.database.postgres import Base


class StockTranslation(Base):
    """
    Model for storing stock ticker translations.
    Supports multiple markets (US, TW, JP) with ZH-TW translations.
    """
    __tablename__ = "stock_translations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(20), nullable=False, index=True)
    market = Column(String(10), nullable=False, index=True)
    name_en = Column(Text, nullable=True)
    name_zh_tw = Column(Text, nullable=True)
    brand_color = Column(String(7), nullable=True)  # Hex color e.g. '#1A2B3C'
    aliases = Column(JSON, nullable=True)  # list[str]: alt names/symbols that resolve to this ticker
    name_preference = Column(
        String(10), nullable=False, default="auto"
    )  # "auto" | "zh_tw" | "en" — display preference; "en" forces English even when a zh name exists
    translation_status = Column(
        String(20),
        nullable=False,
        default="pending",
        index=True
    )  # "pending", "approved", "auto"
    last_updated_by = Column(String(100), nullable=True)
    last_updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("ticker", "market", name="uq_ticker_market"),
        Index("idx_translations_ticker_market", "ticker", "market"),
    )

    def __repr__(self) -> str:
        return f"<StockTranslation(ticker='{self.ticker}', market='{self.market}', name_zh_tw='{self.name_zh_tw}')>"


class ContentSource(Base):
    """
    Operator-maintained registry of followed content sources (podcast shows and
    news RSS feeds). The platform owns this config; the tinboker-agents pipeline
    pulls the active rows via GET /api/sources (see routers/sources.py).

    Unifies two source types in one table:
      - source_type="podcast": uses language, spotify_url, transcript_*
      - source_type="news":    uses region; podcast-only columns stay NULL
    Ingest recency (lookback_days + optional max_episodes cap) applies to both types.
    """
    __tablename__ = "content_sources"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_type = Column(String(20), nullable=False, index=True)  # "podcast" | "news"
    name = Column(Text, nullable=False)
    slug = Column(String(100), nullable=False)
    feed_url = Column(Text, nullable=False)  # RSS/feed URL (podcast "link" / news "url")
    region = Column(String(10), nullable=True, index=True)  # news region: "US" | "TW" | ...
    language = Column(String(10), nullable=True)  # podcast content language: "zh-TW" | "en"
    spotify_url = Column(Text, nullable=True)  # podcast only
    cover_image_url = Column(Text, nullable=True)  # podcast cover art (Spotify show thumbnail, via oEmbed)
    lookback_days = Column(Integer, nullable=True, default=30)  # ingest window: only items newer than N days
    max_episodes = Column(Integer, nullable=True)  # optional safety cap: at most N most-recent items per run
    transcript_service = Column(String(20), nullable=True)  # podcast only: groq|whisper|openai
    transcript_model = Column(String(50), nullable=True)  # podcast only: e.g. whisper-large-v3
    active = Column(Boolean, nullable=False, default=True, index=True)
    extra = Column(JSON, nullable=True)  # type-specific overflow / future-proofing
    last_updated_by = Column(String(100), nullable=True)
    last_updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("source_type", "slug", name="uq_source_type_slug"),
        Index("idx_content_sources_type_active", "source_type", "active"),
    )

    def __repr__(self) -> str:
        return f"<ContentSource(type='{self.source_type}', slug='{self.slug}', active={self.active})>"


class Article(Base):
    """
    Platform-owned articles authored by admins (Phase 1) or registered authors (Phase 4).
    Body is stored inline for MVP; GCS offloading is a future optimisation.
    """
    __tablename__ = "articles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    slug = Column(String(255), nullable=False, unique=True, index=True)
    title = Column(Text, nullable=False)
    subtitle = Column(Text, nullable=True)
    author_id = Column(String(255), nullable=False)
    author_name = Column(String(255), nullable=False)
    author_avatar = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="draft", index=True)
    cover_image_url = Column(Text, nullable=True)
    body_content = Column(Text, nullable=False, default="")
    key_points = Column(JSON, nullable=True)
    tags = Column(JSON, nullable=True)
    tickers = Column(JSON, nullable=True)
    read_minutes = Column(Integer, nullable=True)
    view_count = Column(Integer, nullable=False, default=0)
    published_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_articles_status_published", "status", "published_at"),
    )

    def __repr__(self) -> str:
        return f"<Article(slug='{self.slug}', status='{self.status}')>"


class ArticleTag(Base):
    """Inverted index: tag -> article for discovery queries."""
    __tablename__ = "article_tags"

    id = Column(Integer, primary_key=True, autoincrement=True)
    article_id = Column(Integer, ForeignKey("articles.id", ondelete="CASCADE"), nullable=False)
    tag = Column(String(100), nullable=False)

    __table_args__ = (
        UniqueConstraint("article_id", "tag", name="uq_article_tag"),
        Index("idx_article_tags_tag", "tag"),
    )


class ArticleTicker(Base):
    """Inverted index: ticker -> article for stock page cross-links."""
    __tablename__ = "article_tickers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    article_id = Column(Integer, ForeignKey("articles.id", ondelete="CASCADE"), nullable=False)
    ticker = Column(String(20), nullable=False)

    __table_args__ = (
        UniqueConstraint("article_id", "ticker", name="uq_article_ticker"),
        Index("idx_article_tickers_ticker", "ticker"),
    )


class StockDailyClose(Base):
    """Permanent store for historical daily closing prices.

    Once a trading day ends, the close is immutable — storing it in the DB
    means we never need to re-fetch from FinMind/Massive for the same
    (ticker, date) pair.
    """
    __tablename__ = "stock_daily_closes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(20), nullable=False)
    date = Column(String(10), nullable=False)  # YYYY-MM-DD
    close = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("ticker", "date", name="uq_ticker_date"),
        Index("idx_daily_close_ticker_date", "ticker", "date"),
    )


class StockProfile(Base):
    """Warmed slow-moving company facts for US stocks.

    Company profiles + logos barely change, yet they were being re-fetched from
    Massive/Polygon (~5 req/min) on a 1-hour TTL per ticker — the single biggest source
    of upstream 429s. A background warmer keeps this table fresh (profile + P/E from
    yfinance, logo from Massive once) so request paths read from Postgres instead.
    """

    __tablename__ = "stock_profiles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(20), nullable=False, unique=True, index=True)
    name = Column(Text, nullable=True)
    market_cap = Column(Float, nullable=True)
    sector = Column(String(100), nullable=True)
    industry = Column(String(200), nullable=True)
    pe = Column(Float, nullable=True)
    dividend_yield = Column(Float, nullable=True)
    currency = Column(String(10), nullable=True)
    description = Column(Text, nullable=True)
    logo_url = Column(Text, nullable=True)
    icon_url = Column(Text, nullable=True)
    logo_image = Column(Text, nullable=True)  # base64 SVG (auth-gated upstream)
    icon_image = Column(Text, nullable=True)  # base64 PNG
    source = Column(String(20), nullable=True)  # provider that produced the profile fields
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)


class StockDailyOHLC(Base):
    """Warmed full daily OHLCV bars for US stocks (chart data).

    Sibling to ``stock_daily_closes`` (which stays close-only for the lightweight change%
    path). Filled by the warmer from yfinance — no per-key rate cap — so the per-request
    chart path can read from Postgres instead of hitting Massive's aggregates endpoint.
    """

    __tablename__ = "stock_daily_ohlc"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(20), nullable=False)
    date = Column(String(10), nullable=False)  # YYYY-MM-DD
    open = Column(Float, nullable=True)
    high = Column(Float, nullable=True)
    low = Column(Float, nullable=True)
    close = Column(Float, nullable=False)
    volume = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("ticker", "date", name="uq_ohlc_ticker_date"),
        Index("idx_ohlc_ticker_date", "ticker", "date"),
    )


class TagRegistry(Base):
    """Admin-managed tag registry.

    tier='trending' → shown in topics cloud; tier='hidden' → not shown.
    Auto-discovered tags from Firestore default to 'hidden'.
    """
    __tablename__ = "tag_registry"

    id = Column(Integer, primary_key=True, autoincrement=True)
    slug = Column(String(100), nullable=False, unique=True, index=True)
    display_zh = Column(Text, nullable=False)
    tier = Column(String(20), nullable=False, default="trending", index=True)
    updated_by = Column(String(100), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<TagRegistry(slug='{self.slug}', tier='{self.tier}')>"


class PipelineConfigOverride(Base):
    """Admin-editable pipeline config overrides.

    Stores a single row (namespace='default') with JSON overrides that the
    pipeline merges on top of its code defaults at each run start. The admin
    page writes here via PUT /api/admin/pipeline-settings.
    """
    __tablename__ = "pipeline_config_overrides"

    id = Column(Integer, primary_key=True, autoincrement=True)
    namespace = Column(String(50), nullable=False, unique=True, default="default")
    overrides = Column(JSON, nullable=False, default=dict)
    updated_by = Column(String(100), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
