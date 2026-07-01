"""Deterministically derive sector/theme exposures from clustered events with validation."""

from __future__ import annotations

import json
from typing import Any

from shared.sectors import (
    flatten_exposure_ids,
    flatten_unresolved_trend_ids,
    resolve_clustered_events,
)

from ..state import PipelineState


def derive_sector_exposures(state: PipelineState) -> dict[str, Any]:
    """Return resolved sector/theme exposure metadata and flat index arrays."""
    # 1. Resolve raw matches using deterministic string matching
    raw_result = resolve_clustered_events(state.get("clustered_events", []))
    sector_exposures = raw_result.get("sector_exposures", [])
    unresolved_trends = raw_result.get("unresolved_market_trends", [])

    # 2. Extract actually mentioned tickers from ticker_insights
    ticker_insights_data = state.get("ticker_insights") or {}
    if isinstance(ticker_insights_data, dict):
        insights_list = (
            ticker_insights_data.get("ticker_insights")
            or ticker_insights_data.get("ticker_recommendations")
            or []
        )
    else:
        insights_list = ticker_insights_data or []

    extracted_tickers = {
        str(item.get("ticker", "")).strip().upper()
        for item in insights_list
        if isinstance(item, dict) and item.get("ticker")
    }

    # 3. Separate exposures into auto-approved and to-verify
    verified_exposures = []
    to_verify = []

    for exp in sector_exposures:
        resolved_tickers = exp.get("resolved_tickers") or []
        constituent_tickers = {str(t.get("ticker", "")).strip().upper() for t in resolved_tickers}
        
        # If any constituent ticker overlap exists, auto-approve
        if constituent_tickers & extracted_tickers:
            verified_exposures.append(exp)
        else:
            to_verify.append(exp)

    # 4. Batch verify the exposures that have no ticker co-occurrence
    if to_verify:
        exposures_json = []
        for idx, exp in enumerate(to_verify):
            start_idx = exp.get("start_index")
            end_idx = exp.get("end_index")
            
            # Find context sentences around this range in state["clustered_events"]
            context_sentences = []
            for event in state.get("clustered_events", []):
                for s in event.get("sentences", []):
                    s_idx = s.get("index")
                    if s_idx is not None and start_idx <= s_idx <= end_idx:
                        context_sentences.append(s.get("content", ""))
            
            context = " ".join(context_sentences) if context_sentences else exp.get("mention_text", "")
            exposures_json.append({
                "index": idx,
                "sector_id": exp.get("exposure_id"),
                "display_name": exp.get("display_name"),
                "keyword": exp.get("mention_text"),
                "context": context
            })

        # Call LLM with "sector_verifier" role
        from ..llm import invoke_json, load_prompt
        prompts = load_prompt("sector_verifier")
        
        user_msg = prompts["user"].format(
            exposures_json=json.dumps(exposures_json, ensure_ascii=False, indent=2)
        )
        
        messages = [
            {"role": "system", "content": prompts["system"]},
            {"role": "user", "content": user_msg}
        ]
        
        try:
            verification_result = invoke_json("sector_verifier", messages)
            verifications = verification_result.get("verifications", [])
            
            # Map sector_id to is_relevant
            relevance_map = {}
            for item in verifications:
                sec_id = item.get("sector_id")
                is_relevant = item.get("is_relevant", False)
                relevance_map[sec_id] = is_relevant
                
            for exp in to_verify:
                sec_id = exp.get("exposure_id")
                if relevance_map.get(sec_id, False):
                    # Keep but clear resolved_tickers to avoid showing pre-defined stocks
                    # when no tickers were actually mentioned.
                    new_exp = dict(exp)
                    new_exp["resolved_tickers"] = []
                    verified_exposures.append(new_exp)
                else:
                    print(f"  ❌ Filtering out sector exposure: {exp.get('display_name')} (reason: LLM verified as not relevant)")
        except Exception as e:
            # Fallback in case of LLM error: fail-safe by keeping all exposures
            print(f"  ⚠ Warning: Sector verifier LLM call failed: {e}. Falling back to keeping all exposures.")
            verified_exposures.extend(to_verify)
    
    # 5. Recompute the flat arrays and return
    flat = flatten_exposure_ids(verified_exposures)
    return {
        "sector_exposures": verified_exposures,
        "unresolved_market_trends": unresolved_trends,
        **flat,
        "unresolved_market_trend_ids": flatten_unresolved_trend_ids(unresolved_trends),
    }
