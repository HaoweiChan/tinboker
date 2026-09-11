"""本週聲量竄升 — the weekly recap cards, for tickers and for themes.

One renderer, two data shapes. The layout went through several rounds of revision; doing
each of those twice against a copy-pasted theme variant is exactly the cost this avoids.
A row therefore carries generic fields — a label, a subtitle, a count, last week's count,
a meta line — and the caller decides whether those mean a ticker or a theme.

Ranked by the WEEK-OVER-WEEK CHANGE in mention count, not by the count itself. Ranking by
raw count returns 台積電 / NVDA / GOOGL almost every week, which is true and useless: a
recap card has to be different each week or it is not content. Checked against ten weeks
of production data, the change ranking led with a different story each week.

Layout rule, learned the hard way: **one visual channel encodes one thing.** An earlier
version stacked last-week, bullish, neutral and bearish into a single horizontal bar, and
it read as though grey + red + green summed to this week's total — four quantities in one
length, two of which are not addable to the others. Now the bar length is this week's
count and nothing else, last week is a bullet-chart marker inside it, and sentiment is
demoted to coloured numerals on the caption line. Amber means "change", red and green mean
"sentiment", and neither colour does double duty.
"""
from __future__ import annotations

import logging
from xml.sax.saxutils import escape

from src.services.card_theme import (
    AMBER, BG, BORDER, DOWN, FAINT, INK, LABEL, MARGIN, SIZE, UP, advance, card_font,
)

logger = logging.getLogger(__name__)

MAX_ROWS = 6
MIN_MENTIONS = 5        # below this a "+3" is noise, not a trend
THEME_MIN_MENTIONS = 4  # themes are mentioned less often than the mega-caps

# The quantity bar is deliberately colourless — a neutral volume of talk. Colour on this
# card is reserved: amber for the change, red/green for sentiment.
QTY = "#5d7a90"

HEAD_Y = 78
SUB_Y = 122
CAPTION_Y = 168
RULE_Y = 200
ROW0_Y = 266         # first row's headline baseline
ROW_STEP = 124
BAR_DY, BAR_H = 14, 26          # bar offset below the headline baseline, and its height
CAP_DY = 66                     # caption baseline below the headline baseline
NAME_MAX = SIZE - 2 * MARGIN - 220   # identity room before the right-hand numbers
FOOT_Y = SIZE - MARGIN + 4


def _fmt_week(start: str, end: str) -> str:
    """08/31 - 09/06 — the hyphen is ASCII because the CJK face has no en dash."""
    return f"{start[5:7]}/{start[8:10]} - {end[5:7]}/{end[8:10]}"


def short_name(name_zh: str | None, name_en: str | None, aliases: list | None) -> str:
    """The name a person would say, not the one on the incorporation papers.

    ``stock_translations`` stores SPCX as "Space Exploration Technologies" with
    ``aliases: ["SpaceX"]`` — the alias is the usable label. An alias is only preferred
    when it is shorter AND contains a lowercase letter, because aliases also hold
    alternate ticker symbols (GOOGL carries "GOOG") and a symbol is not a name.
    """
    if (name_zh or "").strip():
        return name_zh.strip()
    best = (name_en or "").strip()
    for alt in aliases or []:
        alt = str(alt).strip()
        if alt and any(c.islower() for c in alt) and (not best or len(alt) < len(best)):
            best = alt
    return best


def _fit(text: str, px: float, width: float) -> str:
    """Last-resort trim, so a pathological 58-character name degrades instead of
    overrunning. With ``short_name`` in front of it this should not normally fire."""
    if advance(text, px) <= width:
        return text
    out = ""
    for ch in text:
        if advance(out + ch, px) > width - advance("…", px):
            break
        out += ch
    return out.rstrip() + "…"


def movers_card_svg(data: dict) -> str:
    """One week of podcast mention movement as a square card.

    ``data`` carries ``title``, ``subtitle``, ``caption``, and ``rows`` of
    ``{label, sublabel, n, prev, meta, sentiment}``, re-ranked here by change — where
    ``sentiment`` is ``(bull, neutral, bear)`` or ``None``. Sector mentions carry no
    sentiment (it is extracted per ticker only), so the theme card passes ``None`` and
    spends that line on representative members instead.
    """
    # Ranked here, not trusted from the caller: the title asserts a ranking, so the
    # renderer owns that invariant. A theme fixture that came straight out of json_agg
    # arrived unsorted and rendered +6, +2, +2, +5 down the page under the word 竄升.
    rows = sorted((data.get("rows") or []),
                  key=lambda r: (r["n"] - r.get("prev", 0), r["n"]), reverse=True)[:MAX_ROWS]
    if not rows:
        raise ValueError("movers card: no rows above the noise floor")

    font = card_font()
    # Scale off the largest of this week and last week, so a shrinking marker never
    # lands outside the track it is meant to annotate.
    peak = max(max(r["n"], r.get("prev", 0)) for r in rows) or 1
    track = SIZE - 2 * MARGIN

    s = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{SIZE}" height="{SIZE}" '
         f'viewBox="0 0 {SIZE} {SIZE}" font-family="{escape(font)}">',
         f'<rect width="{SIZE}" height="{SIZE}" fill="{BG}"/>']

    s.append(f'<text x="{MARGIN}" y="{HEAD_Y}" fill="{INK}" font-size="40" '
             f'font-weight="700">{escape(data["title"])}</text>')
    s.append(f'<text x="{SIZE-MARGIN}" y="{HEAD_Y}" fill="{AMBER}" font-size="26" '
             f'text-anchor="end" font-weight="700">TinBoker 聽播客</text>')
    s.append(f'<text x="{MARGIN}" y="{SUB_Y}" fill="{LABEL}" font-size="24">'
             f'{_fmt_week(data["week_start"], data["week_end"])} · '
             f'{escape(data["subtitle"])}</text>')
    s.append(f'<text x="{MARGIN}" y="{CAPTION_Y}" fill="{FAINT}" font-size="17">'
             f'{escape(data["caption"])}</text>')
    s.append(f'<line x1="{MARGIN}" x2="{SIZE-MARGIN}" y1="{RULE_Y}" y2="{RULE_Y}" '
             f'stroke="{BORDER}"/>')

    for i, r in enumerate(rows):
        cy = ROW0_Y + i * ROW_STEP
        n, prev = r["n"], r.get("prev", 0)

        # ── headline: who, how loud, how much louder — all on one line, so the ranking
        # reads down the right edge without the eye crossing the bar to find it.
        s.append(f'<text x="{MARGIN}" y="{cy}" fill="{INK}" font-size="30" '
                 f'font-weight="700">{escape(str(r["label"]))}'
                 f'<tspan fill="{LABEL}" font-size="21" font-weight="400" dx="12">'
                 f'{escape(_fit(str(r.get("sublabel") or ""), 21, NAME_MAX))}</tspan></text>')
        # "+7", not an arrow: cairosvg does no font fallback and the CJK face has no
        # U+2191, so an arrow would rasterise as a tofu box.
        # The delta is the ranking criterion, so it carries the most weight; the total
        # is context and steps back a size and a shade.
        s.append(f'<text x="{SIZE-MARGIN}" y="{cy+2}" fill="{AMBER}" font-size="44" '
                 f'font-weight="700" text-anchor="end">+{n - prev}</text>')
        s.append(f'<text x="{SIZE-MARGIN-104}" y="{cy}" fill="{LABEL}" font-size="22" '
                 f'text-anchor="end">{n} 次</text>')

        # ── bullet chart: bar length is this week and only this week ──
        by = cy + BAR_DY
        # Track kept dark: at a lighter value it reads as part of the bar and the
        # "how far along" comparison the bullet chart exists for disappears.
        s.append(f'<rect x="{MARGIN}" y="{by}" width="{track}" height="{BAR_H}" '
                 f'fill="{BORDER}" opacity="0.55"/>')
        s.append(f'<rect x="{MARGIN}" y="{by}" width="{n / peak * track:.1f}" '
                 f'height="{BAR_H}" fill="{QTY}"/>')
        if prev:
            # Thicker, and labelled: at 3px with no number the line reads as decoration
            # rather than as last week's value, which is the whole point of a bullet
            # chart. The label flips to the left of the tick when it would run off.
            tick = MARGIN + prev / peak * track
            s.append(f'<line x1="{tick:.1f}" x2="{tick:.1f}" y1="{by-8}" '
                     f'y2="{by+BAR_H+8}" stroke="{INK}" stroke-width="5"/>')
            mark = f"上週 {prev}"
            flip = tick + 10 + advance(mark, 16) > SIZE - MARGIN
            s.append(f'<text x="{tick + (-10 if flip else 10):.1f}" y="{by+BAR_H-8:.0f}" '
                     f'fill="{INK}" font-size="16" font-weight="700" '
                     f'text-anchor="{"end" if flip else "start"}">{mark}</text>')

        # ── caption: benchmark, breadth, sentiment — sentiment carries the only colour
        # "上週" is gone from here — the marker states it now, and repeating it was the
        # single longest item on a line that was already dense on a phone. Sentiment is
        # coloured but not bold: the words 多/空 carry the meaning, colour only echoes it,
        # because in a stock context red and green are read as price before sentiment.
        meta = escape(str(r.get("meta") or ""))
        sentiment = r.get("sentiment")
        if sentiment:
            bull, neutral, bear = sentiment
            meta += (f'<tspan fill="{UP}">多 {bull}</tspan>'
                     f'<tspan fill="{FAINT}"> · 中性 {neutral} · </tspan>'
                     f'<tspan fill="{DOWN}">空 {bear}</tspan>')
        s.append(f'<text x="{MARGIN}" y="{cy+CAP_DY}" fill="{FAINT}" '
                 f'font-size="18">{meta}</text>')

    s.append(f'<text x="{MARGIN}" y="{FOOT_Y}" fill="{FAINT}" font-size="14">'
             f'提及來自 Podcast 逐字稿 · tinboker.com · 非投資建議</text>')
    s.append("</svg>")
    return "\n".join(s)


def ticker_rows(rows: list[dict]) -> list[dict]:
    """Ticker movers as generic rows: ticker large, company name beside it."""
    out = []
    for r in rows:
        if r.get("n", 0) < MIN_MENTIONS:
            continue
        bull, bear = r.get("bull", 0), r.get("bear", 0)
        out.append({
            "label": r["ticker"], "sublabel": r.get("name") or "",
            "n": r["n"], "prev": r.get("prev", 0),
            "meta": f'{r.get("casts", 0)} 個節目 · ',
            "sentiment": (bull, max(0, r["n"] - bull - bear), bear),
        })
    return out


def theme_rows(rows: list[dict]) -> list[dict]:
    """Theme movers as generic rows.

    No sentiment: it is extracted per ticker, and a sector mention carries none. That
    line goes to representative members instead, which is the more useful thing anyway —
    "液冷散熱" means little until you see 雙鴻 and 奇鋐 next to it.
    """
    out = []
    for r in rows:
        if r.get("n", 0) < THEME_MIN_MENTIONS:
            continue
        picks = " · ".join(f'{m["ticker"]} {m["name"]}' for m in (r.get("members") or [])[:3])
        meta = f'成分股 {r.get("member_count", 0)} 檔 · {r.get("casts", 0)} 個節目'
        out.append({
            "label": r.get("name") or r["exposure_id"], "sublabel": "",
            "n": r["n"], "prev": r.get("prev", 0),
            "meta": f"{meta} · {picks}" if picks else meta,
            "sentiment": None,
        })
    return out
