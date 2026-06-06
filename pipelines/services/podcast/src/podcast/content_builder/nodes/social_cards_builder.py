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

from typing import Any, Optional

from ..state import PipelineState

# Threads carousels accept at most 20 items, so cap at cover + 19 themes.
MAX_CARDS = 20


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


def build_social_cards(state: PipelineState) -> dict[str, Any]:
    """Join node: build ``social_cards`` from ``marp_slides`` + ``key_insights``."""
    marp = state.get("marp_slides") or {}
    key_insights = [s.strip() for s in (state.get("key_insights") or []) if s and s.strip()]
    deck_title = (marp.get("title") or state.get("episode_title") or "").strip()

    cards: list[dict[str, Any]] = [{
        "kind": "cover",
        "title": deck_title,
        "bullets": key_insights,
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
        if stamp:
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

    # Nothing postable (no insights and no theme cards) → empty so the platform skips
    # cleanly instead of posting a blank cover.
    if len(cards) == 1 and not key_insights:
        return {"social_cards": []}

    return {"social_cards": cards}
