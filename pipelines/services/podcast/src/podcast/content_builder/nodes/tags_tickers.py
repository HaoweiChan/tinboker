"""Derive episode ``tags`` + ``related_tickers`` from the generated summary.

Single source of truth shared by the automated pipeline (a graph node, so
``run_pipeline`` returns these fields) and the agent-backed regen orchestrator —
so both paths produce identical tags/related_tickers for the same summary.

The canonical join keys are the ASCII ``#tag:Slug`` / ``#ticker:SYMBOL`` links
embedded in the markdown summary (``extract_tags_and_tickers`` parses them as the
primary source). Keeping this in one place removes the prior duplication between
``pipeline/steps/summarize.py`` and the regen orchestrator.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from src.pipeline.utils import extract_tags_and_tickers

from ..state import PipelineState

logger = logging.getLogger(__name__)

_CJK_RE = re.compile(r"[㐀-鿿]")


def derive_tags_tickers(state: PipelineState) -> dict[str, Any]:
    """Return ``{"tags": [...], "related_tickers": [...]}`` from ``markdown_report``."""
    tt = extract_tags_and_tickers({"summary_text": state.get("markdown_report", "")})
    return {"tags": tt["tags"], "related_tickers": tt["tickers"]}


def dedup_tags_against_sectors(
    tags: list[str],
    sector_exposures: list[dict[str, Any]],
) -> list[str]:
    """Drop episode tags that duplicate a FIRED sector exposure (P2 systemic fix).

    Vocabulary pruning removed the definite tag↔sector collisions, but borderline
    entries were deliberately kept (e.g. ``Substrate``, ``OSAT``) and become
    redundant only when the matching sector actually fired on this episode. Called
    at output assembly (``run_pipeline`` + regen ``_assemble``) — the two points
    where both the final tags and the derived exposures exist.

    A tag is dropped when its slug or zh-TW display name matches a fired sector's
    display name or alias: exact normalized match, or CJK containment either way
    (contained string must be >=3 CJK chars — verified against the full 135-tag
    vocabulary x all 103 sectors with zero false positives; catches 半導體指數 vs
    半導體 and 供應鏈 vs HBM 供應鏈 without touching e.g. AI 晶片 vs 晶片).
    """
    if not tags or not sector_exposures:
        return list(tags or [])

    from shared.sectors import load_universe, normalize_exposure_id, normalize_text

    from ..tag_vocabulary import display_for

    fired_ids = {
        normalize_exposure_id(e.get("exposure_id"))
        for e in sector_exposures
        if e.get("exposure_id")
    }
    blocked: set[str] = {
        normalize_text(e["display_name"]) for e in sector_exposures if e.get("display_name")
    }
    for exposure in load_universe().get("exposures", []):
        if normalize_exposure_id(exposure.get("exposure_id")) in fired_ids:
            for alias in [exposure.get("display_name"), *(exposure.get("aliases") or [])]:
                if alias:
                    blocked.add(normalize_text(str(alias)))

    def _cjk_len(s: str) -> int:
        return len(_CJK_RE.findall(s))

    def _collides(tag: str) -> bool:
        for candidate in (normalize_text(tag), normalize_text(display_for(tag))):
            if not candidate:
                continue
            if candidate in blocked:
                return True
            for b in blocked:
                if _cjk_len(b) >= 3 and b in candidate:
                    return True
                if _cjk_len(candidate) >= 3 and candidate in b:
                    return True
        return False

    kept = [t for t in tags if not _collides(t)]
    dropped = [t for t in tags if t not in kept]
    if dropped:
        logger.info(
            "dedup_tags_against_sectors: dropped %d tag(s) duplicating fired sector "
            "exposures: %s", len(dropped), dropped,
        )
    return kept
