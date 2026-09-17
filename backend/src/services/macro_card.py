"""Shareable macro card — one indicator's line, ONE named episode marked on it, and what
the host said about it. The stock card's sibling for episodes that name no stock.

Same theme and the same marker rule as ``stock_card`` (a mark is only drawn when the
event behind it can be named). Where the stock card has a volume pane, this has the
claim: a macro series has no volume, and the sentence is what the card is for.
cairosvg does no font fallback — one family, from ``card_font()``.
"""
from __future__ import annotations

from typing import Optional
from xml.sax.saxutils import escape

from src.services.card_theme import AMBER, BG, BORDER, DOWN, FAINT, INK, LABEL, MARGIN, SIZE, UP, card_font
from src.services.title_card import wrap

PY0, PY1 = 250, 700          # line pane
XLAB_Y = 732                 # date axis
FOOT_Y = SIZE - MARGIN + 4
CLAIM_PX, CLAIM_STEP, CLAIM_MAX_LINES = 30, 46, 3


def macro_card_svg(name: str, code: str, unit: str, pts: list[tuple[str, float]], span_label: str,
                   source: str, event: Optional[dict] = None, claim: str = "") -> str:
    """``pts`` is ``[(YYYY-MM-DD, value)]`` oldest first. ``event`` is ``{date, label}``."""
    if len(pts) < 2:
        raise ValueError(f"{code}: not enough data to draw")
    font = card_font()
    n = len(pts)
    px0, px1 = MARGIN, SIZE - MARGIN - 80
    lo, hi = min(v for _, v in pts), max(v for _, v in pts)
    pad = (hi - lo) * 0.08 or 1
    lo, hi = lo - pad, hi + pad
    decimals = 2 if hi < 1000 else 0

    def x(i: int) -> float:
        return px0 + i * (px1 - px0) / (n - 1)

    def y(v: float) -> float:
        return PY1 - (v - lo) / (hi - lo) * (PY1 - PY0)

    def f(v: float) -> str:
        return f"{v:,.{decimals}f}"

    last, change = pts[-1][1], pts[-1][1] - pts[0][1]
    colour = UP if change >= 0 else DOWN
    sign = "+" if change >= 0 else ""

    s = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{SIZE}" height="{SIZE}" '
         f'viewBox="0 0 {SIZE} {SIZE}" font-family="{escape(font)}">',
         f'<rect width="{SIZE}" height="{SIZE}" fill="{BG}"/>',
         f'<text x="{MARGIN}" y="78" fill="{INK}" font-size="44" font-weight="700">{escape(name)} '
         f'<tspan fill="{LABEL}" font-size="30">{escape(code)}</tspan></text>',
         f'<text x="{MARGIN}" y="146" fill="{colour}" font-size="64" font-weight="700">{f(last)}{escape(unit)}'
         f'<tspan font-size="30" dx="16">{sign}{f(change)} · {n}{escape(span_label)}</tspan></text>',
         f'<text x="{SIZE-MARGIN}" y="78" fill="{AMBER}" font-size="26" text-anchor="end" '
         f'font-weight="700">TinBoker 聽播客</text>',
         f'<text x="{SIZE-MARGIN}" y="110" fill="{LABEL}" font-size="20" text-anchor="end">'
         f'{pts[0][0]} ~ {pts[-1][0]}</text>']

    for k in range(5):
        v = lo + (hi - lo) * k / 4
        yy = y(v)
        s.append(f'<line x1="{px0}" x2="{px1}" y1="{yy:.1f}" y2="{yy:.1f}" stroke="{BORDER}"/>')
        s.append(f'<text x="{px1+8}" y="{yy+6:.1f}" fill="{LABEL}" font-size="19">{f(v)}</text>')

    path = " ".join(f'{"M" if i == 0 else "L"}{x(i):.1f},{y(v):.1f}' for i, (_, v) in enumerate(pts))
    s.append(f'<path d="{path} L{x(n-1):.1f},{PY1} L{x(0):.1f},{PY1} Z" fill="{colour}" opacity="0.10"/>')
    s.append(f'<path d="{path}" fill="none" stroke="{colour}" stroke-width="3" stroke-linejoin="round"/>')

    label = ""
    if event and event.get("date"):
        hit = next((i for i, (d, _) in enumerate(pts) if d >= event["date"]), None)
        if hit is not None:
            ex = x(hit)
            label = str(event.get("label") or pts[hit][0][5:])
            flip = ex > px0 + (px1 - px0) * 0.75
            s.append(f'<line x1="{ex:.1f}" x2="{ex:.1f}" y1="{PY0}" y2="{PY1}" stroke="{AMBER}" '
                     f'stroke-width="2" stroke-dasharray="6 5"/>')
            s.append(f'<circle cx="{ex:.1f}" cy="{y(pts[hit][1]):.1f}" r="7" fill="{AMBER}"/>')
            s.append(f'<text x="{ex + (-8 if flip else 8):.1f}" y="{PY0-10}" fill="{AMBER}" font-size="20" '
                     f'font-weight="700" text-anchor="{"end" if flip else "start"}">{escape(label)}</text>')

    for i in range(0, n, max(1, n // 5)):
        anchor = "start" if i == 0 else "middle"
        s.append(f'<text x="{px0 if i == 0 else x(i):.1f}" y="{XLAB_Y}" fill="{LABEL}" font-size="18" '
                 f'text-anchor="{anchor}">{pts[i][0][5:]}</text>')

    # The claim, centred in the space between the axis and the footer — it needs air
    # above it or it reads as a caption of the axis.
    lines = wrap(claim.strip(), CLAIM_PX, SIZE - 2 * MARGIN - 32)[:CLAIM_MAX_LINES] if claim.strip() else []
    if lines:
        block = 34 + len(lines) * CLAIM_STEP
        top = XLAB_Y + 40 + ((FOOT_Y - 40) - (XLAB_Y + 40) - block) / 2
        s.append(f'<rect x="{MARGIN}" y="{top:.0f}" width="5" height="{block:.0f}" fill="{AMBER}"/>')
        s.append(f'<text x="{MARGIN+24}" y="{top+20:.0f}" fill="{AMBER}" font-size="20" font-weight="700">'
                 f'{escape(label + " 的說法" if label else "節目的說法")}</text>')
        for k, line in enumerate(lines):
            s.append(f'<text x="{MARGIN+24}" y="{top+64+k*CLAIM_STEP:.0f}" fill="{INK}" '
                     f'font-size="{CLAIM_PX}">{escape(line)}</text>')

    s.append(f'<text x="{MARGIN}" y="{FOOT_Y}" fill="{FAINT}" font-size="14">資料：{escape(source)} · '
             f'說法來自 Podcast 逐字稿 · tinboker.com · 非投資建議</text>')
    s.append("</svg>")
    return "\n".join(s)
