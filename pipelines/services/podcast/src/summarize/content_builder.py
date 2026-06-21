"""Content generation via LangGraph pipeline.

Replaces the old Dify Workflow API integration. Calls the content-builder
LangGraph pipeline directly in-process.
"""

import os
from typing import Optional


def is_workflow_api_available() -> bool:
    """Check if the LangGraph pipeline can run (needs OPENROUTER_API_KEY)."""
    return os.getenv("OPENROUTER_API_KEY") is not None


def analyze_transcript_with_workflow_api(
    transcript: str,
    source: str = "Podcast",
    episode_title: str = "Episode",
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    user_id: Optional[str] = None,
    timeout: int = 300,
    words: Optional[list] = None,
    sentences: Optional[list] = None,
) -> dict:
    """Analyze transcript using the LangGraph content-builder pipeline.

    This function maintains the same interface as the old Dify API caller
    so the rest of the podcast pipeline needs no changes.

    Args:
        transcript: Transcript text content
        source: Name of the podcast/source
        episode_title: Title of the episode
        api_key: Unused (kept for backward compatibility)
        base_url: Unused (kept for backward compatibility)
        user_id: Unused (kept for backward compatibility)
        timeout: Unused (kept for backward compatibility)
        words: Deprecated, use sentences instead
        sentences: List of sentence objects with timing information

    Returns:
        Dictionary with markdown_report, events_markdown, marp_markdown,
        ticker_insights, ticker_marp_markdown, key_insights.

    Raises:
        ValueError: If OPENROUTER_API_KEY is not set
        RuntimeError: If the pipeline fails
    """
    if not os.getenv("OPENROUTER_API_KEY"):
        raise ValueError(
            "OPENROUTER_API_KEY is required for the content generation pipeline. "
            "Set it via Google Secret Manager or environment variable."
        )

    from src.podcast.content_builder import run_pipeline

    sentences_input = sentences or []
    if not sentences_input and words:
        sentences_input = words

    result = run_pipeline(
        transcript=transcript,
        sentences=sentences_input,
        source=source,
        episode_title=episode_title,
    )

    markdown_report = result.get("markdown_report", "")
    if not markdown_report or not markdown_report.strip():
        raise ValueError(
            "Content pipeline returned empty markdown_report. "
            f"Pipeline result keys: {list(result.keys())}"
        )

    return {
        "markdown_report": markdown_report,
        "events_markdown": result.get("events_markdown") or None,
        "pptx_base64": None,
        "marp_markdown": result.get("marp_markdown") or None,
        "ticker_insights": result.get("ticker_insights") or None,
        "ticker_marp_markdown": result.get("ticker_marp_markdown") or None,
        "key_insights": result.get("key_insights") or [],
        # Canonical tags/related_tickers derived from the summary's #tag:/#ticker:
        # links by the pipeline's derive_tags_tickers node — the single source of
        # truth shared with the regen path (the consumer prefers these over the
        # placeholder ticker extraction).
        "tags": result.get("tags") or [],
        "related_tickers": result.get("related_tickers") or [],
        "social_cards": result.get("social_cards") or [],
        "sector_exposures": result.get("sector_exposures") or [],
        "unresolved_market_trends": result.get("unresolved_market_trends") or [],
        "sector_exposure_ids": result.get("sector_exposure_ids") or [],
        "sector_ids": result.get("sector_ids") or [],
        "theme_ids": result.get("theme_ids") or [],
        "unresolved_market_trend_ids": result.get("unresolved_market_trend_ids") or [],
    }
