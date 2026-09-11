"""Shared visual tokens for the server-rendered share cards.

One place for the palette and canvas so the stock card and the heat card cannot drift
apart. These mirror the frontend's dark "終端機 Terminal" tokens
(frontend/src/index.css), hard-coded because an image generator cannot read CSS
variables; if the theme moves, these move with it.

Note the constraint every card here inherits: cairosvg does NO font fallback, so a card
must name exactly one family (``card_font()``) rather than a CSS stack, and must stay
inside glyphs that family actually has — an arrow or a dash outside it rasterises as a
tofu box rather than failing loudly.
"""
from __future__ import annotations

from src.services.og_image import cjk_font_family

SIZE = 1080     # square: Threads/IG post ratio, no re-crop
MARGIN = 56     # the only margin — sides, and the footer's bottom baseline

BG = "#07090e"       # --background
INK = "#e0e6eb"      # --foreground
AMBER = "#fbac23"    # --primary
BORDER = "#1c2531"   # --border
LABEL = "#c8d2dd"    # axis + secondary text: one step under INK, still readable
FAINT = "#bfc9d5"    # footer tier: one hair under LABEL, legible at 13-14px

# TW convention, applied to US tickers too: the audience is Taiwanese and a card that
# flips colour by market would be read wrong more often than it would be read right.
UP = "#ef4444"       # 漲
DOWN = "#22c55e"     # 跌
FLAT = "#4b5563"     # 中性


def card_font() -> str:
    """The one font family every card names. See the module docstring for why one."""
    return cjk_font_family()


def advance(text: str, px: float) -> float:
    """Rough rendered width. CJK is full-width, Latin roughly 0.6em.

    An estimate on purpose — measuring for real means a font toolkit in the request
    path, and the layouts using it are space-between, so being a few percent off shifts
    the gaps slightly instead of breaking anything.
    """
    return sum(px if ord(c) > 0x2E80 else px * 0.6 for c in text)


def fmt(v: float) -> str:
    """Money as people write it: no decimals when there are none to show."""
    return f"{v:,.0f}" if float(v).is_integer() else f"{v:,.2f}"
