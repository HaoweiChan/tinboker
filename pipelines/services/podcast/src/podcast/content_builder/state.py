"""Pipeline state schema for LangGraph content generation workflow."""

from __future__ import annotations

from typing import Any, Optional

from typing_extensions import TypedDict


class EventItem(TypedDict, total=False):
    start_index: int
    end_index: int
    section_topic: str
    # Closed-vocabulary segment classification from the extractor. The clusterer's
    # policy router keys on this (see nodes/clusterer.py). Missing -> "unknown" -> kept.
    segment_type: str
    # For "qa" (and other gated types), whether the segment carries market substance
    # worth surfacing. Personal/shout-out Q&A is is_substantive=False and dropped.
    is_substantive: bool


class ClusteredEvent(TypedDict, total=False):
    section_topic: str
    sentences: list[dict[str, Any]]
    start: int
    end: int


class ArticleSection(TypedDict, total=False):
    heading: str
    content: str
    start_time: Optional[int]
    subsections: list[dict[str, str]]


class WriterOutput(TypedDict, total=False):
    title: str
    executive_summary: str
    sections: list[ArticleSection]
    conclusion: str
    stock_tickers: list[dict[str, str]]
    tags: list[dict[str, str]]


class TickerReason(TypedDict, total=False):
    title: str
    description: str
    category: str
    start_index: int
    end_index: int
    start_time: int
    end_time: int


class TickerRisk(TypedDict, total=False):
    title: str
    description: str
    severity: str
    start_index: int
    end_index: int
    start_time: int
    end_time: int


class TickerInsight(TypedDict, total=False):
    ticker: str
    sentiment: str
    sentiment_score: float
    time_horizon: str
    bluf_thesis: str
    price_target: Optional[float]
    reasons: list[TickerReason]
    risks: list[TickerRisk]


class PipelineState(TypedDict, total=False):
    # Inputs
    transcript: str
    source: str
    episode_title: str
    sentences: list[dict[str, Any]]

    # Resolved per-show structure profile ({structure_hint, policy}); seeded by
    # run_pipeline / the regen orchestrator from content_builder.profiles.load_profile.
    show_profile: dict[str, Any]

    # After extraction
    events: list[EventItem]

    # After clustering
    clustered_events: list[ClusteredEvent]

    # After writing
    writer_output: WriterOutput

    # After markdown transform
    markdown_report: str

    # 3–8 plain-text zh-TW takeaways derived from markdown_report
    key_insights: list[str]

    # Tags + tickers parsed from markdown_report's #tag:/#ticker: links
    # (derive_tags_tickers node) — the canonical episode tags/related_tickers.
    tags: list[str]
    related_tickers: list[str]

    # Events markdown (parallel branch)
    events_markdown: str

    # After marp writing
    marp_slides: dict[str, Any]
    marp_markdown: str

    # Ordered AlphaMemo-style cards (cover + one per theme), built by joining
    # marp_slides + key_insights. Powers the Threads carousel/replies + episode SEO.
    social_cards: list[dict[str, Any]]

    # Ticker insights (parallel branch)
    ticker_insights: dict[str, Any]
    ticker_marp_slides: dict[str, Any]
    ticker_marp_markdown: str

    # Error tracking
    errors: list[str]
