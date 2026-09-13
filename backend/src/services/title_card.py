"""A cover that is just the words — kicker, big title, footer — for pieces whose body
carries no chart worth putting on the card (the paid weekly, research articles).

Marp-style: one idea, large type on the site's dark ground. Wrapped by measured glyph
advance, not character count, so a CJK title and a Latin ticker break the same way.
"""
from __future__ import annotations

from xml.sax.saxutils import escape

from src.services.card_theme import AMBER, BG, FAINT, INK, LABEL, MARGIN, SIZE, advance, card_font

MAX_TITLE = 80
_SIZES = (72, 60, 50)   # try the largest that fits in MAX_LINES
_MAX_LINES = 4
_LINE_GAP = 1.3
_PUNCT = "，、。；：？！,;:"


def wrap(text: str, px: float, width: float) -> list[str]:
    """Greedy per-character wrap at measured width; a break lands after punctuation or a
    space when one is within reach. Pure."""
    lines: list[str] = []
    cur = ""
    for ch in text:
        # ponytail: hanging punctuation — a comma never starts a line, it overhangs.
        if advance(cur + ch, px) > width and cur and ch not in _PUNCT:
            cut = max(cur.rfind(" "), max(cur.rfind(p) for p in _PUNCT))
            if cut >= len(cur) // 2:
                lines.append(cur[:cut + 1].strip())
                cur = cur[cut + 1:].lstrip()
            else:
                lines.append(cur)
                cur = ""
        cur += ch
    if cur:
        lines.append(cur)
    return lines


def title_card_svg(title: str, kicker: str = "", footer: str = "tinboker.com · 非投資建議") -> str:
    font = card_font()
    width = SIZE - 2 * MARGIN
    title = title.strip()[:MAX_TITLE]
    for px in _SIZES:
        lines = wrap(title, px, width)
        if len(lines) <= _MAX_LINES:
            break
    else:
        lines = lines[:_MAX_LINES]
    block = px * _LINE_GAP * len(lines)
    y0 = (SIZE - block) / 2 + px          # vertically centred block, first baseline
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{SIZE}" height="{SIZE}" '
         f'viewBox="0 0 {SIZE} {SIZE}" font-family="{escape(font)}">',
         f'<rect width="{SIZE}" height="{SIZE}" fill="{BG}"/>',
         f'<text x="{SIZE-MARGIN}" y="{MARGIN+28}" fill="{AMBER}" font-size="26" '
         f'text-anchor="end" font-weight="700">TinBoker 聽播客</text>']
    if kicker:
        s.append(f'<text x="{MARGIN}" y="{MARGIN+28}" fill="{LABEL}" font-size="26">{escape(kicker)}</text>')
    for i, line in enumerate(lines):
        s.append(f'<text x="{MARGIN}" y="{y0 + i * px * _LINE_GAP:.0f}" fill="{INK}" '
                 f'font-size="{px}" font-weight="700">{escape(line)}</text>')
    s.append(f'<text x="{MARGIN}" y="{SIZE-MARGIN+4}" fill="{FAINT}" font-size="14">{escape(footer)}</text>')
    s.append("</svg>")
    return "\n".join(s)
