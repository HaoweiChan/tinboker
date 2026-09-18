"""Macro claims extractor node — the ticker extractor's sibling for indicators.

Optional by construction: any failure returns an empty list. A node that raises aborts
``app.invoke`` and the episode falls back to the placeholder summarizer (service.py), and
an optional field is never worth that.
"""

import json
from typing import Any

from ..llm import invoke_json, load_prompt
from ..macro_vocab import MACRO_SERIES
from ..state import PipelineState

MIN_CONFIDENCE = 0.6     # below this the model itself called it background, not a view
MAX_CLAIM_CHARS = 80
_DIRECTIONS = {"UP", "DOWN", "FLAT", "UNCLEAR"}
_HORIZONS = {"SHORT_TERM", "MEDIUM_TERM", "LONG_TERM", "UNCLEAR"}


def build_messages(state: PipelineState) -> list[dict[str, str]]:
    prompts = load_prompt("macro_extractor")
    vocabulary = "\n".join(f"  - {k}：{v}" for k, v in MACRO_SERIES.items())
    return [
        {"role": "system", "content": prompts["system"].format(vocabulary=vocabulary)},
        {"role": "user", "content": prompts["user"].format(
            events=json.dumps(state.get("clustered_events", []), ensure_ascii=False),
            source=state.get("source", "Podcast"),
            episode_title=state.get("episode_title", "Episode"),
        )},
    ]


def _sentence_starts(state: PipelineState) -> dict[int, float]:
    """sentence index → start in SECONDS (pipeline timings are milliseconds)."""
    out: dict[int, float] = {}
    for event in state.get("clustered_events") or []:
        for s in event.get("sentences") or []:
            if isinstance(s.get("index"), int) and isinstance(s.get("start"), (int, float)):
                out[s["index"]] = s["start"] / 1000.0
    return out


def _clean(text: Any, limit: int = 400) -> str:
    return " ".join(str(text or "").split())[:limit]


def postprocess(result: Any, state: PipelineState) -> dict[str, Any]:
    """Validate against the vocabulary, resolve the time from ``start_index``, and keep
    one claim per indicator — the most confident, since the mention key downstream is
    ``{episode}:macro:{indicator}`` and would otherwise keep whichever came first."""
    starts = _sentence_starts(state)
    best: dict[str, dict[str, Any]] = {}
    rows = result.get("macro_claims") if isinstance(result, dict) else None
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        indicator = str(row.get("indicator_id") or "").strip().upper()
        claim = _clean(row.get("claim"), MAX_CLAIM_CHARS)
        try:
            confidence = float(row.get("confidence") or 0)
        except (TypeError, ValueError):
            confidence = 0.0
        if indicator not in MACRO_SERIES or not claim or confidence < MIN_CONFIDENCE:
            continue
        idx = row.get("start_index")
        direction = str(row.get("direction_expected") or "").upper()
        horizon = str(row.get("time_horizon") or "").upper()
        clean = {
            "indicator_id": indicator,
            "display_name": _clean(row.get("display_name"), 40) or MACRO_SERIES[indicator],
            "level_quoted": _clean(row.get("level_quoted"), 80) or None,
            "direction_expected": direction if direction in _DIRECTIONS else "UNCLEAR",
            "claim": claim,
            "reasons": [_clean(r, 120) for r in (row.get("reasons") or []) if _clean(r)][:3],
            "implication": _clean(row.get("implication"), 160) or None,
            "time_horizon": horizon if horizon in _HORIZONS else "UNCLEAR",
            "quote": _clean(row.get("quote"), 300) or None,
            "start_index": idx if isinstance(idx, int) else None,
            # None when the index is missing or invented — never a guessed time.
            "start_time_s": starts.get(idx) if isinstance(idx, int) else None,
            "confidence": round(confidence, 2),
        }
        if indicator not in best or confidence > best[indicator]["confidence"]:
            best[indicator] = clean
    return {"macro_claims": list(best.values())}


def extract_macro(state: PipelineState) -> dict[str, Any]:
    try:
        result = invoke_json("macro_extractor", build_messages(state))
    except Exception as exc:  # noqa: BLE001 — one optional field must not abort the run
        print(f"  ⚠ macro extraction failed: {exc}")
        return {"macro_claims": []}
    return postprocess(result, state)
