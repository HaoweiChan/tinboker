"""Social cards builder: assembles AlphaMemo-style cards for each episode.

Produces a single ordered ``social_cards`` list — a cover card (the episode hook +
key insights) followed by one card per theme (heading + bullets, each theme's last
bullet stamped with its transcript timestamp). This one structure drives both the
Threads carousel/reply-chain (on the platform) and the on-page episode SEO
(JSON-LD ``Clip`` parts), so index ``i`` of the list == carousel image ``i`` ==
threaded reply ``i``.

Image URLs are filled in later by the upload step; here they are left ``None``.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

from shared.tickers import lookup_ticker

from ...exporters.ticker_insights import market_for_ticker, score_to_label
from ..state import PipelineState

logger = logging.getLogger(__name__)

# Threads carousels accept at most 20 items, so cap at cover + 19 themes.
MAX_CARDS = 20

# Ticker-overview grid: rows per card + hard ceiling on table cards so an episode
# with a long ticker rotation can't cascade into an endless run of grid slides.
ROWS_PER_TABLE = 7
MAX_TABLE_CARDS = 2

# Sentiment enum → (zh-TW chip text, CSS class). Both bullish tiers collapse to
# 看多, both bearish to 看空; NEUTRAL is 觀望. Classes match card_deck.py badges.
_SENTIMENT_BADGE = {
    "STRONG_BULLISH": ("看多", "sent-bull"),
    "BULLISH": ("看多", "sent-bull"),
    "NEUTRAL": ("觀望", "sent-neutral"),
    "BEARISH": ("看空", "sent-bear"),
    "STRONG_BEARISH": ("看空", "sent-bear"),
}
_MARKET_ZH = {"TW": "台股", "US": "美股", "HK": "港股", "KR": "韓股", "EU": "歐股"}
_SEVERITY_ZH = {"HIGH": "高", "MEDIUM": "中", "LOW": "低"}

# Detects a bullet that already carries its own trailing [MM:SS]/[HH:MM:SS] stamp
# (the marp_writer prompt asks for a timestamp at the end of each point).
_HAS_TRAILING_TS = re.compile(r"\[\d{1,2}:\d{2}(?::\d{2})?\]\s*$")


def format_timestamp(ms: Optional[int]) -> str:
    """Format a millisecond offset as ``[MM:SS]`` (or ``[HH:MM:SS]``); ``""`` if unknown."""
    if ms is None:
        return ""
    try:
        total = int(ms) // 1000
    except (TypeError, ValueError):
        return ""
    if total < 0:
        return ""
    hours, rem = divmod(total, 3600)
    minutes, seconds = divmod(rem, 60)
    if hours:
        return f"[{hours:02d}:{minutes:02d}:{seconds:02d}]"
    return f"[{minutes:02d}:{seconds:02d}]"


def cards_from_marp_slides(
    marp_slides: Optional[dict[str, Any]],
    key_insights: Optional[list[str]] = None,
    episode_title: str = "",
) -> list[dict[str, Any]]:
    """Build the ordered cover+theme card list from structured marp slides.

    Pure (no ``state``) so it is the single source of truth shared by the PNG
    social cards (:func:`build_social_cards`) and the on-page episode deck
    (``marp_converter.convert_marp``) — keeping the two visually identical.

    The cover carries the key insights as its hook; each theme card's last
    bullet is stamped with the slide's transcript timestamp *unless* a bullet
    already ends with its own ``[MM:SS]`` (the marp_writer prompt emits a
    per-point timestamp, which we must not double-stamp).
    """
    marp = marp_slides or {}
    insights = [s.strip() for s in (key_insights or []) if s and s.strip()]
    deck_title = (marp.get("title") or episode_title or "").strip()

    cards: list[dict[str, Any]] = [{
        "kind": "cover",
        "title": deck_title,
        "bullets": insights,
        "start_time_ms": None,
        "image_url": None,
    }]

    for slide in marp.get("slides", []):
        bullets = [b.strip() for b in (slide.get("bullet_points") or []) if b and str(b).strip()]
        # Skip bulletless slides (e.g. a Marp title slide) — an empty card would
        # desync the carousel↔reply indices on the platform side.
        if not bullets:
            continue
        start_ms = slide.get("start_time")
        stamp = format_timestamp(start_ms)
        if stamp and not any(_HAS_TRAILING_TS.search(b) for b in bullets):
            bullets = bullets[:-1] + [f"{bullets[-1]} {stamp}"]
        cards.append({
            "kind": "theme",
            "title": (slide.get("heading") or "").strip(),
            "bullets": bullets,
            "start_time_ms": start_ms,
            "image_url": None,
        })
        if len(cards) >= MAX_CARDS:
            break

    return cards


def _insight_rows(ticker_insights: Optional[dict[str, Any]]) -> list[dict[str, Any]]:
    """Pull the per-ticker rows out of the ``ticker_insights`` wrapper (or bare list)."""
    raw: Any = ticker_insights
    if isinstance(raw, dict):
        for key in ("ticker_insights", "ticker_recommendations"):
            if isinstance(raw.get(key), list):
                raw = raw[key]
                break
    return [r for r in raw if isinstance(r, dict)] if isinstance(raw, list) else []


def _sentiment_badge(score: Any) -> tuple[str, str]:
    """Map a 0–1 sentiment score → (zh-TW chip text, CSS class) via the 5-tier label."""
    try:
        label = score_to_label(float(score))
    except (TypeError, ValueError):
        label = "NEUTRAL"
    return _SENTIMENT_BADGE.get(label, _SENTIMENT_BADGE["NEUTRAL"])


def _risk_factor(risks: Any) -> str:
    """Worst-case risk severity across a ticker's risks → 高/中/低 (— if none)."""
    order = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}
    worst = 0
    for r in risks or []:
        worst = max(worst, order.get(str(r.get("severity", "")).upper(), 0))
    return {3: "高", 2: "中", 1: "低"}.get(worst, "—")


def _ticker_name_code(ticker: str) -> tuple[str, str]:
    """Resolve a symbol to (display name, code). Unknown symbols show the symbol alone."""
    info = lookup_ticker(ticker)
    if info and info.name and info.name != ticker:
        return info.name, ticker
    return ticker, ""


def _ticker_row(insight: dict[str, Any]) -> Optional[dict[str, str]]:
    ticker = str(insight.get("ticker", "")).strip()
    if not ticker:
        return None
    name, code = _ticker_name_code(ticker)
    sentiment, sentiment_class = _sentiment_badge(insight.get("sentiment_score"))
    return {
        "group": _MARKET_ZH.get(market_for_ticker(ticker), "其他"),
        "name": name, "code": code,
        "sentiment": sentiment, "sentiment_class": sentiment_class,
        "risk": _risk_factor(insight.get("risks")),
    }


def _analysis_card(insight: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Build one focus-analysis card from a ticker's top reason (deterministic)."""
    ticker = str(insight.get("ticker", "")).strip()
    reasons = [r for r in (insight.get("reasons") or []) if isinstance(r, dict)]
    if not ticker or not reasons:
        return None
    name, code = _ticker_name_code(ticker)
    top = reasons[0]
    lead = str(top.get("title", "")).strip()
    body = str(top.get("description", "")).strip() or str(insight.get("bluf_thesis", "")).strip()
    if not lead and not body:
        return None
    sentiment, sentiment_class = _sentiment_badge(insight.get("sentiment_score"))
    return {
        "kind": "analysis",
        "title": "產業焦點",
        "focus": f"{name} {code}".strip(),
        "lead": lead or body, "body": body if lead else "",
        "source": format_timestamp(top.get("start_time")),
        "sentiment": sentiment, "sentiment_class": sentiment_class,
        "start_time_ms": top.get("start_time"), "image_url": None,
    }


def cards_from_ticker_insights(
    ticker_insights: Optional[dict[str, Any]],
    episode_title: str = "",  # noqa: ARG001 — kept for signature parity with cards_from_marp_slides
) -> list[dict[str, Any]]:
    """Build the structured ticker deck (overview grid + focus-analysis cards).

    Pure + deterministic: reads the per-ticker ``ticker_insights`` rows directly,
    no LLM. Sentiment chips come from ``sentiment_score`` (via the 5-tier label),
    risk from the worst ``risks[].severity``, names from the ticker registry.
    """
    insights = _insight_rows(ticker_insights)
    if not insights:
        return []

    rows = [r for r in (_ticker_row(i) for i in insights) if r]
    cards: list[dict[str, Any]] = []
    if rows:
        cap = ROWS_PER_TABLE * MAX_TABLE_CARDS
        if len(rows) > cap:
            logger.warning(
                "ticker overview: %d tickers exceed the %d-row cap (%d table cards) — dropping %d",
                len(rows), cap, MAX_TABLE_CARDS, len(rows) - cap,
            )
            rows = rows[:cap]
        for start in range(0, len(rows), ROWS_PER_TABLE):
            cards.append({
                "kind": "ticker_table", "title": "本期提及標的與態度",
                "rows": rows[start:start + ROWS_PER_TABLE],
                "start_time_ms": None, "image_url": None,
            })

    # Focus-analysis cards: strongest-conviction tickers first (furthest from 0.5).
    def _conviction(i: dict[str, Any]) -> float:
        try:
            return abs(float(i.get("sentiment_score", 0.5)) - 0.5)
        except (TypeError, ValueError):
            return 0.0

    for insight in sorted(insights, key=_conviction, reverse=True):
        card = _analysis_card(insight)
        if card:
            cards.append(card)
        if len(cards) >= MAX_CARDS:
            break
    return cards


def build_social_cards(state: PipelineState) -> dict[str, Any]:
    """Join node: build ``social_cards`` from ``marp_slides`` + ``key_insights``."""
    cards = cards_from_marp_slides(
        state.get("marp_slides") or {},
        state.get("key_insights") or [],
        (state.get("episode_title") or ""),
    )

    # Nothing postable (no insights and no theme cards) → empty so the platform skips
    # cleanly instead of posting a blank cover.
    if len(cards) == 1 and not cards[0]["bullets"]:
        return {"social_cards": []}

    return {"social_cards": cards}
