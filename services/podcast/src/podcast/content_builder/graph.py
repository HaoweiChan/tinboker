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
     END              END             convert_ticker_marp
                                             │
                                             ▼
                                            END
"""

from __future__ import annotations

import json
from typing import Any

from langgraph.graph import END, StateGraph

from .nodes.clusterer import cluster_sentences
from .nodes.events_markdown import build_events_markdown
from .nodes.extractor import extract_events
from .nodes.markdown_transform import transform_to_markdown
from .nodes.marp_converter import convert_marp, convert_marp_ticker
from .nodes.marp_writer import write_marp_slides
from .nodes.ticker_extractor import extract_tickers
from .nodes.writer import write_article
from .state import PipelineState


def _write_ticker_marp(state: PipelineState) -> dict[str, Any]:
    """Generate Marp slides specifically for ticker recommendations."""
    from .llm import invoke_json, load_prompt

    prompts = load_prompt("marp_writer")
    ticker_data = state.get("ticker_recommendations", {})
    events_json = json.dumps(ticker_data, ensure_ascii=False)

    user_msg = prompts["user"].format(
        events=events_json,
        source=state.get("source", "Podcast"),
        episode_title=state.get("episode_title", "Episode"),
    )

    result = invoke_json("marp_writer", [
        {"role": "system", "content": prompts["system"]},
        {"role": "user", "content": user_msg},
    ])

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
    graph.add_node("write_marp_slides", write_marp_slides)
    graph.add_node("convert_marp", convert_marp)
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

    # Article branch
    graph.add_edge("write_article", "transform_to_markdown")
    graph.add_edge("transform_to_markdown", END)

    # Marp branch
    graph.add_edge("write_marp_slides", "convert_marp")
    graph.add_edge("convert_marp", END)

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
        - ticker_recommendations
        - ticker_marp_markdown
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
        "ticker_recommendations": result.get("ticker_recommendations"),
        "ticker_marp_markdown": result.get("ticker_marp_markdown", ""),
    }
