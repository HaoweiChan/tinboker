"""Marp writer node: generates structured slide data from clustered events.

Drives the episode deck only (``clustered_events`` → cover + theme cards). The
ticker deck is no longer LLM-written — it is built deterministically from
``ticker_insights`` (see ``nodes.social_cards_builder.cards_from_ticker_insights``).
``build_messages_from_events`` stays generic so the agent-backed regeneration path
renders a byte-identical prompt for the episode deck.
"""

import json
from typing import Any

from ..llm import invoke_json, load_prompt
from ..state import PipelineState


def build_messages_from_events(
    events_obj: Any,
    source: str = "Podcast",
    episode_title: str = "Episode",
) -> list[dict[str, str]]:
    """Render the marp_writer chat messages for an arbitrary ``events`` payload."""
    prompts = load_prompt("marp_writer")
    events_json = json.dumps(events_obj, ensure_ascii=False)

    user_msg = prompts["user"].format(
        events=events_json,
        source=source,
        episode_title=episode_title,
    )

    return [
        {"role": "system", "content": prompts["system"]},
        {"role": "user", "content": user_msg},
    ]


def build_messages(state: PipelineState) -> list[dict[str, str]]:
    """Render the episode-slides marp_writer messages from ``clustered_events``."""
    return build_messages_from_events(
        state.get("clustered_events", []),
        state.get("source", "Podcast"),
        state.get("episode_title", "Episode"),
    )


def postprocess(result: Any, state: PipelineState) -> dict[str, Any]:
    """Store the structured slide data for the marp-converter step."""
    return {"marp_slides": result}


def write_marp_slides(state: PipelineState) -> dict[str, Any]:
    """Generate structured Marp slide data from clustered events."""
    result = invoke_json("marp_writer", build_messages(state))
    return postprocess(result, state)
