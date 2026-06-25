"""Marp converter node: transforms structured slide data into Marp markdown.

The on-page episode deck (``marp_markdown``) and the PNG social cards must look
identical, so both are built from the SAME unified card set:
``social_cards_builder.assemble_social_cards`` (cover → ticker table → themes →
focus-list) and ``card_deck.build_inline_deck_markdown`` renders it with the shared
TinBoker theme inlined as a ``<style>`` block (the in-browser ``marp-core`` can't
load an external ``--theme-set`` file the way the PNG render path does).
"""

from datetime import datetime, timezone
from typing import Any, Optional

from ..card_deck import build_inline_deck_markdown
from ..state import PipelineState
from .social_cards_builder import assemble_social_cards, cards_from_ticker_insights


def _date_str(state: PipelineState) -> str:
    """Best-effort ``YYYY.MM.DD`` for the cover from whatever date the state has."""
    raw = state.get("released_at_ms") or state.get("created_time") or state.get("date")
    if raw is None:
        return ""
    # Epoch milliseconds (int or numeric string).
    try:
        ms = int(raw)
        if ms > 10_000_000_000:  # clearly milliseconds, not seconds
            return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y.%m.%d")
    except (TypeError, ValueError):
        pass
    # ISO-ish string → take the date portion.
    s = str(raw)
    for sep in ("T", " "):
        s = s.split(sep, 1)[0]
    return s.replace("-", ".")


def convert_marp(state: PipelineState) -> dict[str, Any]:
    """Render the on-page episode deck from the SAME unified card set as the PNG
    social cards, so the on-page Marp and the published PNGs are identical."""
    cards = assemble_social_cards(state)
    return {"marp_markdown": _render(state, cards, content_type="podcast", size="1080x1080")}


def convert_marp_ticker(state: PipelineState) -> dict[str, Any]:
    """Build the ticker deck (overview grid + focus analysis) straight from ticker_insights.

    Deterministic — no LLM. These cards carry no cover/bullets, so the cover-guard
    in ``_render`` doesn't apply; emit whenever there is at least one card.
    """
    cards = cards_from_ticker_insights(
        state.get("ticker_insights") or {},
        state.get("episode_title") or "",
    )
    if not cards:
        return {"ticker_marp_markdown": ""}
    show_name = (state.get("source") or state.get("podcast_name") or "").strip()
    markdown = build_inline_deck_markdown(
        cards, show_name=show_name, date_str=_date_str(state),
        content_type="article", size="1240x780",
    )
    return {"ticker_marp_markdown": markdown}


def _render(state: PipelineState, cards: list[dict], content_type: str, size: str) -> str:
    show_name: Optional[str] = (state.get("source") or state.get("podcast_name") or "").strip()
    # A lone cover with no bullets is not worth a deck — return empty markdown.
    if len(cards) <= 1 and not (cards and cards[0].get("bullets")):
        return ""
    return build_inline_deck_markdown(
        cards, show_name=show_name, date_str=_date_str(state),
        content_type=content_type, size=size,
    )
