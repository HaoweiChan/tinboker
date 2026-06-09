"""Ticker insights extractor node."""

import json
from typing import Any

from ..llm import invoke_json, load_prompt
from ..state import PipelineState


def extract_tickers(state: PipelineState) -> dict[str, Any]:
    """Extract ticker insights from clustered events."""
    prompts = load_prompt("ticker_extractor")
    events_json = json.dumps(state.get("clustered_events", []), ensure_ascii=False)

    user_msg = prompts["user"].format(
        events=events_json,
        source=state.get("source", "Podcast"),
        episode_title=state.get("episode_title", "Episode"),
    )

    result = invoke_json("ticker_extractor", [
        {"role": "system", "content": prompts["system"]},
        {"role": "user", "content": user_msg},
    ])

    return {"ticker_insights": result}
