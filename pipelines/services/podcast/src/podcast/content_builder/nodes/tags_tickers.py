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

from typing import Any

from src.pipeline.utils import extract_tags_and_tickers

from ..state import PipelineState


def derive_tags_tickers(state: PipelineState) -> dict[str, Any]:
    """Return ``{"tags": [...], "related_tickers": [...]}`` from ``markdown_report``."""
    tt = extract_tags_and_tickers({"summary_text": state.get("markdown_report", "")})
    return {"tags": tt["tags"], "related_tickers": tt["tickers"]}
