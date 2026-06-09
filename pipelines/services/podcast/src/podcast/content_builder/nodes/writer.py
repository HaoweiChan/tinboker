"""Writer node: generates structured financial article from clustered events.

``build_messages`` / ``postprocess`` are factored out so the agent-backed
regeneration path reuses the identical prompt + parsing (see ``nodes/extractor.py``).
"""

import json
from typing import Any

from ..llm import invoke_json, load_prompt
from ..state import PipelineState
from ..tag_vocabulary import vocabulary_prompt_block


def build_messages(state: PipelineState) -> list[dict[str, str]]:
    """Render the writer chat messages from ``clustered_events`` (no LLM call)."""
    prompts = load_prompt("writer")
    events_json = json.dumps(state.get("clustered_events", []), ensure_ascii=False)

    user_msg = prompts["user"].format(
        events=events_json,
        source=state.get("source", "Podcast"),
        episode_title=state.get("episode_title", "Episode"),
        tag_vocabulary=vocabulary_prompt_block(),
    )

    return [
        {"role": "system", "content": prompts["system"]},
        {"role": "user", "content": user_msg},
    ]


def postprocess(result: Any, state: PipelineState) -> dict[str, Any]:
    """Store the structured writer output for the markdown-transform step."""
    return {"writer_output": result}


def write_article(state: PipelineState) -> dict[str, Any]:
    """Generate a structured financial article from clustered events."""
    result = invoke_json("writer", build_messages(state))
    return postprocess(result, state)
