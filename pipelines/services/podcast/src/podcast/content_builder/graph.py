"""LangGraph workflow definition for the content generation pipeline.

Graph topology (mirrors the original Dify workflow):

    start
      │
      ▼
  extract_events
      │
      ├──────────────────────────────┐
      ▼                              ▼
  cluster_sentences          build_events_markdown ──► END
      │
      ├────────────────────┬──────────────────┐
      ▼                    ▼                  ▼
 consolidate_chapters  write_marp_slides  extract_tickers
      │                    │                  │
      ▼                    ▼                  ▼
  write_article        convert_marp     convert_marp_ticker ──► END
      │                    │             (deterministic deck
      ▼                    ▼              from ticker_insights)
  transform_md           END
      │
      ▼
 extract_key_insights
      │
      ▼
     END

(cluster_sentences also fans out to derive_sector_exposures ──► END.
 consolidate_chapters merges the fine clustered_events into a small,
 length-scaled set of chapter_events that only the writer + markdown
 timestamp anchoring read.)
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, StateGraph

from .nodes.chapter_consolidator import consolidate_chapters
from .nodes.clusterer import cluster_sentences
from .nodes.events_markdown import build_events_markdown
from .nodes.extractor import extract_events
from .nodes.key_insights_extractor import extract_key_insights
from .nodes.markdown_transform import transform_to_markdown
from .nodes.marp_converter import convert_marp, convert_marp_ticker
from .nodes.marp_writer import write_marp_slides
from .nodes.sector_exposures import derive_sector_exposures
from .nodes.social_cards_builder import build_social_cards
from .nodes.social_copy_writer import write_social_copy
from .nodes.tags_tickers import derive_tags_tickers
from .nodes.ticker_extractor import extract_tickers
from .nodes.writer import write_article
from .state import PipelineState


def build_graph() -> StateGraph:
    """Construct and compile the content generation LangGraph."""
    graph = StateGraph(PipelineState)

    # Add nodes
    graph.add_node("extract_events", extract_events)
    graph.add_node("cluster_sentences", cluster_sentences)
    graph.add_node("consolidate_chapters", consolidate_chapters)
    graph.add_node("build_events_markdown", build_events_markdown)
    graph.add_node("write_article", write_article)
    graph.add_node("transform_to_markdown", transform_to_markdown)
    graph.add_node("derive_tags_tickers", derive_tags_tickers)
    graph.add_node("extract_key_insights", extract_key_insights)
    graph.add_node("write_marp_slides", write_marp_slides)
    graph.add_node("convert_marp", convert_marp)
    graph.add_node("build_social_cards", build_social_cards)
    graph.add_node("write_social_copy", write_social_copy)
    graph.add_node("derive_sector_exposures", derive_sector_exposures)
    graph.add_node("extract_tickers", extract_tickers)
    graph.add_node("convert_marp_ticker", convert_marp_ticker)

    # Entry point
    graph.set_entry_point("extract_events")

    # After extraction: fan out to clusterer + events_markdown (parallel branches)
    graph.add_edge("extract_events", "cluster_sentences")
    graph.add_edge("extract_events", "build_events_markdown")

    # Events markdown is a terminal branch
    graph.add_edge("build_events_markdown", END)

    # After clustering: fan out to marp_writer + ticker_extractor + sector
    # exposures (all on the fine clustered_events), and to chapter consolidation
    # which feeds the writer with the coarse, length-scaled chapters.
    graph.add_edge("cluster_sentences", "consolidate_chapters")
    graph.add_edge("cluster_sentences", "write_marp_slides")
    graph.add_edge("cluster_sentences", "extract_tickers")
    graph.add_edge("cluster_sentences", "derive_sector_exposures")
    graph.add_edge("consolidate_chapters", "write_article")

    # Article branch (markdown → tags/tickers → key_insights, from the finished summary)
    graph.add_edge("write_article", "transform_to_markdown")
    graph.add_edge("transform_to_markdown", "derive_tags_tickers")
    graph.add_edge("derive_tags_tickers", "extract_key_insights")

    # Marp branch
    graph.add_edge("write_marp_slides", "convert_marp")

    # Join: the unified carousel needs the marp slides, the key insights AND the
    # ticker insights (for the overview grid + analysis cards), so build_social_cards
    # fans in on all three branches before it runs.
    graph.add_edge("extract_key_insights", "build_social_cards")
    graph.add_edge("convert_marp", "build_social_cards")
    graph.add_edge("extract_tickers", "build_social_cards")
    # Social copy reads the assembled cards + summary, then ends the branch.
    graph.add_edge("build_social_cards", "write_social_copy")
    graph.add_edge("write_social_copy", END)

    # Deterministic exposure branch (separate from direct ticker extraction).
    graph.add_edge("derive_sector_exposures", END)

    # Ticker branch — the deck is now built deterministically from ticker_insights
    # (overview grid + focus-analysis cards), so no LLM marp step in between.
    graph.add_edge("extract_tickers", "convert_marp_ticker")
    graph.add_edge("convert_marp_ticker", END)

    return graph.compile()


def run_pipeline(
    transcript: str,
    sentences: list[dict[str, Any]],
    source: str = "Podcast",
    episode_title: str = "Episode",
) -> dict[str, Any]:
    """Run the full content generation pipeline and return outputs.

    Returns a dict with keys matching the old Dify API output:
        - markdown_report
        - events_markdown
        - marp_markdown
        - ticker_insights
        - ticker_marp_markdown
        - key_insights
        - social_cards
    """
    from .profiles import load_profile

    app = build_graph()

    initial_state: PipelineState = {
        "transcript": transcript,
        "sentences": sentences,
        "source": source,
        "episode_title": episode_title,
        # Per-show structure prior + segment policy; drives the extractor prompt
        # and the clusterer's policy router. Defaults cover unprofiled shows.
        "show_profile": load_profile(source),
    }

    result = app.invoke(initial_state)

    related_tickers = result.get("related_tickers", [])
    ticker_insights = result.get("ticker_insights")
    if ticker_insights and not related_tickers:
        from src.podcast.exporters.ticker_insights import iter_insight_tickers
        related_tickers = sorted(set(iter_insight_tickers(ticker_insights)))

    return {
        "markdown_report": result.get("markdown_report", ""),
        "events_markdown": result.get("events_markdown", ""),
        "marp_markdown": result.get("marp_markdown", ""),
        "ticker_insights": ticker_insights,
        "ticker_marp_markdown": result.get("ticker_marp_markdown", ""),
        "key_insights": result.get("key_insights", []),
        "tags": result.get("tags", []),
        "related_tickers": related_tickers,
        "social_cards": result.get("social_cards", []),
        "social_thread": result.get("social_thread") or {"post": "", "comments": []},
        "sector_exposures": result.get("sector_exposures", []),
        "unresolved_market_trends": result.get("unresolved_market_trends", []),
        "sector_exposure_ids": result.get("sector_exposure_ids", []),
        "sector_ids": result.get("sector_ids", []),
        "theme_ids": result.get("theme_ids", []),
        "unresolved_market_trend_ids": result.get("unresolved_market_trend_ids", []),
    }
