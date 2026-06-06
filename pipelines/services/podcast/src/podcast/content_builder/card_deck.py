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
from typing import Any, Optional

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
  padding: 84px 88px 104px; margin: 0;
  letter-spacing: .2px;
}}
section::after {{
  content: "{_BRAND}";
  position: absolute; right: 64px; bottom: 56px;
  font-size: 24px; font-weight: 600; color: {MUTED}; letter-spacing: 1px;
}}
/* ---- Cover ---- */
section.cover {{ justify-content: center; }}
section.cover .label {{
  font-size: 30px; font-weight: 800; letter-spacing: 8px;
  color: {accent}; text-transform: uppercase; margin-bottom: 28px;
}}
section.cover h1 {{ font-size: 132px; font-weight: 900; line-height: 1.04; margin: 0 0 18px; color: {TEXT}; }}
section.cover .date {{ font-size: 34px; color: {MUTED}; margin-bottom: 36px; }}
section.cover .rule {{ width: 132px; height: 10px; background: {accent}; border-radius: 6px; margin-bottom: 40px; }}
section.cover .hook {{ font-size: 40px; line-height: 1.6; font-weight: 500; color: {SOFT}; }}
/* ---- Theme card ---- */
section.theme h2 {{
  font-size: 52px; font-weight: 800; line-height: 1.3; margin: 0 0 44px; color: {TEXT};
  padding: 20px 28px 20px 26px;
  border-left: 12px solid {accent};
  background: linear-gradient(90deg, {accent_soft}, rgba(0,0,0,0));
}}
section.theme ul {{ list-style: none; padding: 0; margin: 0; }}
section.theme li {{
  position: relative; padding-left: 40px; margin-bottom: 34px;
  font-size: 37px; line-height: 1.62; font-weight: 500; color: {SOFT};
}}
section.theme li::before {{ content: "▍"; position: absolute; left: 0; top: 2px; color: {accent}; font-size: 34px; }}
section.theme .ts {{ color: {accent}; font-weight: 700; font-size: .82em; white-space: nowrap; }}
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


def _cover_slide(card: dict, show_name: str, date_str: str) -> str:
    title = html.escape((card.get("title") or show_name or "").strip())
    bullets = [b for b in (card.get("bullets") or []) if b and b.strip()]
    hook = html.escape("，".join(b.strip().rstrip("。") for b in bullets[:3]))
    if hook:
        hook += "。"
    lines = ["<!-- _class: cover -->", "", '<div class="label">Podcast Memo</div>', "", f"# {title}", ""]
    if date_str:
        lines.append(f'<div class="date">{html.escape(date_str)}</div>')
    lines.append('<div class="rule"></div>')
    if hook:
        lines.append(f'<div class="hook">{hook}</div>')
    return "\n".join(lines)


def _theme_slide(card: dict) -> str:
    heading = html.escape((card.get("title") or "").strip())
    bullets = [b for b in (card.get("bullets") or []) if b and b.strip()]
    parts = ["<!-- _class: theme -->", "", f"## {heading}", ""]
    parts += [f"- {_wrap_timestamp(b)}" for b in bullets]
    return "\n".join(parts)


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
    slides = [
        _cover_slide(c, show_name or "", date_str or "") if c.get("kind") == "cover"
        else _theme_slide(c)
        for c in cards
    ]
    return "\n".join(front) + "\n" + "\n\n---\n\n".join(slides) + "\n"
