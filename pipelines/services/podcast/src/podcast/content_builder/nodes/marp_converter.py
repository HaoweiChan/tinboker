"""Marp converter node: transforms structured slide data into Marp markdown.

The on-page episode deck (``marp_markdown``) and the PNG social cards must look
identical, so both are built from the SAME card model + CSS:
``social_cards_builder.cards_from_marp_slides`` produces the cover+theme cards and
``card_deck.build_inline_deck_markdown`` renders them with the shared TinBoker
theme inlined as a ``<style>`` block (the in-browser ``marp-core`` can't load an
external ``--theme-set`` file the way the PNG render path does).
"""

from datetime import datetime, timezone
from typing import Any, Optional

from ..card_deck import build_inline_deck_markdown
from ..state import PipelineState
from .social_cards_builder import cards_from_marp_slides


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
    """Convert structured ``marp_slides`` to branded (inline-themed) Marp markdown."""
    cards = cards_from_marp_slides(
        state.get("marp_slides") or {},
        state.get("key_insights") or [],
        state.get("episode_title") or "",
    )
    return {"marp_markdown": _render(state, cards, content_type="podcast", size="1080x1080")}


def convert_marp_ticker(state: PipelineState) -> dict[str, Any]:
    """Convert ticker marp slides to branded (inline-themed) Marp markdown."""
    cards = cards_from_marp_slides(
        state.get("ticker_marp_slides") or {},
        [],
        state.get("episode_title") or "",
    )
    return {"ticker_marp_markdown": _render(state, cards, content_type="article", size="1240x780")}


def _render(state: PipelineState, cards: list[dict], content_type: str, size: str) -> str:
    show_name: Optional[str] = (state.get("source") or state.get("podcast_name") or "").strip()
    # A lone cover with no bullets is not worth a deck — return empty markdown.
    if len(cards) <= 1 and not (cards and cards[0].get("bullets")):
        return ""
    return build_inline_deck_markdown(
        cards, show_name=show_name, date_str=_date_str(state),
        content_type=content_type, size=size,
    )
