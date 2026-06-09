"""Event extraction node: identifies topics/sections from sentences.

Split into ``build_messages`` (render the prompt) and ``postprocess`` (normalize
the model's reply) so the agent-backed regeneration path
(``podcast.regen.orchestrator``) reuses the *exact* same prompt + parsing as the
live ``invoke_json`` path — the node itself is just build → invoke → postprocess.
"""

import json
from typing import Any

from ..llm import invoke_json, load_prompt
from ..state import PipelineState


def build_messages(state: PipelineState) -> list[dict[str, str]]:
    """Render the extractor chat messages for ``state`` (no LLM call)."""
    prompts = load_prompt("extractor")
    sentences_json = json.dumps(state.get("sentences", []), ensure_ascii=False)

    user_msg = prompts["user"].format(
        source=state.get("source", "Podcast"),
        episode_title=state.get("episode_title", "Episode"),
        sentences=sentences_json,
    )

    return [
        {"role": "system", "content": prompts["system"]},
        {"role": "user", "content": user_msg},
    ]


def postprocess(result: Any, state: PipelineState) -> dict[str, Any]:
    """Normalize the extractor reply into a ``{"events": [...]}`` state update."""
    if isinstance(result, list):
        return {"events": result}
    return {"events": result.get("events", [])}


def extract_events(state: PipelineState) -> dict[str, Any]:
    """Extract topic events from transcript sentences."""
    result = invoke_json("extractor", build_messages(state))
    return postprocess(result, state)
