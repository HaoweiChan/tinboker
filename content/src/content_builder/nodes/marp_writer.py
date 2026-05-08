"""Marp writer node: generates structured slide data from clustered events."""

import json
from typing import Any

from content_builder.llm import invoke_json, load_prompt
from content_builder.state import PipelineState


def write_marp_slides(state: PipelineState) -> dict[str, Any]:
    """Generate structured Marp slide data from clustered events."""
    prompts = load_prompt("marp_writer")
    events_json = json.dumps(state.get("clustered_events", []), ensure_ascii=False)

    user_msg = prompts["user"].format(
        events=events_json,
        source=state.get("source", "Podcast"),
        episode_title=state.get("episode_title", "Episode"),
    )

    result = invoke_json("marp_writer", [
        {"role": "system", "content": prompts["system"]},
        {"role": "user", "content": user_msg},
    ])

    return {"marp_slides": result}
