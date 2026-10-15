"""Ticker insights extractor node.

``build_messages`` / ``postprocess`` are factored out so the agent-backed
regeneration path reuses the identical prompt + parsing (see ``nodes/extractor.py``).
"""

import json
from copy import deepcopy
from typing import Any

from ..llm import invoke_json, load_prompt
from ..state import PipelineState


def build_messages(state: PipelineState) -> list[dict[str, str]]:
    """Render the ticker-extractor chat messages from ``clustered_events``."""
    prompts = load_prompt("ticker_extractor")
    events_json = json.dumps(state.get("clustered_events", []), ensure_ascii=False)

    user_msg = prompts["user"].format(
        events=events_json,
        source=state.get("source", "Podcast"),
        episode_title=state.get("episode_title", "Episode"),
    )

    return [
        {"role": "system", "content": prompts["system"]},
        {"role": "user", "content": user_msg},
    ]


def postprocess(result: Any, state: PipelineState) -> dict[str, Any]:
    """Anchor indexed evidence to source sentences; retain legacy time-only rows."""
    normalized = deepcopy(result)
    rows = normalized
    if isinstance(normalized, dict):
        rows = normalized.get("ticker_insights")
        if not isinstance(rows, list):
            rows = normalized.get("ticker_recommendations", [])
    sentences = state.get("sentences") or [
        sentence for event in state.get("clustered_events", [])
        for sentence in event.get("sentences", [])
    ]
    by_index = {sentence.get("index", i): sentence for i, sentence in enumerate(sentences)}
    for row in rows if isinstance(rows, list) else []:
        for field in ("reasons", "risks"):
            for evidence in row.get(field) or []:
                if "start_index" not in evidence and "end_index" not in evidence:
                    continue  # Legacy time-only evidence has no index claim to reconcile.
                start, end = evidence.get("start_index"), evidence.get("end_index")
                if (type(start) is not int or type(end) is not int or start < 0 or end < start
                        or end - start >= len(by_index)
                        or any(i not in by_index for i in range(start, end + 1))):
                    raise ValueError(f"{row.get('ticker')} {field}: invalid sentence span {start!r}–{end!r}")
                start_ms, end_ms = by_index[start].get("start"), by_index[end].get("end")
                if (type(start_ms) not in (int, float) or type(end_ms) not in (int, float)
                        or not 0 <= start_ms <= end_ms):
                    raise ValueError(f"{row.get('ticker')} {field}: sentence span lacks valid source timestamps")
                evidence.update(start_time=start_ms, end_time=end_ms)
    return {"ticker_insights": normalized}


def extract_tickers(state: PipelineState) -> dict[str, Any]:
    """Extract ticker insights from clustered events."""
    result = invoke_json("ticker_extractor", build_messages(state))
    return postprocess(result, state)
