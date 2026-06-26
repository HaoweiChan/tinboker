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
section.ticker-table .grp {{
  flex: 0 0 132px; font-size: 26px; font-weight: 700; color: {MUTED};
  letter-spacing: 1px;
}}
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
section.focus-list .fitem {{ padding: 26px 0; border-bottom: 1px solid {BORDER}; }}
section.focus-list .fitem:first-child {{ border-top: 1px solid {BORDER}; }}
section.focus-list .fhead {{ display: flex; align-items: center; gap: 18px; margin-bottom: 14px; }}
section.focus-list .fname {{ font-size: 38px; font-weight: 800; color: {TEXT}; }}
section.focus-list .fhead .src {{
  margin-left: auto; font-size: 24px; font-weight: 700; color: {MUTED};
  background: {SURFACE}; padding: 4px 14px; border-radius: 6px; white-space: nowrap;
}}
section.focus-list .flead {{
  font-size: 33px; line-height: 1.5; font-weight: 500; color: {SOFT}; margin: 0;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
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


def _cover_slide(card: dict, show_name: str, date_str: str) -> str:
    # Show name wins: the LLM marp deck title hallucinates famous brands (e.g. 股癌)
    # for unrelated shows, so the cover must use the deterministic podcast name.
    title = html.escape((show_name or card.get("title") or "").strip())
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
        grp = html.escape((r.get("group") or "").strip())
        name = html.escape((r.get("name") or "").strip())
        code = html.escape((r.get("code") or "").strip())
        risk = html.escape((r.get("risk") or "—").strip())
        badge = _badge(r)
        code_html = f'<span class="code">{code}</span>' if code else ""
        rows.append(
            '<div class="row">'
            f'<span class="grp">{grp}</span>'
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
        lead = html.escape((it.get("lead") or "").strip())
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
