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

from xml.sax.saxutils import escape

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
    lines = _wrap(title, TITLE_CHARS_PER_LINE, TITLE_MAX_LINES)
    line_height = 76
    block_top = HEIGHT / 2 - (len(lines) - 1) * line_height / 2 - 8

    title_tspans = "".join(
        f'<tspan x="80" y="{block_top + i * line_height:.0f}">{escape(line)}</tspan>'
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
  <text x="80" y="120" font-family="system-ui,-apple-system,'PingFang TC','Noto Sans TC',sans-serif" \
font-size="26" fill="{AMBER}" letter-spacing="2">{escape(kicker)}</text>
  <text font-family="system-ui,-apple-system,'PingFang TC','Noto Sans TC',sans-serif" \
font-size="56" font-weight="700" fill="{INK}">{title_tspans}</text>
  <text x="80" y="{HEIGHT - 60}" font-family="system-ui,-apple-system,'PingFang TC','Noto Sans TC',sans-serif" \
font-size="24" fill="{MUTED}">{escape(footer)}</text>
</svg>"""
