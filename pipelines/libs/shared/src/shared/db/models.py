"""Dataclasses for the consolidated content store (Phase B of data-consolidation-plan.md).

These mirror the Firestore document shapes defined in docs/spec-from-platform.md but are
storage-agnostic — no Firestore or SQLAlchemy types appear here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


@dataclass
class Podcast:
    name: str  # PK — stable identifier; renaming breaks platform subscriptions
    spotify_show_link: Optional[str] = None
    description: Optional[str] = None
    thumbnail_url: Optional[str] = None
    language: str = "zh"  # "zh" | "en"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class Episode:
    """One podcast episode.  Maps to the Firestore ``episodes/{id}`` shape (§ 2 spec)."""

    id: str  # PK — stable, opaque (e.g. "gooaye-股癌_ep566")
    podcast_name: str  # FK -> podcasts.name

    # Content identity
    episode_title: Optional[str] = None
    episode_number: Optional[int] = None

    # Timestamps
    created_time: Optional[int] = None  # Unix ms — immutable after first write (§ 2.1)
    released_at_ms: Optional[int] = None  # Unix ms derived from spotify_release_date (§ 2.3 #1)

    # Spotify metadata
    spotify_id: Optional[str] = None
    spotify_url: Optional[str] = None
    spotify_embed_url: Optional[str] = None
    spotify_release_date: Optional[str] = None  # YYYY-MM-DD string (§ 2.3 #5)
    spotify_description: Optional[str] = None
    spotify_duration_ms: Optional[int] = None
    spotify_images: list[str] = field(default_factory=list)

    # File URLs (GCS gs:// or VPS /media/ paths post Phase E)
    mp3_url: Optional[str] = None
    transcript_url: Optional[str] = None
    summary_url: Optional[str] = None
    summary_image_url: Optional[str] = None
    events_markdown_url: Optional[str] = None
    sentences_markdown_url: Optional[str] = None
    marp_markdown_url: Optional[str] = None
    ticker_marp_markdown_url: Optional[str] = None
    ticker_insights_url: Optional[str] = None

    # Inlined content cache (duplicates GCS content; must be kept in sync on re-gen § 2.3 #4)
    summary_content: Optional[str] = None
    key_insights: list[str] = field(default_factory=list)
    events_markdown_content: Optional[str] = None
    sentences_markdown_content: Optional[str] = None
    marp_markdown_content: Optional[str] = None
    ticker_marp_markdown_content: Optional[str] = None
    ticker_insights_content: Optional[str] = None

    # Categorisation
    related_tickers: list[str] = field(default_factory=list)  # symbol-only, mixed TW/US
    tags: list[str] = field(default_factory=list)

    # Engagement (seeded at 0; platform increments)
    num_likes: int = 0
    number_click: int = 0

    # DB timestamps
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class Ticker:
    """Registry of known ticker symbols.  Folded in from tickers.json."""

    symbol: str  # PK — canonical upper-case symbol (e.g. "NVDA", "2330")
    canonical: Optional[str] = None  # display form if different from symbol
    name: Optional[str] = None  # human name e.g. "NVIDIA Corporation"
    market: Optional[str] = None  # "US" | "TW" | "HK" | ...
    sector: Optional[str] = None


@dataclass
class TickerInsight:
    """Per-episode, per-ticker insight doc.  Matches spec § 4 (schema_version 3)."""

    episode_id: str  # PK part 1, FK -> episodes.id
    ticker: str  # PK part 2, FK -> tickers.symbol

    schema_version: int = 3

    bluf_thesis: Optional[str] = None
    time_horizon: Optional[str] = None  # 短期 | 中期 | 長期

    # Sentiment — score is INTERNAL ONLY; never returned by the public API (§ 4.2)
    sentiment_label: Optional[str] = None  # STRONG_BULLISH | BULLISH | NEUTRAL | BEARISH | STRONG_BEARISH
    sentiment_score: Optional[float] = None  # 0.0–1.0, internal sort key only

    reasons: list[dict[str, Any]] = field(default_factory=list)  # JSONB
    risks: list[dict[str, Any]] = field(default_factory=list)  # JSONB

    podcaster: Optional[str] = None
    podcast_launch_time: Optional[str] = None  # ISO 8601 UTC

    created_at: Optional[datetime] = None


@dataclass
class TrendingTicker:
    """Nightly aggregate per ticker.  Matches spec § 5 (schema_version 3)."""

    ticker: str  # PK, FK -> tickers.symbol

    schema_version: int = 3

    count_30d: int = 0
    count_90d: int = 0
    count_all_time: int = 0

    # Aggregated sentiment (score internal only — § 4.2)
    sentiment_label: Optional[str] = None
    sentiment_score: Optional[float] = None

    last_mentioned: Optional[str] = None  # ISO 8601 UTC

    top_podcasters: list[dict[str, Any]] = field(default_factory=list)  # JSONB
    top_episodes: list[dict[str, Any]] = field(default_factory=list)  # JSONB

    computed_at: Optional[datetime] = None
