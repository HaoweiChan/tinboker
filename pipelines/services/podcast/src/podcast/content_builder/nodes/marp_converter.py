"""Marp converter node: transforms structured slide data into Marp markdown."""

from typing import Any

from ..state import PipelineState

# Dark theme CSS matching the TinBoker slide reference style.
# Two accent variants: YELLOW (#F5A623) for episode slides, BLUE (#4A90D9) for
# ticker slides. Both share the same dark background and typography.
_THEME_CSS_TEMPLATE = """
section {{
  background: #0e1014;
  color: #D1D5DB;
  font-family: "Noto Sans TC", "SF Pro Display", -apple-system, sans-serif;
  padding: 60px 64px 48px 64px !important;
  line-height: 1.6;
}}
h1 {{
  color: #FFFFFF;
  font-size: 2.6em;
  font-weight: 800;
  line-height: 1.2;
  margin-bottom: 0.3em;
}}
h2 {{
  color: #FFFFFF;
  font-size: 1.7em;
  font-weight: 700;
  line-height: 1.25;
  border-left: 5px solid {accent};
  padding-left: 16px;
  margin-bottom: 0.8em;
}}
h3 {{
  color: {accent};
  font-size: 0.85em;
  font-weight: 700;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  margin-bottom: 0.3em;
}}
p {{
  font-size: 1.05em;
  color: #D1D5DB;
  margin-bottom: 0.6em;
}}
blockquote {{
  border-left: 4px solid {accent};
  padding: 12px 0 12px 20px;
  margin: 16px 0;
  background: transparent;
  font-size: 1.0em;
  color: #E5E7EB;
  line-height: 1.65;
}}
blockquote p {{
  margin: 0;
  color: #E5E7EB;
}}
ul, ol {{
  margin-bottom: 1.2em;
}}
li {{
  color: #D1D5DB;
  margin-bottom: 0.5em;
}}
hr {{
  border: none;
  border-top: 3px solid {accent};
  width: 60px;
  margin: 16px 0 24px 0;
}}
a {{
  color: {accent};
  text-decoration: none;
}}
section.cover h1 {{
  font-size: 3.2em;
  margin-bottom: 0.15em;
}}
section.cover p {{
  font-size: 1.05em;
  color: #9CA3AF;
}}
"""

_ACCENT_YELLOW = "#F5A623"
_ACCENT_BLUE = "#4A90D9"


def convert_marp(state: PipelineState) -> dict[str, Any]:
    """Convert structured marp_slides output to Marp markdown string."""
    marp_output = state.get("marp_slides", {})
    return {"marp_markdown": _build_marp_markdown(marp_output, size="1080x1080", accent=_ACCENT_YELLOW)}


def convert_marp_ticker(state: PipelineState) -> dict[str, Any]:
    """Convert ticker marp slides to Marp markdown string."""
    marp_output = state.get("ticker_marp_slides", {})
    return {"ticker_marp_markdown": _build_marp_markdown(marp_output, size="1240x780", accent=_ACCENT_BLUE)}


def _build_marp_markdown(marp_output: dict, size: str = "1080x1080", accent: str = _ACCENT_YELLOW) -> str:
    """Build Marp markdown string from structured slide data."""
    css = _THEME_CSS_TEMPLATE.format(accent=accent)
    parts = [
        "---",
        "marp: true",
        "theme: uncover",
        f"size: {size}",
        'header: ""',
        'footer: ""',
        "---",
        "",
        f"<style>{css}</style>",
        "",
    ]

    if marp_output and "slides" in marp_output:
        for i, slide in enumerate(marp_output.get("slides", [])):
            if slide.get("content"):
                parts.append(slide["content"])
                parts.append("")
                if slide.get("start_time") is not None:
                    parts.append(f"<!-- #time:{slide['start_time']} -->")
                    parts.append("")
                if slide.get("slide_notes"):
                    parts.append(f"<!-- Notes: {slide['slide_notes']} -->")
                    parts.append("")
            else:
                if slide.get("heading"):
                    parts.append(f"## {slide['heading']}")
                    parts.append("")
                if slide.get("start_time") is not None:
                    parts.append(f"<!-- #time:{slide['start_time']} -->")
                    parts.append("")
                for point in slide.get("bullet_points", []):
                    parts.append(f"> {point}")
                    parts.append("")
                if slide.get("slide_notes"):
                    parts.append(f"<!-- Notes: {slide['slide_notes']} -->")
                    parts.append("")

            parts.append("---")
            parts.append("")

    elif marp_output and "title" in marp_output:
        parts.append(f"# {marp_output['title']}")
        parts.append("")
        parts.append("---")
        parts.append("")

    return "\n".join(parts)
