"""Social copy writer node: turns an episode's cards into human-tone Threads copy.

Produces ``social_thread = {post, comments: [{heading, text}, ...]}`` — one
grand-summary post plus one short, conversational comment per *theme* card (the
cover is covered by the post, not a comment). The downstream Threads publisher
prefers this human copy over the mechanical ``【title】 + bullets`` fallback.

Runs after ``build_social_cards`` (it reads the assembled cards + the summary),
and is also exposed as an optional regen step so the copy can be re-authored or
hand-edited per episode.
"""

from __future__ import annotations

import json
from typing import Any

from ..llm import invoke_json, load_prompt
from ..state import PipelineState
from .social_cards_builder import cards_from_marp_slides


def _cards_for_copy(state: PipelineState) -> list[dict[str, Any]]:
    """The cards to summarise — use built ``social_cards`` or derive them."""
    cards = state.get("social_cards")
    if cards:
        return cards
    return cards_from_marp_slides(
        state.get("marp_slides") or {},
        state.get("key_insights") or [],
        state.get("episode_title") or "",
    )


def build_messages(state: PipelineState) -> list[dict[str, str]]:
    """Render the social_copy_writer chat messages from the episode's cards."""
    prompts = load_prompt("social_copy_writer")
    cards = _cards_for_copy(state)
    # Trim to what the writer needs (kind/title/bullets) — drop image_url/None noise.
    slim = [
        {"kind": c.get("kind"), "title": c.get("title"), "bullets": c.get("bullets") or []}
        for c in cards
        if isinstance(c, dict)
    ]
    summary = (state.get("markdown_report") or "").strip()
    # The summary is only a steer; a few hundred chars of it is plenty of direction.
    if len(summary) > 1200:
        summary = summary[:1200].rstrip() + "…"

    user_msg = prompts["user"].format(
        cards=json.dumps(slim, ensure_ascii=False, indent=2),
        source=state.get("source") or "Podcast",
        episode_title=state.get("episode_title") or "Episode",
        summary=summary or "（無摘要，請從卡片內容自行抓重點）",
    )
    return [
        {"role": "system", "content": prompts["system"]},
        {"role": "user", "content": user_msg},
    ]


def postprocess(result: Any, state: PipelineState) -> dict[str, Any]:
    """Normalise the LLM/agent output into a clean ``social_thread`` dict."""
    post = ""
    comments: list[dict[str, str]] = []
    if isinstance(result, dict):
        post = (result.get("post") or "").strip()
        for item in result.get("comments") or []:
            if isinstance(item, dict):
                text = (item.get("text") or "").strip()
                heading = (item.get("heading") or "").strip()
            else:
                text, heading = str(item).strip(), ""
            if text:
                comments.append({"heading": heading, "text": text})
    return {"social_thread": {"post": post, "comments": comments}}


def write_social_copy(state: PipelineState) -> dict[str, Any]:
    """Generate the human-tone Threads post + per-theme comments."""
    result = invoke_json("social_copy_writer", build_messages(state))
    return postprocess(result, state)
