"""Event extraction node: identifies topics/sections from sentences."""

import json
from typing import Any

from ..llm import invoke_json, load_prompt
from ..state import PipelineState


def extract_events(state: PipelineState) -> dict[str, Any]:
    """Extract topic events from transcript sentences."""
    prompts = load_prompt("extractor")
    sentences_json = json.dumps(state["sentences"], ensure_ascii=False)

    user_msg = prompts["user"].format(
        source=state.get("source", "Podcast"),
        episode_title=state.get("episode_title", "Episode"),
        sentences=sentences_json,
    )

    result = invoke_json("extractor", [
        {"role": "system", "content": prompts["system"]},
        {"role": "user", "content": user_msg},
    ])

    if isinstance(result, list):
        return {"events": result}
    return {"events": result.get("events", [])}
