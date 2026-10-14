"""Shareable intraday card — one index's day so far, drawn the way a quote app draws it:
the line from the open, the previous close as a dotted rule, the rest of the session left
empty so the reader can see it is still trading, and a lunch break as a gap.

The first image of every market-move post. Same theme and font rule as the other cards
(``card_theme``): cairosvg does no font fallback, so one family and no glyph outside it.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

from src.services.card_theme import AMBER, BG, BORDER, DOWN, FAINT, INK, LABEL, MARGIN, SIZE, UP, advance, card_font
from src.services.yahoo_chart import Intraday

PY0, PY1 = 300, 740          # line pane
XLAB_Y = 776                 # time axis
STATS_Y = 850                # 開盤 / 最高 / 最低 / 昨收
PEERS_Y = 960
FOOT_Y = SIZE - MARGIN + 4
GAP_SECONDS = 600            # a hole this long inside the session is a break, not a slow minute

TZ_LABEL = {"Asia/Taipei": "台北時間", "Asia/Tokyo": "東京時間", "Asia/Seoul": "首爾時間",
            "America/New_York": "紐約時間"}


def is_closed(day: Intraday) -> bool:
    return day.last_ts >= day.session_end - 60


def segments(points: list[tuple[int, float]]) -> list[list[tuple[int, float]]]:
    """Split where the tape stops for a break (Tokyo's lunch), so the line is not drawn
    straight across an hour nobody traded."""
    out: list[list[tuple[int, float]]] = []
    for p in points:
        if out and p[0] - out[-1][-1][0] <= GAP_SECONDS:
            out[-1].append(p)
        else:
            out.append([p])
    return out


def _f(v: float) -> str:
    return f"{v:,.2f}"


def signed(v: float, pct: bool = False) -> str:
    return f"{'+' if v >= 0 else '-'}{abs(v):,.2f}{'%' if pct else ''}"


def intraday_card_svg(name: str, code: str, day: Intraday,
                      peers: Optional[list[tuple[str, float]]] = None, source: str = "Yahoo Finance") -> str:
    """``peers`` is ``[(name, pct)]`` for the market's other indices, printed under the
    stats so one card answers "was it just this index?"."""
    if len(day.points) < 2:
        raise ValueError(f"{code}: not enough bars to draw")
    font = card_font()
    tz = ZoneInfo(day.tz)
    px0, px1 = MARGIN, SIZE - MARGIN - 120
    t0, t1 = day.session_start, max(day.session_end, day.last_ts)
    lo, hi = min(day.low, day.prev_close), max(day.high, day.prev_close)
    pad = (hi - lo) * 0.10 or day.prev_close * 0.002
    lo, hi = lo - pad, hi + pad
    colour = UP if day.change >= 0 else DOWN

    def x(ts: int) -> float:
        return px0 + (ts - t0) / (t1 - t0) * (px1 - px0)

    def y(v: float) -> float:
        return PY1 - (v - lo) / (hi - lo) * (PY1 - PY0)

    stamp = datetime.fromtimestamp(day.last_ts, tz)
    status = "收盤" if is_closed(day) else "盤中"
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{SIZE}" height="{SIZE}" '
         f'viewBox="0 0 {SIZE} {SIZE}" font-family="{escape(font)}">',
         f'<rect width="{SIZE}" height="{SIZE}" fill="{BG}"/>',
         f'<text x="{MARGIN}" y="78" fill="{INK}" font-size="44" font-weight="700">{escape(name)} '
         f'<tspan fill="{LABEL}" font-size="28">{escape(code)}</tspan></text>',
         f'<text x="{SIZE-MARGIN}" y="78" fill="{AMBER}" font-size="26" text-anchor="end" '
         f'font-weight="700">TinBoker 聽播客</text>',
         f'<text x="{SIZE-MARGIN}" y="112" fill="{LABEL}" font-size="22" text-anchor="end">'
         f'{status} {stamp:%Y-%m-%d %H:%M} {escape(TZ_LABEL.get(day.tz, day.tz))}</text>',
         f'<text x="{MARGIN}" y="178" fill="{INK}" font-size="80" font-weight="700">{_f(day.last)}</text>',
         f'<text x="{MARGIN}" y="236" fill="{colour}" font-size="40" font-weight="700">'
         f'{signed(day.pct, pct=True)}<tspan dx="18" font-size="32">({signed(day.change)})</tspan></text>']

    for k in range(5):
        v = lo + (hi - lo) * k / 4
        yy = y(v)
        s.append(f'<line x1="{px0}" x2="{px1}" y1="{yy:.1f}" y2="{yy:.1f}" stroke="{BORDER}"/>')
        s.append(f'<text x="{px1+10}" y="{yy+7:.1f}" fill="{LABEL}" font-size="20">'
                 f'{v:,.{0 if hi - lo > 50 else 2}f}</text>')

    segs = segments(day.points)
    for a, b in zip(segs, segs[1:]):
        gx0, gx1 = x(a[-1][0]), x(b[0][0])
        s.append(f'<rect x="{gx0:.1f}" y="{PY0}" width="{gx1-gx0:.1f}" height="{PY1-PY0}" '
                 f'fill="{BORDER}" opacity="0.6"/>')
        s.append(f'<text x="{(gx0+gx1)/2:.1f}" y="{PY0+30}" fill="{LABEL}" font-size="20" '
                 f'text-anchor="middle">午休</text>')

    for seg in segs:
        path = " ".join(f'{"M" if i == 0 else "L"}{x(t):.1f},{y(v):.1f}' for i, (t, v) in enumerate(seg))
        if len(seg) > 1:
            s.append(f'<path d="{path} L{x(seg[-1][0]):.1f},{PY1} L{x(seg[0][0]):.1f},{PY1} Z" '
                     f'fill="{colour}" opacity="0.14"/>')
        s.append(f'<path d="{path}" fill="none" stroke="{colour}" stroke-width="3" stroke-linejoin="round"/>')

    py = y(day.prev_close)
    s.append(f'<line x1="{px0}" x2="{px1}" y1="{py:.1f}" y2="{py:.1f}" stroke="{LABEL}" '
             f'stroke-width="2" stroke-dasharray="2 8"/>')
    tag = f"昨收 {_f(day.prev_close)}"
    # Above the rule when the day is down (the line lives under it), below when up.
    ty = py - 14 if day.change < 0 else py + 32
    s.append(f'<rect x="{px0}" y="{ty-24:.1f}" width="{advance(tag, 20)+20:.0f}" height="32" rx="6" '
             f'fill="{BG}" opacity="0.85"/>')
    s.append(f'<text x="{px0+10}" y="{ty:.1f}" fill="{LABEL}" font-size="20">{escape(tag)}</text>')
    s.append(f'<circle cx="{x(day.last_ts):.1f}" cy="{y(day.last):.1f}" r="8" fill="{colour}"/>')

    # Time axis: the open, then every whole hour of the session.
    ticks = [t0]
    h = int(datetime.fromtimestamp(t0, tz).replace(minute=0, second=0).timestamp()) + 3600
    while h <= t1:
        if x(h) - x(ticks[-1]) >= 70:
            ticks.append(h)
        h += 3600
    for i, t in enumerate(ticks):
        s.append(f'<text x="{x(t):.1f}" y="{XLAB_Y}" fill="{LABEL}" font-size="20" '
                 f'text-anchor="{"start" if i == 0 else "middle"}">{datetime.fromtimestamp(t, tz):%H:%M}</text>')

    col = (SIZE - 2 * MARGIN) / 4
    for i, (label, v) in enumerate((("開盤", day.open), ("最高", day.high), ("最低", day.low),
                                     ("昨收", day.prev_close))):
        cx = MARGIN + i * col
        s.append(f'<text x="{cx:.0f}" y="{STATS_Y}" fill="{LABEL}" font-size="22">{label}</text>')
        s.append(f'<text x="{cx:.0f}" y="{STATS_Y+42}" fill="{INK}" font-size="32" font-weight="700">'
                 f'{_f(v)}</text>')

    if peers:
        cx = MARGIN
        s.append(f'<text x="{cx}" y="{PEERS_Y}" fill="{LABEL}" font-size="24">同市場</text>')
        cx += advance("同市場", 24) + 24
        for pname, pct in peers:
            if cx > SIZE - MARGIN - 200:
                break
            s.append(f'<text x="{cx:.0f}" y="{PEERS_Y}" fill="{INK}" font-size="24">{escape(pname)} '
                     f'<tspan fill="{UP if pct >= 0 else DOWN}" font-weight="700">{signed(pct, pct=True)}</tspan></text>')
            cx += advance(f"{pname} {signed(pct, pct=True)}", 24) + 36

    s.append(f'<text x="{MARGIN}" y="{FOOT_Y}" fill="{FAINT}" font-size="14">資料：{escape(source)} · '
             f'盤中數據可能延遲 · tinboker.com · 非投資建議</text>')
    s.append("</svg>")
    return "\n".join(s)
