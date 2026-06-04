"""
SQLAlchemy ORM models for the TinBoker database.
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, JSON, Index, UniqueConstraint
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
