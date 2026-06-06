"""Markdown transform node: converts structured writer output to markdown."""

from typing import Any

from ..state import PipelineState


def transform_to_markdown(state: PipelineState) -> dict[str, Any]:
    """Transform structured writer output into a markdown string."""
    writer_output = state.get("writer_output", {})
    if not writer_output:
        return {"markdown_report": ""}

    parts = []

    if writer_output.get("title"):
        parts.append(f"# {writer_output['title']}\n")

    if writer_output.get("executive_summary"):
        parts.append(f"{writer_output['executive_summary']}\n")

    for section in writer_output.get("sections", []):
        heading = section.get("heading", "").lstrip("# ").strip()
        start_time = section.get("start_time")

        if heading:
            if start_time is not None:
                parts.append(f"## {heading} (#time:{start_time})\n")
            else:
                parts.append(f"## {heading}\n")

        content = section.get("content", "")
        if content:
            if content.strip().startswith(f"## {heading}"):
                lines = content.split("\n", 1)
                if len(lines) > 1:
                    parts.append(f"{lines[1]}\n")
            else:
                parts.append(f"{content}\n")

        for subsection in section.get("subsections", []):
            if subsection.get("heading"):
                parts.append(f"### {subsection['heading']}\n")
            if subsection.get("content"):
                parts.append(f"{subsection['content']}\n")

    if writer_output.get("conclusion"):
        parts.append(f"## 結論\n\n{writer_output['conclusion']}\n")

    return {"markdown_report": "\n".join(parts)}
