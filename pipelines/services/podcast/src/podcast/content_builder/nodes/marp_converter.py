"""Marp converter node: transforms structured slide data into Marp markdown."""

from typing import Any

from ..state import PipelineState


def convert_marp(state: PipelineState) -> dict[str, Any]:
    """Convert structured marp_slides output to Marp markdown string."""
    marp_output = state.get("marp_slides", {})
    return {"marp_markdown": _build_marp_markdown(marp_output, size="1080x1080")}


def convert_marp_ticker(state: PipelineState) -> dict[str, Any]:
    """Convert ticker marp slides to Marp markdown string."""
    marp_output = state.get("ticker_marp_slides", {})
    return {"ticker_marp_markdown": _build_marp_markdown(marp_output, size="1240x780")}


def _build_marp_markdown(marp_output: dict, size: str = "1080x1080") -> str:
    """Build Marp markdown string from structured slide data."""
    parts = [
        "---",
        "marp: true",
        "theme: default",
        "paginate: true",
        f"size: {size}",
        'header: ""',
        'footer: ""',
        "---",
        "",
        "<style>",
        "section {",
        "  padding-bottom: 3rem !important;",
        "}",
        "ul, ol {",
        "  margin-bottom: 1.5rem !important;",
        "}",
        "p:last-child, li:last-child {",
        "  margin-bottom: 2rem !important;",
        "}",
        "</style>",
        "",
    ]

    if marp_output and "title" in marp_output:
        title = marp_output["title"]
        parts.append(f"# {title}")
        parts.append("")
        parts.append("---")
        parts.append("")

    if marp_output and "slides" in marp_output:
        for slide in marp_output.get("slides", []):
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
                    parts.append(f"- {point}")
                parts.append("")
                if slide.get("slide_notes"):
                    parts.append(f"<!-- Notes: {slide['slide_notes']} -->")
                    parts.append("")

            parts.append("---")
            parts.append("")

    return "\n".join(parts)
