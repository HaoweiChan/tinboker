"""Writer node: generates structured financial article from clustered events."""

import json
from typing import Any

from ..llm import invoke_json, load_prompt
from ..state import PipelineState


def write_article(state: PipelineState) -> dict[str, Any]:
    """Generate a structured financial article from clustered events."""
    prompts = load_prompt("writer")
    events_json = json.dumps(state.get("clustered_events", []), ensure_ascii=False)

    user_msg = prompts["user"].format(
        events=events_json,
        source=state.get("source", "Podcast"),
        episode_title=state.get("episode_title", "Episode"),
    )

    result = invoke_json("writer", [
        {"role": "system", "content": prompts["system"]},
        {"role": "user", "content": user_msg},
    ])

    return {"writer_output": result}
