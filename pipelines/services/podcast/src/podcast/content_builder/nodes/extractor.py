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


def _raw_events(result: Any) -> list:
    """Pull the raw events list out of an array or a ``{"events": [...]}`` reply."""
    return result if isinstance(result, list) else (result or {}).get("events", [])


def postprocess(result: Any, state: PipelineState) -> dict[str, Any]:
    """Normalize the extractor reply into a ``{"events": [...]}`` state update."""
    return {"events": [_normalize_event(ev) for ev in _raw_events(result)]}


# Long episodes overflow a single extractor call: the JSON reply grows with the
# transcript and, past ~1500 sentences, exceeds even Gemini's max output tokens —
# the reply truncates mid-array, fails to parse, and the episode falls back to the
# placeholder summarizer (see content_builder/llm.py ``_MAX_TOKENS_MAP`` history).
# For long transcripts we extract in sentence-position chunks and merge, keeping
# each call's reply small. Episodes at or below the threshold keep the original
# single-call behavior byte-for-byte, so only currently-failing long episodes take
# the new path.
_CHUNK_THRESHOLD = 1200  # sentences; at or below this -> single call (unchanged)
_CHUNK_SIZE = 800        # sentences per chunk on the long-episode path


def _extract_chunked(state: PipelineState, sentences: list) -> list[dict[str, Any]]:
    """Extract events for a long transcript by chunking sentence positions.

    Each chunk is re-indexed to 0-based local positions (matching the extractor
    prompt's "0-based sentence index" contract); the model's returned ranges are
    offset back to global positions so the clusterer — which indexes the full
    sentence list positionally (``sentences_list[i]``) — still resolves them.

    A topic straddling a chunk boundary is split into one event per chunk; the
    clusterer handles each independently, so the only effect is slightly finer
    chaptering at boundaries — a fair trade vs. the whole episode failing.
    """
    merged: list[dict[str, Any]] = []
    for offset in range(0, len(sentences), _CHUNK_SIZE):
        batch = sentences[offset:offset + _CHUNK_SIZE]
        local = [{**s, "index": i} for i, s in enumerate(batch)]
        sub_state = {**state, "sentences": local}
        for ev in _raw_events(invoke_json("extractor", build_messages(sub_state))):
            if isinstance(ev, dict):
                ev = dict(ev)
                if isinstance(ev.get("start_index"), int):
                    ev["start_index"] += offset
                if isinstance(ev.get("end_index"), int):
                    ev["end_index"] += offset
            merged.append(ev)
    return merged


def extract_events(state: PipelineState) -> dict[str, Any]:
    """Extract topic events from transcript sentences.

    Long transcripts are processed in position-chunks (``_extract_chunked``) to
    keep each LLM reply small enough to parse; shorter ones use a single call as
    before.
    """
    sentences = state.get("sentences", [])
    if len(sentences) > _CHUNK_THRESHOLD:
        merged = _extract_chunked(state, sentences)
        return {"events": [_normalize_event(ev) for ev in merged]}
    result = invoke_json("extractor", build_messages(state))
    return postprocess(result, state)
