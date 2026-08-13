"""Generated cover image for syndicated copies.

The show's own artwork cannot be the thumbnail: a summary carrying the podcast's logo
reads as the podcast's own post, which is passing off someone else's brand. And the
episode's ``summary_image`` is a generated placeholder ("Placeholder Chart") on every
episode checked. So the cover is drawn here — our own template, naming the show as the
subject rather than wearing it as identity.

SVG rather than a raster: no image library, no bundled CJK font, and vocus renders it —
verified against a live draft. If a platform ever needs a raster, this is the place to
add one, not the call sites.
"""
from __future__ import annotations

import functools
import logging
import re
import shutil
import subprocess
from xml.sax.saxutils import escape

logger = logging.getLogger(__name__)

WIDTH, HEIGHT = 1200, 600

# Two lines at 56px is the comfortable maximum for the title block. CJK glyphs are
# full-width, so a character count is a good enough width estimate; Latin runs narrower
# and simply leaves the line short.
TITLE_CHARS_PER_LINE = 14
TITLE_MAX_LINES = 3

# The frontend's dark "終端機 Terminal" tokens, resolved to hex — near-black canvas,
# amber primary, electric-cyan accent (frontend/src/index.css). Hard-coded because an
# image generator cannot read CSS variables; if the theme moves, these move with it.
BG_FROM = "#07090e"     # --background
BG_TO = "#0c1017"       # --card
INK = "#e0e6eb"         # --foreground
AMBER = "#fbac23"       # --primary
MUTED = "#8a97a8"       # --muted-foreground
BORDER = "#1c2531"      # --border

# cairosvg does NO font fallback: it renders with one family and turns every glyph that
# family lacks into a tofu box. A CSS stack like "system-ui, ..., sans-serif" therefore
# produces a cover with Latin text and □□□ where the Chinese should be — confirmed by
# rendering it. So the family is resolved at runtime to one that actually has the glyphs.
_FALLBACK_FAMILY = "Noto Sans CJK TC"      # what fonts-noto-cjk installs in the container
_FALLBACK_EMOJI = "Noto Color Emoji"       # what fonts-noto-color-emoji installs

# Episode titles really do carry emoji ("EP684 | 🔦"), and no CJK face has those glyphs.
# Since there is no fallback, emoji runs are emitted in their own tspan naming an emoji
# family — cairo then renders them in full colour. Covers the common pictographic blocks
# plus the joiners, so a ZWJ sequence stays one run instead of fragmenting.
_EMOJI = re.compile(
    "([\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF"
    "\U00002B00-\U00002BFF\U0000FE0F\U0000200D\U0001F900-\U0001F9FF]+)"
)


@functools.lru_cache(maxsize=1)
def emoji_font_family() -> str:
    """A font family on this machine that has colour emoji glyphs."""
    if shutil.which("fc-match"):
        try:
            out = subprocess.run(["fc-match", "-f", "%{family[0]}", "emoji"],
                                 capture_output=True, text=True, timeout=5, check=True).stdout.strip()
            if out:
                return out
        except (subprocess.SubprocessError, OSError) as e:
            logger.info("og: emoji fc-match failed (%s); using %s", e, _FALLBACK_EMOJI)
    return _FALLBACK_EMOJI


def _runs(text: str, emoji_family: str) -> str:
    """Text as SVG, with emoji stretches switched to a font that can draw them."""
    out = []
    for part in _EMOJI.split(text):
        if not part:
            continue
        if _EMOJI.fullmatch(part):
            out.append(f'<tspan font-family="{emoji_family}">{escape(part)}</tspan>')
        else:
            out.append(escape(part))
    return "".join(out)


@functools.lru_cache(maxsize=1)
def cjk_font_family() -> str:
    """A font family present on this machine that covers Traditional Chinese.

    Asked of fontconfig rather than hard-coded, so the same code renders on a developer's
    Mac (Heiti TC) and in the Debian image (Noto Sans CJK TC). Browsers viewing the SVG
    fall back to their own default when the name is unknown to them, which is fine —
    only the server-side raster is picky.
    """
    if shutil.which("fc-match"):
        try:
            out = subprocess.run(["fc-match", "-f", "%{family[0]}", "sans-serif:lang=zh-tw"],
                                 capture_output=True, text=True, timeout=5, check=True).stdout.strip()
            if out:
                return out
        except (subprocess.SubprocessError, OSError) as e:
            logger.info("og: fc-match failed (%s); using %s", e, _FALLBACK_FAMILY)
    return _FALLBACK_FAMILY


# Artwork square on the right; the title column stops short of it.
ART_SIZE = 260
ART_X = WIDTH - ART_SIZE - 80
ART_Y = (HEIGHT - ART_SIZE) // 2


def _wrap(text: str, per_line: int, max_lines: int) -> list[str]:
    """Greedy character wrap, ellipsised if it would overflow."""
    text = " ".join((text or "").split())
    lines: list[str] = []
    while text and len(lines) < max_lines:
        if len(text) <= per_line:
            lines.append(text)
            text = ""
            break
        cut = per_line
        # Prefer breaking at a space when one is nearby, so Latin titles do not split
        # mid-word; CJK has no spaces and falls through to the hard cut.
        space = text.rfind(" ", 0, per_line + 1)
        if space > per_line // 2:
            cut = space
        lines.append(text[:cut].strip())
        text = text[cut:].strip()
    if text and lines:
        lines[-1] = lines[-1][: per_line - 1].rstrip() + "…"
    return lines or [""]


def episode_cover_svg(title: str, kicker: str = "", footer: str = "tinboker.com",
                      cover_data_uri: str = "") -> str:
    """A 2:1 cover: small kicker, wrapped title, footer domain, show artwork on the right.

    ``cover_data_uri`` must be a ``data:`` URI, not an http URL — an external reference
    inside an SVG is at the mercy of the renderer's CSP and of whether it rasterises
    server-side, and a silently missing image is worse than no image at all.
    """
    font = escape(cjk_font_family(), {'"': "&quot;"})
    emoji = escape(emoji_font_family(), {'"': "&quot;"})
    lines = _wrap(title, TITLE_CHARS_PER_LINE, TITLE_MAX_LINES)
    line_height = 76
    block_top = HEIGHT / 2 - (len(lines) - 1) * line_height / 2 - 8

    title_tspans = "".join(
        f'<tspan x="80" y="{block_top + i * line_height:.0f}">{_runs(line, emoji)}</tspan>'
        for i, line in enumerate(lines)
    )

    # The show's artwork as an illustration inside our layout — the same way a review
    # shows the cover of the thing reviewed. It is deliberately NOT the whole image:
    # a summary wearing only the podcast's logo reads as the podcast's own post.
    art = ""
    if cover_data_uri:
        art = (f'<clipPath id="artclip"><rect x="{ART_X}" y="{ART_Y}" width="{ART_SIZE}" '
               f'height="{ART_SIZE}" rx="28"/></clipPath>'
               f'<image href="{escape(cover_data_uri)}" x="{ART_X}" y="{ART_Y}" '
               f'width="{ART_SIZE}" height="{ART_SIZE}" preserveAspectRatio="xMidYMid slice" '
               f'clip-path="url(#artclip)"/>'
               f'<rect x="{ART_X}" y="{ART_Y}" width="{ART_SIZE}" height="{ART_SIZE}" rx="28" '
               f'fill="none" stroke="{AMBER}" stroke-opacity="0.4" stroke-width="2"/>')

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" \
viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-label="{escape(title)}">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="{BG_FROM}"/>
      <stop offset="100%" stop-color="{BG_TO}"/>
    </linearGradient>
  </defs>
  <rect width="{WIDTH}" height="{HEIGHT}" fill="url(#bg)"/>
  <rect width="{WIDTH}" height="6" fill="{AMBER}"/>
  {art}
  <text x="80" y="120" font-family="{font}" font-size="26" fill="{AMBER}" letter-spacing="2">{_runs(kicker, emoji)}</text>
  <text font-family="{font}" font-size="56" font-weight="700" fill="{INK}">{title_tspans}</text>
  <text x="80" y="{HEIGHT - 60}" font-family="{font}" font-size="24" fill="{MUTED}">{escape(footer)}</text>
</svg>"""


def episode_cover_png(svg: str) -> bytes:
    """Rasterise a cover for platforms whose share cards cannot use SVG.

    og:image is not honoured as SVG by the social crawlers, so a card built from the SVG
    URL comes out blank. cairosvg is imported here rather than at module scope: the SVG
    path must keep working (and its tests must keep running) on machines without libcairo.
    """
    import cairosvg  # noqa: PLC0415 — optional at import time, see docstring

    return cairosvg.svg2png(bytestring=svg.encode("utf-8"),
                            output_width=WIDTH, output_height=HEIGHT)
