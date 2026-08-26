"""
SQLAlchemy ORM models for the TinBoker database.
"""

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP

from src.database.postgres import Base

JSON_VARIANT = JSON().with_variant(JSONB, "postgresql")
TZ_DATETIME = DateTime(timezone=True).with_variant(TIMESTAMP(timezone=True), "postgresql")


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
    cover_image_url = Column(Text, nullable=True)  # podcast cover art on our media host (mirrored from Spotify at ingest)
    lookback_days = Column(Integer, nullable=True, default=30)  # ingest window: only items newer than N days
    max_episodes = Column(Integer, nullable=True)  # optional safety cap: at most N most-recent items per run
    transcript_service = Column(String(20), nullable=True)  # podcast only: groq|whisper|openai
    transcript_model = Column(String(50), nullable=True)  # podcast only: e.g. whisper-large-v3
    active = Column(Boolean, nullable=False, default=True, index=True)
    # Per-show outbound-publishing kill switch: when False, this show's episodes are
    # never pushed to any external platform (Threads, Facebook, 方格子, Substack).
    # Independent of `active` — we keep ingesting the show and it still feeds the site,
    # we just stop publishing about it anywhere else.
    social_enabled = Column(Boolean, nullable=False, default=True)
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
    """Warmed whole-market daily OHLCV + 成交金額 bars.

    Sibling to ``stock_daily_closes`` (which stays close-only for the lightweight change%
    path). Populated by ``tw_daily_ohlc_refresh`` from the official TWSE/TPEx OpenAPI
    whole-market feeds (2 free calls/day, no key) so the request path — /topics money-flow
    windows and stock charts — reads daily bars from Postgres instead of fanning out
    hundreds of per-ticker FinMind calls. ``trading_value`` (成交金額, NT$) is what the
    bubble chart sizes on; ``source`` records which feed produced the row (twse/tpex).
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
    trading_value = Column(Float, nullable=True)  # 成交金額 NT$ (bubble-chart size)
    source = Column(String(20), nullable=True)    # twse | tpex
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("ticker", "date", name="uq_ohlc_ticker_date"),
        Index("idx_ohlc_ticker_date", "ticker", "date"),
    )


class StockInstitutionalDaily(Base):
    """Warmed whole-market daily 三大法人 (institutional) net-buy shares.

    Populated by ``tw_daily_ohlc_refresh`` from the official keyless feeds — TWSE T86
    (上市, historical/backfillable) + TPEx OpenAPI 3insti (上櫃, today-forward). Stores NET
    SHARES per stock/day; the /topics money-flow windows convert to NT$ at read time using
    the latest close from ``stock_daily_ohlc``. Replaces the per-ticker FinMind fan-out
    (the other half of the /topics call storm).
    """

    __tablename__ = "stock_institutional_daily"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(20), nullable=False)
    date = Column(String(10), nullable=False)  # YYYY-MM-DD
    foreign_net_shares = Column(Float, nullable=True)  # 外資 (incl. foreign dealer) net shares
    trust_net_shares = Column(Float, nullable=True)    # 投信 (investment trust) net shares
    total_net_shares = Column(Float, nullable=True)    # 三大法人 net shares
    source = Column(String(20), nullable=True)         # twse | tpex
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("ticker", "date", name="uq_insti_ticker_date"),
        Index("idx_insti_ticker_date", "ticker", "date"),
    )


class ScreenerCandidate(Base):
    """Ranked whole-market TW anomaly-screener output for one trading day.

    Written by ``screener_refresh`` — ALL Stage-1 passers for a date (not a Top-N
    cut), scored cross-sectionally within that day's pool. Re-running a date
    overwrites its rows (idempotent on ``(date, ticker)``).
    """

    __tablename__ = "screener_candidates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(String(10), nullable=False)  # YYYY-MM-DD
    ticker = Column(String(20), nullable=False)
    rank = Column(Integer, nullable=False)  # 1 = highest final_score
    final_score = Column(Float, nullable=False)
    momentum_score = Column(Float, nullable=False)
    institution_score = Column(Float, nullable=False)
    # Raw sub-metrics: close_ma20, close_ma60, vol_mult, institution_raw,
    # price_pos_60d, ret_5d, ma20, ma60, high_20, high_60, today_volume, etc.
    factors = Column(JSON, nullable=True)
    is_60d_high = Column(Boolean, nullable=False, default=False)
    crowded = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("date", "ticker", name="uq_screener_date_ticker"),
        Index("idx_screener_date_rank", "date", "rank"),
    )

    def __repr__(self) -> str:
        return f"<ScreenerCandidate(date='{self.date}', ticker='{self.ticker}', rank={self.rank})>"


class TagRegistry(Base):
    """Admin-managed topic registry — the unified index of tags AND sectors/themes.

    tier='trending' → shown in topics cloud; tier='hidden' → not shown.
    Auto-discovered tags from Firestore default to 'hidden'.

    kind discriminates the two topic flavours that share this index:
      'tag'    → free-form extraction tags (full admin CRUD; this is the default).
      'sector' → sector/theme exposures authored through the admin taxonomy API.
    Sector rows carry the universe identity (exposure_id) and display visuals
    (icon_id, color_hex) so the admin list can render them without a universe lookup.
    redirect_to marks a retired/merged exposure row; canonical rows leave it NULL.
    """
    __tablename__ = "tag_registry"

    id = Column(Integer, primary_key=True, autoincrement=True)
    slug = Column(String(100), nullable=False, unique=True, index=True)
    display_zh = Column(Text, nullable=False)
    tier = Column(String(20), nullable=False, default="trending", index=True)
    kind = Column(String(20), nullable=False, default="tag", index=True)
    exposure_id = Column(String(120), nullable=True, index=True)
    exposure_type = Column(String(20), nullable=True)
    icon_id = Column(String(64), nullable=True)
    color_hex = Column(String(16), nullable=True)
    description = Column(Text, nullable=True)
    members = Column(JSON_VARIANT, nullable=True)
    aliases = Column(JSON_VARIANT, nullable=True)
    field_owners = Column(JSON_VARIANT, nullable=True)
    # For 'sector' rows of exposure_type='theme': the parent industry exposure_id.
    # Lets industry discussion-heat be derived by aggregating its child themes.
    parent_id = Column(String(120), nullable=True, index=True)
    redirect_to = Column(String(120), nullable=True, index=True)
    updated_by = Column(String(100), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<TagRegistry(slug='{self.slug}', kind='{self.kind}', tier='{self.tier}')>"


class TaxonomyDraft(Base):
    """Drafted bulk taxonomy payload awaiting explicit publish."""

    __tablename__ = "taxonomy_drafts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    status = Column(String(20), nullable=False, default="draft", index=True)
    payload = Column(JSON_VARIANT, nullable=False)
    diff = Column(JSON_VARIANT, nullable=True)
    actor = Column(String(100), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    published_at = Column(DateTime, nullable=True)


class TaxonomyVersion(Base):
    """Single-row structural taxonomy version counter."""

    __tablename__ = "taxonomy_version"

    id = Column(Integer, primary_key=True, default=1)
    version = Column(Integer, nullable=False, default=0)
    updated_by = Column(String(100), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TaxonomyChangelog(Base):
    """Dated changelog entries for structural taxonomy changes."""

    __tablename__ = "taxonomy_changelog"

    id = Column(Integer, primary_key=True, autoincrement=True)
    version = Column(Integer, nullable=False, index=True)
    entry = Column(Text, nullable=False)
    rationale = Column(Text, nullable=True)
    actor = Column(String(100), nullable=False)
    at = Column(TZ_DATETIME, default=datetime.utcnow, nullable=False)


class TagRegistryAudit(Base):
    """Trigger-written audit snapshots for tag_registry sector taxonomy writes."""

    __tablename__ = "tag_registry_audit"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tag_registry_id = Column(Integer, nullable=True, index=True)
    exposure_id = Column(String(120), nullable=True, index=True)
    action = Column(String(10), nullable=False, index=True)
    actor = Column(String(100), nullable=False, default="unknown", index=True)
    note = Column(Text, nullable=True)
    before = Column("before", JSON_VARIANT, nullable=True)
    after = Column("after", JSON_VARIANT, nullable=True)
    at = Column(TZ_DATETIME, default=datetime.utcnow, nullable=False, index=True)


class AnalyticsSnapshot(Base):
    """Daily point-in-time audience snapshot, for follower/fan growth charts.

    Meta's APIs return only the *current* follower/fan count (no history), so we record
    them once a day (cron → POST /api/admin/analytics/snapshot) and chart the
    accumulation. One row per UTC day (``day`` unique, upserted). Shared across envs
    (one Postgres), so it doesn't matter which env's cron writes it.
    """
    __tablename__ = "analytics_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    day = Column(String(10), nullable=False, unique=True, index=True)  # YYYY-MM-DD (UTC)
    threads_followers = Column(Integer, nullable=True)
    fb_followers = Column(Integer, nullable=True)
    fb_fans = Column(Integer, nullable=True)
    captured_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<AnalyticsSnapshot(day={self.day}, th={self.threads_followers}, fb={self.fb_followers})>"


class PromoDraft(Base):
    """A saved draft for the admin promo cross-poster (free-form Threads/FB post).

    Durable + shared across envs (all share this Postgres). ``media`` stores each item
    as ``{type, path, filename}`` where ``path`` is the permanent media-store location,
    so a draft's media never expires; the read path resolves it to a fetchable URL on
    load. ``comments`` is a list of text-only follow-ups; ``platforms`` the selected
    targets.
    """
    __tablename__ = "promo_drafts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False, default="未命名草稿")
    text = Column(Text, nullable=False, default="")
    media = Column(JSON, nullable=False, default=list)
    comments = Column(JSON, nullable=False, default=list)
    platforms = Column(JSON, nullable=False, default=list)
    updated_by = Column(String(100), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<PromoDraft(id={self.id}, name='{self.name}')>"


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


class ScheduledSocialPost(Base):
    """
    A scheduled social media post (either an episode publish or a free-form promo).
    """
    __tablename__ = "scheduled_social_posts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    post_type = Column(String(50), nullable=False)  # "episode" | "promo"
    episode_id = Column(String(255), nullable=True)  # for episode posts

    # Post content snapshot
    text = Column(Text, nullable=False, default="")
    media = Column(JSON, nullable=False, default=list)  # [{type, path, filename, url}]
    comments = Column(JSON, nullable=False, default=list)  # for promo: [str], for episode: [{heading, text}]
    platforms = Column(JSON, nullable=False, default=list)  # ["threads", "facebook"]

    # Scheduling & status
    scheduled_for = Column(DateTime, nullable=False, index=True)
    status = Column(String(20), nullable=False, default="pending", index=True)  # "pending", "processing", "posted", "failed"
    error_message = Column(Text, nullable=True)
    posted_at = Column(DateTime, nullable=True)
    published_results = Column(JSON, nullable=True)  # response log from Meta APIs

    created_by = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<ScheduledSocialPost(id={self.id}, type='{self.post_type}', status='{self.status}', scheduled_for='{self.scheduled_for}')>"


class ContentMention(Base):
    """One ticker or sector mention extracted from a podcast episode (TKB-001).

    Rows are derived by the mention-sync job from the pipeline-written
    ticker_insights table (ticker mentions) and episode sector_exposures
    (sector mentions). `mention_key` makes the upsert idempotent — nullable
    ticker/exposure_id columns can't carry a Postgres unique constraint.
    """

    __tablename__ = "content_mentions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    mention_key = Column(String(500), nullable=False, unique=True)  # "{episode_id}:{mention_type}:{ticker|exposure_id}"
    episode_id = Column(String(255), nullable=False, index=True)
    source_type = Column(String(20), nullable=False, default="podcast")
    podcaster = Column(String(255), nullable=True)
    mention_type = Column(String(10), nullable=False, index=True)  # "ticker" | "sector"
    ticker = Column(String(20), nullable=True, index=True)  # canonical symbol, ticker mentions only
    exposure_id = Column(String(100), nullable=True, index=True)  # sector mentions only
    display_name = Column(Text, nullable=True)
    market = Column(String(10), nullable=True)  # "TW" | "US" | "KR" (ticker mentions)
    mentioned_at = Column(DateTime, nullable=False, index=True)  # episode release time (UTC)
    mention_start_s = Column(Float, nullable=True)  # offset within the episode, when available
    confidence = Column(Float, nullable=False, default=1.0)
    extraction_method = Column(String(50), nullable=False)  # "pipeline_llm" | "alias_match"
    sentiment_label = Column(String(20), nullable=True)
    thesis = Column(Text, nullable=True)
    payload = Column(JSON, nullable=True)  # extras: resolved member tickers, mention_text, ...
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_mentions_ticker_date", "ticker", "mentioned_at"),
        Index("idx_mentions_exposure_date", "exposure_id", "mentioned_at"),
    )


class TickerPerformanceSnapshot(Base):
    """Post-mention returns for one ticker mention (TKB-001).

    rNd = close on the Nth trading day after the baseline close (the last close
    on/before the mention date), as a percent. A window stays NULL until it has
    elapsed and the closes exist in stock_daily_closes; the sync job recomputes
    until all windows fill.
    """

    __tablename__ = "ticker_performance_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    mention_id = Column(Integer, ForeignKey("content_mentions.id", ondelete="CASCADE"), nullable=False, unique=True)
    ticker = Column(String(20), nullable=False, index=True)
    mention_date = Column(String(10), nullable=False)  # YYYY-MM-DD
    baseline_close = Column(Float, nullable=True)
    r1d = Column(Float, nullable=True)
    r5d = Column(Float, nullable=True)
    r20d = Column(Float, nullable=True)
    r60d = Column(Float, nullable=True)
    computed_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SectorPerformanceSnapshot(Base):
    """Post-mention returns for one sector mention: equal-weight average of the
    exposure's resolved member tickers that have close data (TKB-001)."""

    __tablename__ = "sector_performance_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    mention_id = Column(Integer, ForeignKey("content_mentions.id", ondelete="CASCADE"), nullable=False, unique=True)
    exposure_id = Column(String(100), nullable=False, index=True)
    mention_date = Column(String(10), nullable=False)  # YYYY-MM-DD
    member_count = Column(Integer, nullable=False, default=0)  # members with close data
    r1d = Column(Float, nullable=True)
    r5d = Column(Float, nullable=True)
    r20d = Column(Float, nullable=True)
    r60d = Column(Float, nullable=True)
    computed_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class User(Base):
    """A registered member (was Firestore ``users/{user_id}``, P3 of the Firestore exit).

    The five subscription arrays and the preferences map stay JSON rather than becoming
    child tables: every read wants the whole set at once, every write is a single
    add/remove on one user, and the population is ~40 rows. A join buys nothing here.
    ponytail: JSON arrays, normalise if per-ticker fan-in queries ever need an index.
    """
    __tablename__ = "users"

    id = Column(String(64), primary_key=True)  # uuid4, was the Firestore doc id
    google_id = Column(String(64), nullable=False, unique=True, index=True)
    email = Column(String(320), nullable=False, index=True)
    name = Column(String(200), nullable=False, default="")
    avatar = Column(Text, nullable=True)  # https URL or data:image/... URI (~300KB cap)
    email_verified = Column(Boolean, nullable=False, default=False)
    created_at = Column(TZ_DATETIME, nullable=True)
    updated_at = Column(TZ_DATETIME, nullable=True)

    watchlist = Column(JSON_VARIANT, nullable=False, default=list)  # tickers
    podcast_subscriptions = Column(JSON_VARIANT, nullable=False, default=list)
    episode_bookmarks = Column(JSON_VARIANT, nullable=False, default=list)  # "{podcast}_{ep}"
    alerts = Column(JSON_VARIANT, nullable=False, default=list)
    tag_subscriptions = Column(JSON_VARIANT, nullable=False, default=list)
    notification_preferences = Column(JSON_VARIANT, nullable=False, default=dict)

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email='{self.email}')>"


class UserNotification(Base):
    """In-app notification (was the Firestore ``users/{id}/notifications`` subcollection)."""
    __tablename__ = "user_notifications"

    id = Column(String(64), primary_key=True)  # uuid4
    user_id = Column(String(64), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    type = Column(String(32), nullable=False)
    title = Column(Text, nullable=False, default="")
    body = Column(Text, nullable=False, default="")
    data = Column(JSON_VARIANT, nullable=False, default=dict)
    is_read = Column(Boolean, nullable=False, default=False)
    created_at = Column(TZ_DATETIME, nullable=False, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        # Every query is "this user's inbox, newest first" or "…unread only".
        Index("idx_user_notifications_user_created", "user_id", "created_at"),
        Index("idx_user_notifications_user_unread", "user_id", "is_read"),
    )

    def __repr__(self) -> str:
        return f"<UserNotification(id={self.id}, user_id={self.user_id}, read={self.is_read})>"


class SocialPostLedger(Base):
    """Which episodes have already been posted, per platform (idempotency ledger).

    Lives in Postgres rather than the container-local SQLite this replaced: that file
    had no volume, so every backend redeploy wiped the ledger and re-posted everything
    still inside the recency window (24 of 63 Threads posts in Aug 2026). Postgres is
    also shared across dev/staging/prod, which all carry the same publishing tokens —
    one ledger now covers all three.

    The row is inserted *before* posting (see ``social_ledger.claim``), so two
    overlapping triggers cannot both pass the check and double-post.
    """
    __tablename__ = "social_posts"

    platform = Column(String(20), primary_key=True)     # "threads" | "facebook"
    episode_id = Column(String(255), primary_key=True)
    media_id = Column(String(255), nullable=True)       # root post/media id, set after publishing
    url = Column(Text, nullable=True)                   # the episode URL that was posted
    child_ids = Column(JSON, nullable=False, default=list)  # reply/comment ids
    posted_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<SocialPostLedger({self.platform}, {self.episode_id})>"


class ThreadsComment(Base):
    """An external reply on one of our Threads posts, with its triage verdict.

    Only comments actually addressed to us land here: replies aimed at another
    commenter further down the tree are filtered out before insert, as are our own
    reply-chain posts and known bots.
    """
    __tablename__ = "threads_comments"

    id = Column(String(255), primary_key=True)            # the reply's Threads media id
    root_post_id = Column(String(255), nullable=False, index=True)
    replied_to_id = Column(String(255), nullable=True)    # our post/comment it answers
    username = Column(String(255), nullable=True)
    text = Column(Text, nullable=False, default="")
    posted_at = Column(DateTime, nullable=True)           # when the commenter wrote it

    # Triage
    category = Column(String(30), nullable=True)          # praise|question|substantive|hostile|noise|promo|bot
    verdict = Column(String(20), nullable=True)           # auto_reply|needs_review|ignore
    reason = Column(Text, nullable=True)                  # one line, why
    draft = Column(Text, nullable=True)                   # proposed reply, empty when ignoring

    # Outcome
    status = Column(String(20), nullable=False, default="pending", index=True)
    # pending | replied | skipped | ignored | hidden
    reply_media_id = Column(String(255), nullable=True)
    replied_at = Column(DateTime, nullable=True)
    auto = Column(Boolean, nullable=False, default=False)  # sent without human review

    synced_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<ThreadsComment({self.id}, {self.category}, {self.status})>"
