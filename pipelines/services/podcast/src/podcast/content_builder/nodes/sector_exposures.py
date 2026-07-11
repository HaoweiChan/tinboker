"""Deterministically derive sector/theme exposures from clustered events with validation."""

from __future__ import annotations

import json
from typing import Any

from shared.sectors import (
    flatten_exposure_ids,
    flatten_unresolved_trend_ids,
    load_universe,
    normalize_exposure_id,
    resolve_clustered_events,
)

from ..state import PipelineState

# A6: cap on brand-new candidates manufactured purely from ticker->sector CURATED
# membership (no alias was ever spoken). Keeps a ticker-heavy episode from fanning
# out into a huge, low-confidence verifier batch (see plan-review.md Gap 1).
_MAX_TICKER_DERIVED_CANDIDATES = 5


def _ticker_derived_candidates(
    extracted_tickers: set[str],
    already_matched_ids: set[str],
    insights_list: list[dict[str, Any]],
    clustered_events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """A6: manufacture sector-exposure candidates from ticker->sector membership.

    The string-alias matcher (``resolve_clustered_events``) only ever produces a
    candidate when the sector's own name/alias is spoken aloud — an episode that
    discusses a ticker at length but never says its sector's alias (P1) never gets
    a candidate at all. This fills that gap using the sector universe's CURATED
    membership only (deliberate editorial assignment, not a compiled market-cap
    list), capped at ``_MAX_TICKER_DERIVED_CANDIDATES`` total, and only for
    exposures the alias matcher didn't already find.

    Context (required for the verifier to judge relevance) is borrowed from
    wherever the ticker was actually discussed — ``ticker_insights[*].reasons``/
    ``risks`` sentence locations — since a purely ticker-derived candidate has no
    transcript span of its own (see plan-review.md Gap 2). A ticker with no located
    mention is skipped rather than sent to the verifier with empty context.
    """
    if not extracted_tickers:
        return []

    ticker_context: dict[str, str] = {}
    for insight in insights_list:
        if not isinstance(insight, dict):
            continue
        ticker = str(insight.get("ticker", "")).strip().upper()
        if not ticker or ticker not in extracted_tickers:
            continue
        spans = [
            (loc.get("start_index"), loc.get("end_index"))
            for loc in (insight.get("reasons") or []) + (insight.get("risks") or [])
            if isinstance(loc, dict) and loc.get("start_index") is not None and loc.get("end_index") is not None
        ]
        sentences: list[str] = []
        for start_idx, end_idx in spans:
            for event in clustered_events:
                for s in event.get("sentences", []) or []:
                    s_idx = s.get("index")
                    if s_idx is not None and start_idx <= s_idx <= end_idx:
                        sentences.append(s.get("content", ""))
        if sentences:
            ticker_context[ticker] = " ".join(sentences)

    seen_ids = set(already_matched_ids)
    candidates: list[dict[str, Any]] = []
    for exposure in load_universe().get("exposures", []):
        if len(candidates) >= _MAX_TICKER_DERIVED_CANDIDATES:
            break
        exposure_id = normalize_exposure_id(exposure.get("exposure_id"))
        if exposure_id in seen_ids:
            continue

        curated_members = [
            m for m in (exposure.get("members") or []) if str(m.get("source") or "") == "curated"
        ]
        matched_ticker = next(
            (
                str(m.get("ticker") or "").upper()
                for m in curated_members
                if str(m.get("ticker") or "").upper() in extracted_tickers
            ),
            None,
        )
        if not matched_ticker:
            continue
        context = ticker_context.get(matched_ticker)
        if not context:
            continue  # ticker was extracted but never located in a sentence -> skip

        seen_ids.add(exposure_id)
        candidates.append({
            "exposure_id": exposure_id,
            "exposure_type": exposure.get("exposure_type"),
            "display_name": exposure.get("display_name"),
            "mention_text": matched_ticker,
            "confidence": 0.6,
            "icon_id": exposure.get("icon_id"),
            "color_hex": exposure.get("color_hex"),
            "resolved_tickers": [
                {"ticker": str(m.get("ticker") or "").upper(), "name": str(m.get("name") or "")}
                for m in curated_members[:5]
            ],
            "total_matches": len(curated_members),
            "start_index": None,
            "end_index": None,
            "start_time": None,
            "end_time": None,
            # Internal-only markers, stripped before this candidate is persisted.
            "_context": context,
            "_ticker_derived": True,
        })
    return candidates


def _public(exp: dict[str, Any]) -> dict[str, Any]:
    """Strip internal-only (underscore-prefixed) keys before persisting an exposure."""
    return {k: v for k, v in exp.items() if not k.startswith("_")}


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

    # 3b. A6: manufacture candidates for sectors the alias matcher never found at
    # all, from ticker->sector curated membership. These are appended to the SAME
    # verifier batch as the keyword-matched ones, but tagged so the error handler
    # below can fail closed for them specifically (Gap 3).
    already_matched_ids = {str(e.get("exposure_id")) for e in sector_exposures}
    ticker_candidates = _ticker_derived_candidates(
        extracted_tickers, already_matched_ids, insights_list, state.get("clustered_events", []),
    )
    to_verify.extend(ticker_candidates)

    # 4. Batch verify the exposures that have no ticker co-occurrence
    if to_verify:
        exposures_json = []
        for idx, exp in enumerate(to_verify):
            start_idx = exp.get("start_index")
            end_idx = exp.get("end_index")

            # Find context sentences around this range in state["clustered_events"]
            context_sentences = []
            if start_idx is not None and end_idx is not None:
                for event in state.get("clustered_events", []):
                    for s in event.get("sentences", []):
                        s_idx = s.get("index")
                        if s_idx is not None and start_idx <= s_idx <= end_idx:
                            context_sentences.append(s.get("content", ""))

            context = (
                " ".join(context_sentences)
                if context_sentences
                else exp.get("_context") or exp.get("mention_text", "")
            )
            exposures_json.append({
                "index": idx,
                "sector_id": exp.get("exposure_id"),
                "display_name": exp.get("display_name"),
                "keyword": exp.get("mention_text"),
                "context": context,
                "resolved_tickers": [
                    t.get("ticker") for t in (exp.get("resolved_tickers") or []) if t.get("ticker")
                ],
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
                    new_exp = dict(exp)
                    if not exp.get("_ticker_derived"):
                        # Keep but clear resolved_tickers to avoid showing pre-defined
                        # stocks when no tickers were actually mentioned.
                        new_exp["resolved_tickers"] = []
                    verified_exposures.append(_public(new_exp))
                else:
                    print(f"  ❌ Filtering out sector exposure: {exp.get('display_name')} (reason: LLM verified as not relevant)")
        except Exception as e:
            # Fallback in case of LLM error: fail-open for the ORIGINAL keyword-matched
            # candidates (as before), but fail-CLOSED for A6's ticker-derived-only
            # candidates — those have no transcript alias match at all, so keeping
            # them on a verifier outage would silently reintroduce the wrong-sector
            # mislabeling A6/A7 exist to prevent, at greater scale (plan-review.md Gap 3).
            print(f"  ⚠ Warning: Sector verifier LLM call failed: {e}. Failing open for keyword-matched candidates only; dropping {sum(1 for e2 in to_verify if e2.get('_ticker_derived'))} ticker-derived candidate(s).")
            verified_exposures.extend(
                _public(exp) for exp in to_verify if not exp.get("_ticker_derived")
            )

    # 5. Recompute the flat arrays and return
    flat = flatten_exposure_ids(verified_exposures)
    return {
        "sector_exposures": verified_exposures,
        "unresolved_market_trends": unresolved_trends,
        **flat,
        "unresolved_market_trend_ids": flatten_unresolved_trend_ids(unresolved_trends),
    }
