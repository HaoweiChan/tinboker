"""Render the social_cards list into a TinBoker-branded Marp deck (markdown + theme).

One slide per card → one PNG per card (via the marp_service /render-png endpoint),
so slide index i lines up exactly with social_cards[i]: cover first, then one theme
card per theme.

The palette matches tinboker.com's dark UI (deep slate-ink surfaces, near-white text,
the chrome-blue accent). The square 1080×1080 canvas is set via the Marp ``@size`` theme
annotation, so the deck must be rendered with this module's theme CSS loaded via
``marp --theme-set`` (inline ``<style>`` size metadata is NOT honored by marp-cli).
"""

from __future__ import annotations

import html
import re
import unicodedata
from typing import Any, Optional

from .brand_logo import LOGO_DATA_URI

# tinboker.com dark palette (from frontend/src/index.css .dark tokens)
BG = "#0f1117"        # --background  222 22% 7%
SURFACE = "#161a22"   # --card        222 21% 11%
TEXT = "#e7eaee"      # --foreground  220 16% 92%
SOFT = "#c7ccd6"      # slightly dimmed body text
MUTED = "#929baa"     # --muted-foreground 218 12% 62%
BORDER = "#262b36"    # --border      222 18% 18%

# Accent presets — site-blue (the UI accent) vs brand-yellow (the logo mark).
ACCENT_BLUE = ("#5b8dff", "rgba(91,141,255,.16)")     # --accent-info ~#5b8dff
ACCENT_YELLOW = ("#ffd23f", "rgba(255,210,63,.18)")   # brand logo yellow

# Accent by content type: podcast notes are yellow, article notes are blue.
# (Articles don't exist yet — the mapping is assigned now so they pick up blue later.)
ACCENT_BY_KIND = {"podcast": ACCENT_YELLOW, "article": ACCENT_BLUE}

THEME_NAME = "tinboker-cards"

_FONT = "'Noto Sans TC', 'Noto Sans CJK TC', 'PingFang TC', 'Microsoft JhengHei', sans-serif"
_TS_RE = re.compile(r"\s*(\[\d{1,2}:\d{2}(?::\d{2})?\])\s*$")
_BRAND = "TinBoker ｜ 聽播客"

# ---- Text measurement --------------------------------------------------------------
# No card text is ever clamped with an ellipsis: an "…" on a published image reads as a
# broken render. Instead every variable-length string is measured against the line
# budget of its box and trimmed to WHOLE sentences before it reaches the slide.

# Glyph advance in em for Noto Sans TC. CJK / full-width is exactly 1em; Latin is
# narrower but uppercase-heavy tickers (ARPU, DAU/MAU) run ~0.75em, so those are
# over-estimated on purpose — a line that wraps early costs nothing, one that
# overflows gets clipped.
_EM_UPPER = 0.75
_EM_OTHER_ASCII = 0.6
_EM_SPACE = 0.3
# Latin words wrap as a unit and CJK punctuation may not start a line (the browser
# pulls the previous glyph down with it) — reserve this much slack per line.
_LINE_SLACK_EM = 0.5
# A Latin word (with trailing spaces) is one unbreakable token; anything else is one glyph.
_TOKEN_RE = re.compile(r"[A-Za-z0-9][\x21-\x7e]*\s*|\s+|.", re.S)
_SENTENCE_RE = re.compile(r"[^。！？；!?;]+[。！？；!?;]*")
_CLAUSE_RE = re.compile(r"[^，、：,:]+[，、：,:]*")


def _em_width(text: str) -> float:
    w = 0.0
    for ch in text:
        if ch.isspace():
            w += _EM_SPACE
        elif ord(ch) < 0x80:
            w += _EM_UPPER if ch.isupper() else _EM_OTHER_ASCII
        elif unicodedata.east_asian_width(ch) in ("W", "F", "A"):
            w += 1.0
        else:
            w += _EM_OTHER_ASCII
    return w


def estimate_lines(text: str, font_px: float, width_px: float) -> int:
    """Greedy line-wrap estimate of ``text`` at ``font_px`` in a ``width_px`` box."""
    cap = max(1.0, width_px / font_px - _LINE_SLACK_EM)
    lines, cur = 1, 0.0
    for tok in _TOKEN_RE.findall(text.strip()):
        w = _em_width(tok)
        if cur > 0 and cur + w > cap:
            if tok.isspace():
                continue
            lines += 1
            cur = 0.0
        cur += w
        while cur > cap:          # a single token wider than the line (a long URL)
            lines += 1
            cur -= cap
    return lines


def fit_to_lines(text: str, max_lines: int, font_px: float, width_px: float, suffix: str = "") -> str:
    """Trim ``text`` so it renders in at most ``max_lines`` — never with an ellipsis.

    Keeps as many whole sentences as fit; if even the first sentence is too long, keeps
    whole clauses of it and closes with 「。」. Returns ``text`` unchanged when it fits.
    ``suffix`` (e.g. a trailing timestamp) is counted toward the lines but not returned.
    """
    text = (text or "").strip()

    def fits(s: str) -> bool:
        return estimate_lines(s + suffix, font_px, width_px) <= max_lines

    if not text or fits(text):
        return text

    def longest_prefix(parts: list[str]) -> str:
        out = ""
        for part in parts:
            candidate = (out + part).strip()
            if not fits(_close_sentence(candidate)):
                break
            out = candidate
        return _close_sentence(out) if out else ""

    sentences = _SENTENCE_RE.findall(text) or [text]
    first_sentence = sentences[0]
    out = (longest_prefix(sentences)
           or longest_prefix(_CLAUSE_RE.findall(first_sentence) or [first_sentence])
           # A single clause longer than the whole box: cut at the last glyph that fits.
           or longest_prefix(list(first_sentence)))
    return out


def _close_sentence(s: str) -> str:
    s = s.rstrip().rstrip("，、：；,:;")
    return s if not s or s[-1] in "。！？!?" else s + "。"


def pick_fitting(candidates: list[str], max_lines: int, font_px: float, width_px: float) -> str:
    """First candidate that fits whole; otherwise the first one trimmed to fit."""
    cands = [c.strip() for c in candidates if c and c.strip()]
    for c in cands:
        if estimate_lines(c, font_px, width_px) <= max_lines:
            return c
    return fit_to_lines(cands[0], max_lines, font_px, width_px) if cands else ""


# 產業焦點 one-liner box — MUST match `section.focus-list .flead` CSS below. Three
# items × (20+20 padding + 55 head + 14 gap + 3×45 lead) + heading ≈ 840px, inside
# the 864px content box, so three full leads always clear the watermark.
FOCUS_LEAD_FONT_PX = 30
FOCUS_LEAD_MAX_LINES = 3
FOCUS_LEAD_WIDTH_PX = 1080 - 88 * 2


def fit_focus_lead(*candidates: str) -> str:
    """The 產業焦點 one-liner: the first candidate that fits its 3-line box whole."""
    return pick_fitting(list(candidates), FOCUS_LEAD_MAX_LINES, FOCUS_LEAD_FONT_PX, FOCUS_LEAD_WIDTH_PX)


def card_theme_css(accent: str = ACCENT_BLUE[0], accent_soft: str = ACCENT_BLUE[1]) -> str:
    """Return the standalone Marp theme CSS for the cards, with the given accent.

    The leading metadata comment registers the theme name + a square slide size —
    that is what makes marp-cli export 1080×1080 PNGs.
    """
    return f"""
/* @theme {THEME_NAME} */
/* @size 1:1 1080px 1080px */
section {{
  width: 1080px; height: 1080px; box-sizing: border-box;
  display: flex; flex-direction: column; justify-content: flex-start;
  background: {BG}; color: {TEXT};
  font-family: {_FONT};
  /* Bottom padding reserves the watermark band (it sits ~52–92px from the bottom),
     so bounded+clipped content can never run under the logo. */
  padding: 84px 88px 132px; margin: 0;
  letter-spacing: .2px;
}}
/* Brand watermark, bottom-right: ONE ::before lockup — logo mark (left,
   as background) + wordmark text. marp-core reserves section::after for its
   pagination counter, so a brand ::after gets overridden; ::before is free. */
section::before {{
  content: "{_BRAND}";
  position: absolute; right: 64px; bottom: 52px;
  height: 40px; line-height: 40px; padding-left: 52px;
  background: url("{LOGO_DATA_URI}") left center / 40px 40px no-repeat;
  font-size: 24px; font-weight: 600; color: {MUTED}; letter-spacing: 1px;
}}
/* ---- Cover ---- */
section.cover {{ justify-content: center; }}
/* Never let a flex item be squeezed: a shrunk box with overflow:hidden clips its text
   through the middle of a glyph row, which is what sliced cover subtitles in half. With
   shrink off, the fit tiers below decide the size and every visible line is whole. */
section.cover > * {{ flex: 0 0 auto; }}
section.cover .label {{
  font-size: 30px; font-weight: 800; letter-spacing: 8px;
  color: {accent}; text-transform: uppercase; margin-bottom: 28px;
}}
section.cover h1 {{ font-size: 132px; font-weight: 900; line-height: 1.04; margin: 0 0 18px; color: {TEXT}; }}
section.cover .subtitle {{
  font-size: 46px; font-weight: 600; line-height: 1.34; color: {SOFT}; margin: 6px 0 30px;
}}
section.cover .date {{ font-size: 34px; color: {MUTED}; margin-bottom: 36px; }}
section.cover .rule {{ width: 132px; height: 10px; background: {accent}; border-radius: 6px; margin-bottom: 40px; }}
section.cover .hook {{
  font-size: 40px; line-height: 1.6; font-weight: 500; color: {SOFT};
}}
/* Cover fit tiers (chosen per card by measured text in _cover_slide) — the episode title
   and the hook are both unbounded in length, so the type scales to fit the canvas and
   the hook drops whole insights rather than ever ending in an ellipsis. Keep in sync
   with _COVER_TIERS. */
section.cover.fit-s h1 {{ font-size: 112px; }}
section.cover.fit-s .subtitle {{ font-size: 42px; }}
section.cover.fit-s .hook {{ font-size: 35px; }}
section.cover.fit-xs h1 {{ font-size: 96px; }}
section.cover.fit-xs .subtitle {{ font-size: 38px; }}
section.cover.fit-xs .hook {{ font-size: 31px; }}
section.cover.fit-xxs h1 {{ font-size: 84px; }}
section.cover.fit-xxs .subtitle {{ font-size: 34px; }}
section.cover.fit-xxs .hook {{ font-size: 27px; }}
/* ---- Theme card ---- */
section.theme h2 {{
  font-size: 52px; font-weight: 800; line-height: 1.3; margin: 0 0 36px; color: {TEXT};
  padding: 20px 28px 20px 26px; flex: 0 0 auto;
  border-left: 12px solid {accent};
  background: linear-gradient(90deg, {accent_soft}, rgba(0,0,0,0));
}}
/* Bound the bullet list to the space left after the heading and clip any overflow,
   so a dense card never spills into the watermark band (it clips cleanly instead). */
section.theme ul {{ list-style: none; padding: 0; margin: 0; flex: 1 1 auto; min-height: 0; overflow: hidden; }}
section.theme li {{
  position: relative; padding-left: 40px; margin-bottom: 26px;
  font-size: 37px; line-height: 1.52; font-weight: 500; color: {SOFT};
}}
section.theme li:last-child {{ margin-bottom: 0; }}
section.theme li::before {{ content: "▍"; position: absolute; left: 0; top: 2px; color: {accent}; font-size: 34px; }}
section.theme .ts {{ color: {accent}; font-weight: 700; font-size: .82em; white-space: nowrap; }}
/* Content-aware fit tiers (chosen per card by char volume in _theme_slide) — shrink
   type so dense cards FIT instead of clipping. Keep these in sync with _THEME_TIERS. */
section.theme.fit-s h2 {{ font-size: 50px; margin-bottom: 32px; }}
section.theme.fit-s li {{ font-size: 32px; line-height: 1.50; margin-bottom: 22px; }}
section.theme.fit-xs h2 {{ font-size: 46px; margin-bottom: 30px; }}
section.theme.fit-xs li {{ font-size: 28px; line-height: 1.45; margin-bottom: 18px; }}
/* ---- Sentiment badges (5-tier enum → low-noise chip, dark surface) ---- */
.badge {{ display: inline-block; padding: 7px 22px; border-radius: 8px;
  font-size: 28px; font-weight: 800; letter-spacing: 1.5px; white-space: nowrap; }}
.sent-bull {{ color: #4ade80; background: rgba(74,222,128,.14); }}
.sent-neutral {{ color: {ACCENT_YELLOW[0]}; background: rgba(255,210,63,.16); }}
.sent-bear {{ color: #f87171; background: rgba(244,113,113,.15); }}
/* ---- Ticker-table card (financial-terminal grid) ---- */
section.ticker-table h2 {{
  font-size: 50px; font-weight: 800; margin: 0 0 40px; color: {TEXT};
  padding-left: 22px; border-left: 12px solid {accent};
}}
section.ticker-table .rows {{ display: flex; flex-direction: column; border-top: 1px solid {BORDER}; }}
section.ticker-table .row {{
  display: flex; align-items: center; gap: 22px;
  padding: 22px 6px; border-bottom: 1px solid {BORDER};
}}
/* No market column: the code beside the name already says which exchange it is, and
   dropping it gives the 132px back to long company names. */
section.ticker-table .name {{ flex: 1 1 auto; font-size: 38px; font-weight: 600; color: {TEXT}; }}
section.ticker-table .name .code {{ color: {MUTED}; font-weight: 500; font-size: .8em; margin-left: 10px; }}
section.ticker-table .risk {{ flex: 0 0 168px; text-align: right; font-size: 28px; color: {SOFT}; }}
section.ticker-table .risk b {{ color: {accent}; font-weight: 800; }}
/* ---- Analysis card (notched fieldset, deterministic — no <fieldset>) ---- */
section.analysis h2 {{ font-size: 46px; font-weight: 800; margin: 0 0 36px; color: {TEXT}; }}
section.analysis .card {{
  position: relative; border: 1px solid {accent}; border-radius: 14px;
  padding: 52px 40px 40px; margin-top: 18px;
}}
section.analysis .fl-label {{
  position: absolute; top: 0; left: 32px; transform: translateY(-50%);
  background: {BG}; padding: 0 16px;
  font-size: 27px; font-weight: 800; letter-spacing: 1px; color: {accent};
}}
section.analysis .lead {{ font-size: 40px; font-weight: 800; line-height: 1.45; color: {TEXT}; margin: 0 0 24px; }}
section.analysis .lead .src {{
  font-size: .62em; font-weight: 700; color: {MUTED}; margin-left: 14px;
  background: {SURFACE}; padding: 4px 12px; border-radius: 6px; white-space: nowrap;
}}
section.analysis .body {{ font-size: 35px; line-height: 1.62; font-weight: 500; color: {SOFT}; margin: 0; }}
section.analysis .meta {{ margin-top: 36px; }}
/* ---- Focus list (aggregated 產業焦點 — several tickers per slide) ---- */
section.focus-list h2 {{
  font-size: 50px; font-weight: 800; margin: 0 0 30px; color: {TEXT};
  padding-left: 22px; border-left: 12px solid {accent};
}}
section.focus-list .flist {{ display: flex; flex-direction: column; }}
section.focus-list .fitem {{ padding: 20px 0; border-bottom: 1px solid {BORDER}; }}
section.focus-list .fitem:first-child {{ border-top: 1px solid {BORDER}; }}
section.focus-list .fhead {{ display: flex; align-items: center; gap: 18px; margin-bottom: 14px; }}
section.focus-list .fname {{ font-size: 38px; font-weight: 800; color: {TEXT}; }}
section.focus-list .fhead .src {{
  margin-left: auto; font-size: 24px; font-weight: 700; color: {MUTED};
  background: {SURFACE}; padding: 4px 14px; border-radius: 6px; white-space: nowrap;
}}
/* No line-clamp: the lead is pre-trimmed to whole sentences that fit 3 lines
   (fit_focus_lead), so it never ends in "…". Keep in sync with FOCUS_LEAD_*. */
section.focus-list .flead {{
  font-size: {FOCUS_LEAD_FONT_PX}px; line-height: 1.5; font-weight: 500; color: {SOFT}; margin: 0;
}}
""".strip()


def theme_css_for(content_type: str = "podcast") -> str:
    """Theme CSS for a content type: 'podcast' → yellow, 'article' → blue."""
    accent, soft = ACCENT_BY_KIND.get(content_type, ACCENT_YELLOW)
    return card_theme_css(accent, soft)


# Default theme = podcast (yellow), the only content type that produces cards today.
CARD_THEME_CSS = theme_css_for("podcast")


def _wrap_timestamp(bullet: str) -> str:
    """HTML-escape a bullet and wrap a trailing [MM:SS]/[HH:MM:SS] in a styled span."""
    m = _TS_RE.search(bullet)
    if not m:
        return html.escape(bullet)
    body = html.escape(bullet[: m.start()].rstrip())
    return f'{body} <span class="ts">{html.escape(m.group(1))}</span>'


# Per-tier cover metrics — MUST match the `section.cover.fit-*` CSS above.
# (class suffix, h1 font px, subtitle font px, hook font px)
_COVER_TIERS = [
    ("",        132, 46, 40),
    ("fit-s",   112, 42, 35),
    ("fit-xs",   96, 38, 31),
    ("fit-xxs",  84, 34, 27),
]
# Cover furniture that does not scale: label (30px + 28 margin), date (34px + 36
# margin), and the accent rule (10px + 40 margin), each with its line box.
_COVER_FIXED_PX = (30 * 1.2 + 28) + (34 * 1.2 + 36) + (10 + 40)
# The episode title (feed-supplied, unbounded) gets at most this many lines at the
# smallest tier; anything longer is trimmed to whole clauses.
_COVER_SUBTITLE_MAX_LINES = 3


def _cover_height(tier: tuple, title: str, subtitle: str, hook: str) -> float:
    _, h1f, subf, hookf = tier
    width = 1080 - _SIDE_PAD_PX
    height = _COVER_FIXED_PX + estimate_lines(title, h1f, width) * h1f * 1.04 + 18
    if subtitle:
        height += estimate_lines(subtitle, subf, width) * subf * 1.34 + 36
    if hook:
        height += estimate_lines(hook, hookf, width) * hookf * 1.6
    return height


def _cover_tier(title: str, subtitle: str, hook: str) -> Optional[str]:
    """Largest cover tier whose measured height fits the canvas, or None if none does."""
    for tier in _COVER_TIERS:
        if _cover_height(tier, title, subtitle, hook) <= _THEME_BUDGET_PX:
            return tier[0]
    return None


def _cover_fit_suffix(title: str, subtitle: str, hook: str) -> str:
    """Pick the largest cover tier whose estimated height fits the canvas.

    The episode title arrives from the show's own feed and can be any length, and the
    hook is three key insights joined — together they routinely overflow 864px at full
    size. Falls back to the smallest tier (callers trim the hook so it then fits).
    """
    tier = _cover_tier(title, subtitle, hook)
    return _COVER_TIERS[-1][0] if tier is None else tier


def _join_hook(insights: list[str]) -> str:
    hook = "，".join(s.strip().rstrip("。") for s in insights)
    return hook + "。" if hook else ""


def _cover_layout(title: str, subtitle: str, insights: list[str]) -> tuple[str, str]:
    """(tier suffix, hook) — the most whole insights (≤3) that fit, at the largest type.

    Never clamps: when all three don't fit even at the smallest tier, trailing insights
    are dropped; a single insight too long for the space left is trimmed to whole
    clauses by :func:`fit_to_lines`.
    """
    for n in range(min(3, len(insights)), 0, -1):
        hook = _join_hook(insights[:n])
        tier = _cover_tier(title, subtitle, hook)
        if tier is not None:
            return tier, hook
    smallest = _COVER_TIERS[-1]
    hookf = smallest[3]
    room = _THEME_BUDGET_PX - _cover_height(smallest, title, subtitle, "")
    lines = int(room // (hookf * 1.6))
    hook = fit_to_lines(_join_hook(insights[:1]), lines, hookf, 1080 - _SIDE_PAD_PX) if lines > 0 else ""
    return smallest[0], hook


def _cover_slide(card: dict, show_name: str, date_str: str) -> str:
    # Show name wins: the LLM marp deck title hallucinates famous brands (e.g. 股癌)
    # for unrelated shows, so the cover must use the deterministic podcast name.
    raw_title = (show_name or card.get("title") or "").strip()
    insights = [b.strip() for b in (card.get("bullets") or []) if b and b.strip()]
    raw_subtitle = fit_to_lines(
        (card.get("subtitle") or "").strip(), _COVER_SUBTITLE_MAX_LINES,
        _COVER_TIERS[-1][2], 1080 - _SIDE_PAD_PX,
    )
    suffix, raw_hook = _cover_layout(raw_title, raw_subtitle, insights)
    title, subtitle, hook = html.escape(raw_title), html.escape(raw_subtitle), html.escape(raw_hook)
    cls = f"cover {suffix}".strip()
    lines = [f"<!-- _class: {cls} -->", "", '<div class="label">Podcast Memo</div>', "", f"# {title}", ""]
    if subtitle:
        lines.append(f'<div class="subtitle">{subtitle}</div>')
    if date_str:
        lines.append(f'<div class="date">{html.escape(date_str)}</div>')
    lines.append('<div class="rule"></div>')
    if hook:
        lines.append(f'<div class="hook">{hook}</div>')
    return "\n".join(lines)


# Per-tier theme metrics — MUST match the `section.theme.fit-*` CSS above.
# (class suffix, li font px, li line-height, li margin px, h2 font px, h2 margin px)
_THEME_TIERS = [
    ("",        37, 1.52, 26, 52, 36),
    ("fit-s",   32, 1.50, 22, 50, 32),
    ("fit-xs",  28, 1.45, 18, 46, 30),   # readability floor — cut words, not type
]
_THEME_BUDGET_PX = 1080 - 84 - 132   # canvas minus top padding minus watermark band
_SIDE_PAD_PX = 88 * 2                 # left+right section padding
_LI_INDENT_PX = 40                    # li padding-left (bullet marker)
_H2_INSET_PX = 12 + 28 + 26           # h2 border-left + horizontal padding


def _theme_height(tier: tuple, heading: str, bullets: list[str]) -> float:
    _, lf, lh, lm, hf, hm = tier
    li_width = 1080 - _SIDE_PAD_PX - _LI_INDENT_PX
    ul_lines = sum(estimate_lines(b, lf, li_width) for b in bullets)
    ul_h = ul_lines * lf * lh + max(0, len(bullets) - 1) * lm
    return _theme_h2_height(heading, hf, hm) + ul_h


def _theme_h2_height(heading: str, hf: int, hm: int) -> float:
    # 40 = h2 vertical padding; the width loses the accent border + horizontal padding.
    return estimate_lines(heading, hf, 1080 - _SIDE_PAD_PX - _H2_INSET_PX) * hf * 1.3 + 40 + hm


def _theme_tier(heading: str, bullets: list[str]) -> Optional[str]:
    """Largest theme tier whose measured height fits the card, or None if none does."""
    for tier in _THEME_TIERS:
        if _theme_height(tier, heading, bullets) <= _THEME_BUDGET_PX:
            return tier[0]
    return None


def _theme_fit_suffix(heading: str, bullets: list[str]) -> str:
    """Pick the largest type tier whose estimated height fits the card.

    Deterministic auto-fit on measured line wraps so dense cards shrink to FIT rather
    than clip. Falls back to the smallest tier (callers drop bullets so it then fits)."""
    tier = _theme_tier(heading, bullets)
    return _THEME_TIERS[-1][0] if tier is None else tier


# Word budget for a theme card. Shrinking type to fit everything produced a wall of
# 24px text; instead a card carries at most this many points, each at most
# _THEME_BULLET_MAX_LINES lines at the fit-s size, and never goes below fit-xs.
MAX_THEME_BULLETS = 4
_THEME_BULLET_MAX_LINES = 3


def _split_stamp(bullet: str) -> tuple[str, str]:
    m = _TS_RE.search(bullet)
    return (bullet[: m.start()].rstrip(), m.group(1)) if m else (bullet, "")


def _join_stamp(body: str, stamp: str) -> str:
    return f"{body} {stamp}" if stamp else body


def _fit_theme_bullets(heading: str, bullets: list[str]) -> list[str]:
    """Trim a theme card to its word budget: ≤4 points, each ≤3 whole-sentence lines,
    then drop trailing points until the card fits at a readable size.

    A dropped point's timestamp moves to the new last point, so the card still links
    back to its place in the episode.
    """
    li_width = 1080 - _SIDE_PAD_PX - _LI_INDENT_PX
    _, lf, *_ = _THEME_TIERS[1]  # fit-s font: the per-point budget is measured there

    def carry(kept: list[str], dropped: list[str]) -> None:
        stamps = [s for s in (_split_stamp(b)[1] for b in dropped) if s]
        body, own = _split_stamp(kept[-1])
        if stamps and not own:
            kept[-1] = _join_stamp(body, stamps[-1])

    kept = []
    for b in bullets[:MAX_THEME_BULLETS]:
        body, stamp = _split_stamp(b)
        suffix = f" {stamp}" if stamp else ""
        body = fit_to_lines(body, _THEME_BULLET_MAX_LINES, lf, li_width, suffix=suffix)
        if body:
            kept.append(_join_stamp(body, stamp))
    if not kept:
        return []
    carry(kept, bullets[MAX_THEME_BULLETS:])
    while len(kept) > 1 and _theme_tier(heading, kept) is None:
        dropped = kept.pop()
        carry(kept, [dropped])
    return kept


def _theme_slide(card: dict) -> str:
    raw_heading = (card.get("title") or "").strip()
    raw_bullets = _fit_theme_bullets(
        raw_heading, [b.strip() for b in (card.get("bullets") or []) if b and b.strip()]
    )
    suffix = _theme_fit_suffix(raw_heading, raw_bullets)
    cls = f"theme {suffix}".strip()
    parts = [f"<!-- _class: {cls} -->", "", f"## {html.escape(raw_heading)}", ""]
    parts += [f"- {_wrap_timestamp(b)}" for b in raw_bullets]
    return "\n".join(parts)


def _badge(card: dict) -> str:
    """Render a sentiment chip from a card's ``sentiment`` text + ``sentiment_class``."""
    text = (card.get("sentiment") or "").strip()
    if not text:
        return ""
    cls = card.get("sentiment_class") or "sent-neutral"
    return f'<span class="badge {html.escape(cls)}">{html.escape(text)}</span>'


def _ticker_table_slide(card: dict) -> str:
    """Render a mentioned-ticker overview grid (one row per ticker)."""
    heading = html.escape((card.get("title") or "本期提及標的").strip())
    rows = []
    for r in card.get("rows") or []:
        name = html.escape((r.get("name") or "").strip())
        code = html.escape((r.get("code") or "").strip())
        risk = html.escape((r.get("risk") or "—").strip())
        badge = _badge(r)
        code_html = f'<span class="code">{code}</span>' if code else ""
        rows.append(
            '<div class="row">'
            f'<span class="name">{name}{code_html}</span>'
            f'{badge}'
            f'<span class="risk">風險 <b>{risk}</b></span>'
            "</div>"
        )
    return "\n".join([
        "<!-- _class: ticker-table -->", "", f"## {heading}", "",
        '<div class="rows">', *rows, "</div>",
    ])


def _analysis_slide(card: dict) -> str:
    """Render a single-focus analysis card: notched label + lead + body + source."""
    heading = html.escape((card.get("title") or "").strip())
    focus = html.escape((card.get("focus") or "").strip())
    lead = html.escape((card.get("lead") or "").strip())
    body = html.escape((card.get("body") or "").strip())
    source = html.escape((card.get("source") or "").strip())
    src_html = f'<span class="src">{source}</span>' if source else ""
    badge = _badge(card)
    return "\n".join([
        "<!-- _class: analysis -->", "",
        f"## {heading}" if heading else "##", "",
        '<div class="card">',
        f'<div class="fl-label">標的聚焦：{focus}</div>' if focus else "",
        f'<p class="lead">{lead}{src_html}</p>',
        f'<p class="body">{body}</p>',
        f'<div class="meta">{badge}</div>' if badge else "",
        "</div>",
    ])


def _focus_list_slide(card: dict) -> str:
    """Render an aggregated 產業焦點 card: several tickers (name + badge + one-liner)."""
    heading = html.escape((card.get("title") or "產業焦點").strip())
    items = []
    for it in card.get("items") or []:
        name = html.escape((it.get("name") or "").strip())
        code = html.escape((it.get("code") or "").strip())
        # The builder already fits the lead; re-fitting here is a no-op for fresh
        # cards and repairs decks stored before the fit existed.
        lead = html.escape(fit_focus_lead(it.get("lead") or ""))
        source = html.escape((it.get("source") or "").strip())
        name_html = f'{name} <span class="code">{code}</span>' if code else name
        badge = _badge(it)
        src_html = f'<span class="src">{source}</span>' if source else ""
        items.append(
            '<div class="fitem">'
            f'<div class="fhead"><span class="fname">{name_html}</span>{badge}{src_html}</div>'
            f'<p class="flead">{lead}</p>'
            "</div>"
        )
    return "\n".join([
        "<!-- _class: focus-list -->", "", f"## {heading}", "",
        '<div class="flist">', *items, "</div>",
    ])


_SLIDE_RENDERERS = {
    "ticker_table": _ticker_table_slide,
    "analysis": _analysis_slide,
    "focus_list": _focus_list_slide,
}


def _render_slide(card: dict, show_name: str, date_str: str) -> str:
    """Render one card to its slide markdown, dispatching on ``kind``."""
    kind = card.get("kind")
    if kind == "cover":
        return _cover_slide(card, show_name, date_str)
    renderer = _SLIDE_RENDERERS.get(kind)
    return renderer(card) if renderer else _theme_slide(card)


def build_card_deck_markdown(
    cards: list[dict[str, Any]],
    show_name: Optional[str] = None,
    date_str: Optional[str] = None,
) -> str:
    """Build branded Marp markdown — one slide per social card, cover first.

    Render with the theme CSS from ``card_theme_css()`` loaded via ``--theme-set``.
    """
    front = [
        "---", "marp: true", f"theme: {THEME_NAME}", "size: 1:1", "paginate: false",
        'header: ""', 'footer: ""', "---", "",
    ]
    slides = [_render_slide(c, show_name or "", date_str or "") for c in cards]
    return "\n".join(front) + "\n" + "\n\n---\n\n".join(slides) + "\n"


def _parse_size(size: str) -> tuple[int, int]:
    """Parse ``"1080x1080"`` / ``"1:1"`` into pixel (width, height)."""
    presets = {"1:1": (1080, 1080), "16:9": (1280, 720), "4:3": (960, 720)}
    if size in presets:
        return presets[size]
    if "x" in size:
        try:
            w, h = size.lower().split("x", 1)
            return int(w), int(h)
        except ValueError:
            pass
    return 1080, 1080


def build_inline_deck_markdown(
    cards: list[dict[str, Any]],
    show_name: Optional[str] = None,
    date_str: Optional[str] = None,
    content_type: str = "podcast",
    size: str = "1080x1080",
) -> str:
    """Browser-renderable variant of :func:`build_card_deck_markdown`.

    Identical cover/theme slides, but the theme CSS is emitted *inline* as a
    single ``<style>`` block (and a built-in Marp theme is named) so the
    frontend's in-browser ``@marp-team/marp-core`` can render it without the
    external ``--theme-set`` file that the PNG path uses. This keeps the on-page
    episode deck and the PNG social cards visually identical from one CSS source.

    NOTE: the frontend ``SlideViewer`` renders each slide in isolation, so it
    must hoist this ``<style>`` block onto every slide (it does). The block is
    emitted once here to keep the stored markdown small.
    """
    accent, soft = ACCENT_BY_KIND.get(content_type, ACCENT_YELLOW)
    width, height = _parse_size(size)
    css = card_theme_css(accent, soft)
    # The shared CSS hardcodes the 1080² PNG canvas; override for other sizes.
    if (width, height) != (1080, 1080):
        css += f"\nsection {{ width: {width}px; height: {height}px; }}"
    # Use the `tinboker-cards` theme + a size keyword it DECLARES, so marp-core
    # emits a matching SVG viewBox (square / 1240×780). With a built-in theme
    # like `uncover` the `size:` is ignored — it only declares 16:9/4:3 — so the
    # deck would render in a 16:9 viewBox and letterbox inside the square frame.
    # The frontend (marpParser.renderMarpToHTML) registers this theme's @size.
    size_token = {(1080, 1080): "1:1", (1240, 780): "wide"}.get((width, height), f"{width}x{height}")
    front = [
        "---", "marp: true", "theme: tinboker-cards", f"size: {size_token}",
        "paginate: false", 'header: ""', 'footer: ""', "---", "",
        f"<style>\n{css}\n</style>", "",
    ]
    slides = [_render_slide(c, show_name or "", date_str or "") for c in cards]
    return "\n".join(front) + "\n" + "\n\n---\n\n".join(slides) + "\n"
