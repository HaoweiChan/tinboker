"""Shareable stock card — candles, volume, and what the podcasts said, as one SVG.

Drawn here rather than screenshotted from the frontend because a headless browser is a
whole extra runtime to keep alive, and everything on the card is already in Postgres. The
output is a square so it drops straight into Threads/IG without being re-cropped.

Rasterised by ``og_image.svg_to_png``. Note the constraint that shape imposes: cairosvg
does NO font fallback, so this file must name exactly one family (see
``og_image.cjk_font_family``) rather than a CSS stack — a stack renders Latin text and
tofu boxes where the Chinese should be.
"""
from __future__ import annotations

import logging
from xml.sax.saxutils import escape

from src.services.card_theme import (
    AMBER, BG, BORDER, DOWN, FAINT, INK, LABEL, MARGIN, SIZE, UP,
    advance as _advance, card_font, fmt as _fmt,
)
from src.utils.market import infer_market

logger = logging.getLogger(__name__)

# Vertical rhythm. Every y below is measured against these, so moving a pane is one edit.
STAT_Y = 196                 # stat row, one line under the price
PY0, PY1 = 250, 760          # price pane; the top is left clear for spike markers
VY0, VY1 = 782, 890          # volume pane
XLAB_Y = 918                 # date axis, under the bottom pane
FOOT_Y = SIZE - MARGIN + 4   # shared last-line baseline for both footer blocks


def _volume_label(volume: float, is_tw: bool) -> str:
    """Volume in the unit that market's readers actually use."""
    if is_tw:
        return f"{volume / 1000:,.0f} 張"
    if volume >= 1e8:
        return f"{volume / 1e8:.2f} 億股"
    return f"{volume / 1e4:,.0f} 萬股"


def stock_card_svg(stock: dict, mentions: list[dict], days: int = 90) -> str:
    """One ticker's last ``days`` sessions as a square card.

    ``stock`` is a serialised CompanyDetail. ``mentions`` is one row per calendar day the
    ticker was talked about — ``{"d": "YYYY-MM-DD", "n": int, "bull": int, "bear": int}``
    — drawn as a third pane on the candles' own x axis, so a spike in talk sits directly
    under the price bar it belongs to.

    Mentions appear only as a total, never plotted against the price. Two richer versions
    were built and dropped: a daily histogram, and markers on the busiest days. Measured
    against 40 heavily-discussed tickers over 120 days, mention volume correlates +0.11
    with the SAME day's return and -0.02 with the NEXT day's — a coin flip — so marking a
    peak invites the reader to infer a cause the data does not support. A peak is only
    worth drawing next to a price once we can name the event behind it; the ``thesis``
    text on each mention is where that would come from.
    """
    points = (stock.get("chartData") or [])[-days:]
    if not points:
        raise ValueError(f"{stock.get('ticker')}: no chart data to draw")

    ticker = str(stock.get("ticker") or "")
    is_tw = infer_market(ticker) != "US"
    font = card_font()
    change = float(stock.get("change") or 0)
    colour = UP if change >= 0 else DOWN
    sign = "+" if change >= 0 else ""

    px0, px1 = MARGIN, SIZE - MARGIN - 80
    low = min(p["low"] for p in points)
    high = max(p["high"] for p in points)
    pad = (high - low) * 0.06 or 1
    low, high = low - pad, high + pad
    vmax = max(p["volume"] for p in points) or 1
    n = len(points)
    step = (px1 - px0) / n
    width = max(2, step * 0.62)

    def y(value: float) -> float:
        return PY1 - (value - low) / (high - low) * (PY1 - PY0)

    def x(i: int) -> float:
        return px0 + i * step + step / 2

    s = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{SIZE}" height="{SIZE}" '
         f'viewBox="0 0 {SIZE} {SIZE}" font-family="{escape(font)}">',
         f'<rect width="{SIZE}" height="{SIZE}" fill="{BG}"/>']

    # ── header ──
    s.append(f'<text x="{MARGIN}" y="78" fill="{INK}" font-size="44" font-weight="700">'
             f'{escape(str(stock.get("name") or ticker))} '
             f'<tspan fill="{LABEL}" font-size="34">{escape(ticker)}</tspan></text>')
    s.append(f'<text x="{MARGIN}" y="146" fill="{colour}" font-size="64" font-weight="700">'
             f'{float(stock.get("price") or 0):,.2f}'
             f'<tspan font-size="30" dx="16">{sign}{change:,.2f}  '
             f'{sign}{float(stock.get("changePercent") or 0):.2f}%</tspan></text>')
    s.append(f'<text x="{SIZE-MARGIN}" y="78" fill="{AMBER}" font-size="26" '
             f'text-anchor="end" font-weight="700">TinBoker 聽播客</text>')
    # "~" not "→": cairosvg does no font fallback, and the CJK face resolved above
    # has no U+2192 — the arrow rasterises as a tofu box. Verified on Heiti TC.
    s.append(f'<text x="{SIZE-MARGIN}" y="110" fill="{LABEL}" font-size="20" '
             f'text-anchor="end">日K · {points[0]["date"]} ~ {points[-1]["date"]}</text>')

    # ── stat row ──
    # Which extra stat exists is a market fact, not a preference: FinMind gives TW a P/E
    # and no market cap, Massive gives US the reverse. Cells for absent data are dropped
    # rather than printed as a zero that reads like a real number.
    bar = points[-1]
    prev_close = points[-2]["close"] if n > 1 else bar["open"]
    cells = [("開市", _fmt(bar["open"])), ("最高", _fmt(bar["high"])),
             ("最低", _fmt(bar["low"])), ("前收", _fmt(prev_close)),
             ("成交量", _volume_label(bar["volume"], is_tw))]
    if stock.get("pe"):
        cells.append(("本益比", _fmt(stock["pe"])))
    if stock.get("marketCap"):
        cap = float(stock["marketCap"])
        size = f"{cap/1e12:.2f} 兆" if cap >= 1e12 else f"{cap/1e8:,.0f} 億"
        cells.append(("市值", size if is_tw else f"{size} 美元"))
    # Space-between, not equal cells: the items differ a lot in width, and equal cell
    # origins make the gaps look random.
    widths = [_advance(k, 17) + 10 + _advance(v, 22) for k, v in cells]
    gap = (SIZE - 2 * MARGIN - sum(widths)) / max(1, len(cells) - 1)
    cx = float(MARGIN)
    for (key, value), w in zip(cells, widths):
        s.append(f'<text x="{cx:.0f}" y="{STAT_Y}" fill="{FAINT}" font-size="17">{key}'
                 f'<tspan fill="{INK}" font-size="22" font-weight="700" dx="10">'
                 f'{escape(value)}</tspan></text>')
        cx += w + gap

    # ── price pane ──
    last_y = y(points[-1]["close"])
    for k in range(5):
        value = low + (high - low) * k / 4
        yy = y(value)
        s.append(f'<line x1="{px0}" x2="{px1}" y1="{yy:.1f}" y2="{yy:.1f}" stroke="{BORDER}"/>')
        if abs(yy - last_y) > 22:   # the last-price tag would sit on top of this label
            s.append(f'<text x="{px1+8}" y="{yy+6:.1f}" fill="{LABEL}" '
                     f'font-size="19">{value:,.0f}</text>')

    for i, p in enumerate(points):
        c = UP if p["close"] >= p["open"] else DOWN
        cxx = x(i)
        s.append(f'<line x1="{cxx:.1f}" x2="{cxx:.1f}" y1="{y(p["high"]):.1f}" '
                 f'y2="{y(p["low"]):.1f}" stroke="{c}" stroke-width="1.3"/>')
        top, bottom = y(max(p["open"], p["close"])), y(min(p["open"], p["close"]))
        s.append(f'<rect x="{cxx-width/2:.1f}" y="{top:.1f}" width="{width:.1f}" '
                 f'height="{max(1, bottom-top):.1f}" fill="{c}"/>')
        vh = p["volume"] / vmax * (VY1 - VY0)
        # Volume takes the day's own colour, the convention every TW chart uses — heavy
        # volume on a red day and heavy volume on a green day mean opposite things, and
        # a single neutral colour throws that away. It was briefly drawn neutral to stop
        # it competing with a sentiment histogram that no longer exists.
        s.append(f'<rect x="{cxx-width/2:.1f}" y="{VY1-vh:.1f}" width="{width:.1f}" '
                 f'height="{vh:.1f}" fill="{c}" opacity="0.55"/>')

    s.append(f'<line x1="{px0}" x2="{px1}" y1="{last_y:.1f}" y2="{last_y:.1f}" '
             f'stroke="{colour}" stroke-dasharray="4 4"/>')
    s.append(f'<rect x="{px1+2}" y="{last_y-14:.1f}" width="78" height="28" fill="{colour}"/>'
             f'<text x="{px1+8}" y="{last_y+7:.1f}" fill="#000" font-size="18" '
             f'font-weight="700">{points[-1]["close"]:,.0f}</text>')

    # The first date label is anchored to the margin; centred on candle 0 it hangs past it.
    for i in range(0, n, max(1, n // 5)):
        anchor = "start" if i == 0 else "middle"
        s.append(f'<text x="{px0 if i == 0 else x(i):.1f}" y="{XLAB_Y}" fill="{LABEL}" '
                 f'font-size="18" text-anchor="{anchor}">{points[i]["date"][5:]}</text>')
    s.append(f'<text x="{px0}" y="{VY0-8}" fill="{LABEL}" font-size="18">成交量</text>')

    # ── podcast reach, stated as a total and not plotted ──
    # Mentions are calendar-dated and the candles are trading days, so a count is only
    # meaningful once each mention is attached to the first session on or after it.
    dates = [p["date"] for p in points]
    total_mentions = sum(
        int(m.get("n") or 0) for m in (mentions or [])
        if str(m.get("d") or "") and dates[0] <= str(m["d"]) <= dates[-1]
    )
    s.append(f'<text x="{px0}" y="{FOOT_Y-26}" fill="{FAINT}" font-size="15">'
             f'這 {len(points)} 個交易日內，Podcast 共提及 {total_mentions} 次</text>')

    source = "TWSE / FinMind" if is_tw else "Massive"
    s.append(f'<text x="{MARGIN}" y="{FOOT_Y}" fill="{FAINT}" font-size="14">'
             f'資料：{source} · 提及來自 Podcast 逐字稿 · tinboker.com · 非投資建議</text>')


    s.append("</svg>")
    return "\n".join(s)
