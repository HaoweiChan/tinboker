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
      ├────────────────┬─────────────────────┐
      ▼                ▼                     ▼
  write_article   write_marp_slides    extract_tickers
      │                │                     │
      ▼                ▼                     ▼
  transform_md    convert_marp        write_ticker_marp
      │                │                     │
      ▼                ▼                     ▼
 extract_key_     convert_marp        convert_ticker_marp
   insights           │                     │
      │               ▼                     ▼
      ▼              END                    END
     END
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, StateGraph

from .nodes.clusterer import cluster_sentences
from .nodes.events_markdown import build_events_markdown
from .nodes.extractor import extract_events
from .nodes.key_insights_extractor import extract_key_insights
from .nodes.markdown_transform import transform_to_markdown
from .nodes.tags_tickers import derive_tags_tickers
from .nodes.marp_converter import convert_marp, convert_marp_ticker
from .nodes.marp_writer import write_marp_slides
from .nodes.social_cards_builder import build_social_cards
from .nodes.ticker_extractor import extract_tickers
from .nodes.writer import write_article
from .state import PipelineState


def _write_ticker_marp(state: PipelineState) -> dict[str, Any]:
    """Generate Marp slides specifically for ticker insights."""
    from .llm import invoke_json
    from .nodes.marp_writer import build_messages_from_events

    messages = build_messages_from_events(
        state.get("ticker_insights", {}),
        state.get("source", "Podcast"),
        state.get("episode_title", "Episode"),
    )
    result = invoke_json("marp_writer", messages)

    return {"ticker_marp_slides": result}


def build_graph() -> StateGraph:
    """Construct and compile the content generation LangGraph."""
    graph = StateGraph(PipelineState)

    # Add nodes
    graph.add_node("extract_events", extract_events)
    graph.add_node("cluster_sentences", cluster_sentences)
    graph.add_node("build_events_markdown", build_events_markdown)
    graph.add_node("write_article", write_article)
    graph.add_node("transform_to_markdown", transform_to_markdown)
    graph.add_node("derive_tags_tickers", derive_tags_tickers)
    graph.add_node("extract_key_insights", extract_key_insights)
    graph.add_node("write_marp_slides", write_marp_slides)
    graph.add_node("convert_marp", convert_marp)
    graph.add_node("build_social_cards", build_social_cards)
    graph.add_node("extract_tickers", extract_tickers)
    graph.add_node("write_ticker_marp", _write_ticker_marp)
    graph.add_node("convert_marp_ticker", convert_marp_ticker)

    # Entry point
    graph.set_entry_point("extract_events")

    # After extraction: fan out to clusterer + events_markdown (parallel branches)
    graph.add_edge("extract_events", "cluster_sentences")
    graph.add_edge("extract_events", "build_events_markdown")

    # Events markdown is a terminal branch
    graph.add_edge("build_events_markdown", END)

    # After clustering: fan out to writer + marp_writer + ticker_extractor
    graph.add_edge("cluster_sentences", "write_article")
    graph.add_edge("cluster_sentences", "write_marp_slides")
    graph.add_edge("cluster_sentences", "extract_tickers")

    # Article branch (markdown → tags/tickers → key_insights, from the finished summary)
    graph.add_edge("write_article", "transform_to_markdown")
    graph.add_edge("transform_to_markdown", "derive_tags_tickers")
    graph.add_edge("derive_tags_tickers", "extract_key_insights")

    # Marp branch
    graph.add_edge("write_marp_slides", "convert_marp")

    # Join: social cards need BOTH the marp slides and the key insights, so
    # build_social_cards waits on both branches (LangGraph fan-in) before END.
    graph.add_edge("extract_key_insights", "build_social_cards")
    graph.add_edge("convert_marp", "build_social_cards")
    graph.add_edge("build_social_cards", END)

    # Ticker branch
    graph.add_edge("extract_tickers", "write_ticker_marp")
    graph.add_edge("write_ticker_marp", "convert_marp_ticker")
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
    app = build_graph()

    initial_state: PipelineState = {
        "transcript": transcript,
        "sentences": sentences,
        "source": source,
        "episode_title": episode_title,
    }

    result = app.invoke(initial_state)

    return {
        "markdown_report": result.get("markdown_report", ""),
        "events_markdown": result.get("events_markdown", ""),
        "marp_markdown": result.get("marp_markdown", ""),
        "ticker_insights": result.get("ticker_insights"),
        "ticker_marp_markdown": result.get("ticker_marp_markdown", ""),
        "key_insights": result.get("key_insights", []),
        "tags": result.get("tags", []),
        "related_tickers": result.get("related_tickers", []),
        "social_cards": result.get("social_cards", []),
    }
