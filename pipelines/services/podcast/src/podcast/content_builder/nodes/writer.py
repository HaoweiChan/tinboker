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


# The writer must emit one section per clustered event, so its JSON article grows
# with the episode. Past ~N events a single reply exceeds even Gemini's max output
# tokens — it truncates mid-string ("Unterminated string"), fails to parse, and the
# WHOLE episode falls back to the placeholder summarizer (exactly the failure the
# extractor already chunks around; see nodes/extractor.py). For long episodes we
# write the article in event-position chunks and merge the sections, keeping each
# reply small. Episodes at or below the threshold keep the original single-call
# behavior byte-for-byte, so only currently-failing long episodes take the new path.
_CHUNK_THRESHOLD = 20  # clustered events; at or below this -> single call (unchanged)
_CHUNK_SIZE = 12       # events per chunk on the long-episode path


def _merge_writer_outputs(outputs: list[Any]) -> dict[str, Any]:
    """Merge per-chunk writer outputs into one article.

    Sections are concatenated in chunk order. The writer emits one section per
    input event in order and each chunk receives a contiguous slice of
    ``clustered_events``, so the merged section order matches the full event order
    — which ``markdown_transform`` maps positionally onto ``clustered_events`` to
    anchor chapter timestamps. ``title``/``executive_summary`` come from the first
    chunk that produced them; ``conclusion`` from the last (it reads as the wrap-up);
    ``stock_tickers``/``tags`` are unioned (de-duped, order-preserving).
    """
    merged: dict[str, Any] = {
        "title": "",
        "executive_summary": "",
        "sections": [],
        "conclusion": "",
        "stock_tickers": [],
        "tags": [],
    }
    seen_tickers: set = set()
    seen_tags: set = set()
    for out in outputs:
        if not isinstance(out, dict):
            continue
        if not merged["title"] and out.get("title"):
            merged["title"] = out["title"]
        if not merged["executive_summary"] and out.get("executive_summary"):
            merged["executive_summary"] = out["executive_summary"]
        for section in out.get("sections") or []:
            merged["sections"].append(section)
        if out.get("conclusion"):
            merged["conclusion"] = out["conclusion"]  # keep the last non-empty
        for ticker in out.get("stock_tickers") or []:
            key = ticker.get("symbol") if isinstance(ticker, dict) else ticker
            if key not in seen_tickers:
                seen_tickers.add(key)
                merged["stock_tickers"].append(ticker)
        for tag in out.get("tags") or []:
            key = tag.get("tag_name") if isinstance(tag, dict) else tag
            if key not in seen_tags:
                seen_tags.add(key)
                merged["tags"].append(tag)
    return merged


def _write_chunked(state: PipelineState, events: list) -> dict[str, Any]:
    """Write the article for a long episode by chunking ``clustered_events``.

    Each chunk gets a sub-state with just its slice of events; ``build_messages``
    renders the identical prompt over that slice, so each reply stays small enough
    to parse. The full ``clustered_events`` remains in the real graph state, so
    downstream timestamp anchoring is unaffected.
    """
    outputs: list[Any] = []
    for offset in range(0, len(events), _CHUNK_SIZE):
        batch = events[offset:offset + _CHUNK_SIZE]
        sub_state = {**state, "clustered_events": batch}
        outputs.append(invoke_json("writer", build_messages(sub_state)))
    return _merge_writer_outputs(outputs)


def write_article(state: PipelineState) -> dict[str, Any]:
    """Generate a structured financial article from clustered events.

    Long episodes (many clustered events) are written in event-position chunks
    (``_write_chunked``) to keep each LLM reply small enough to parse; shorter ones
    use a single call as before.
    """
    events = state.get("clustered_events", [])
    if len(events) > _CHUNK_THRESHOLD:
        result = _write_chunked(state, events)
    else:
        result = invoke_json("writer", build_messages(state))
    return postprocess(result, state)
