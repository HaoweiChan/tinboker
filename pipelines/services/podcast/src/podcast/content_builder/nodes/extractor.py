"""Event extraction node: identifies topics/sections from sentences.

Split into ``build_messages`` (render the prompt) and ``postprocess`` (normalize
the model's reply) so the agent-backed regeneration path
(``podcast.regen.orchestrator``) reuses the *exact* same prompt + parsing as the
live ``invoke_json`` path — the node itself is just build → invoke → postprocess.

Each event is classified with a closed-vocabulary ``segment_type`` (+ an
``is_substantive`` flag for gated types like Q&A). The clusterer's policy router
keys on these; ``postprocess`` normalizes them so a missing/odd value degrades to
``unknown`` (kept as content) rather than breaking routing.
"""

import json
from typing import Any

from ..llm import invoke_json, load_prompt
from ..state import PipelineState

# Closed vocabulary the extractor must classify each event into (mirrors the
# extractor.yaml system prompt and the clusterer policy keys).
SEGMENT_TYPES = {
    "sponsor", "intro", "outro", "chitchat", "analysis", "guest", "qa", "unknown",
}

# Types where market substance is not expected — is_substantive is irrelevant
# (they are dropped by the default policy regardless), so default it to False.
_NON_SUBSTANTIVE_TYPES = {"sponsor", "intro", "outro", "chitchat"}

_TRUTHY_STRINGS = {"true", "1", "yes", "substantive"}


def build_messages(state: PipelineState) -> list[dict[str, str]]:
    """Render the extractor chat messages for ``state`` (no LLM call)."""
    prompts = load_prompt("extractor")
    sentences_json = json.dumps(state.get("sentences", []), ensure_ascii=False)
    structure_hint = (state.get("show_profile") or {}).get("structure_hint") or "（無特定結構提示，依實際內容判斷）"

    user_msg = prompts["user"].format(
        source=state.get("source", "Podcast"),
        episode_title=state.get("episode_title", "Episode"),
        structure_hint=structure_hint,
        sentences=sentences_json,
    )

    return [
        {"role": "system", "content": prompts["system"]},
        {"role": "user", "content": user_msg},
    ]


def _normalize_event(ev: Any) -> dict[str, Any]:
    """Coerce one raw event to a normalized {segment_type, is_substantive, ...} dict."""
    if not isinstance(ev, dict):
        return {"segment_type": "unknown", "is_substantive": True}

    seg = str(ev.get("segment_type") or "").strip().lower()
    if seg not in SEGMENT_TYPES:
        seg = "unknown"

    raw_sub = ev.get("is_substantive")
    if isinstance(raw_sub, bool):
        sub = raw_sub
    elif isinstance(raw_sub, str):
        sub = raw_sub.strip().lower() in _TRUTHY_STRINGS
    else:
        # Missing: keep content-bearing types by default (floor = never worse than
        # "keep everything"); the always-drop types don't care.
        sub = seg not in _NON_SUBSTANTIVE_TYPES

    return {**ev, "segment_type": seg, "is_substantive": sub}


def postprocess(result: Any, state: PipelineState) -> dict[str, Any]:
    """Normalize the extractor reply into a ``{"events": [...]}`` state update."""
    events = result if isinstance(result, list) else (result or {}).get("events", [])
    return {"events": [_normalize_event(ev) for ev in (events or [])]}


def extract_events(state: PipelineState) -> dict[str, Any]:
    """Extract topic events from transcript sentences."""
    result = invoke_json("extractor", build_messages(state))
    return postprocess(result, state)
