"""Ticker insights extractor node.

``build_messages`` / ``postprocess`` are factored out so the agent-backed
regeneration path reuses the identical prompt + parsing (see ``nodes/extractor.py``).
"""

import json
from typing import Any

from ..llm import invoke_json, load_prompt
from ..state import PipelineState


def build_messages(state: PipelineState) -> list[dict[str, str]]:
    """Render the ticker-extractor chat messages from ``clustered_events``."""
    prompts = load_prompt("ticker_extractor")
    events_json = json.dumps(state.get("clustered_events", []), ensure_ascii=False)

    user_msg = prompts["user"].format(
        events=events_json,
        source=state.get("source", "Podcast"),
        episode_title=state.get("episode_title", "Episode"),
    )

    return [
        {"role": "system", "content": prompts["system"]},
        {"role": "user", "content": user_msg},
    ]


def postprocess(result: Any, state: PipelineState) -> dict[str, Any]:
    """Store the raw ticker-insights payload (the ``ticker_recommendations`` wrapper)."""
    return {"ticker_insights": result}


def extract_tickers(state: PipelineState) -> dict[str, Any]:
    """Extract ticker insights from clustered events."""
    result = invoke_json("ticker_extractor", build_messages(state))
    return postprocess(result, state)
