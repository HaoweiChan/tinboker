"""Markdown transform node: converts structured writer output to markdown.

Section heading timestamps (``#time:ms``) are anchored DETERMINISTICALLY to the
real millisecond offsets the clusterer computed from the transcript — never to
the value the writer LLM echoes back. The model reliably preserves section
ORDER, but it is unreliable at transcribing 6-digit millisecond numbers: it has
historically emitted section ordinals (``#time:1``, ``#time:2`` …) or omitted the
field entirely, which surfaced on the site as chapters stuck at 00:00 or summary
chapters silently falling back to raw transcript sentences. Code owns the
timestamp; the LLM owns the prose. ``build_events_markdown`` already anchors the
same way — this keeps the summary path consistent with it.
"""

from typing import Any, Optional

from ..state import PipelineState


def _anchor_section_times(
    sections: list[dict[str, Any]],
    cluster_starts: list[int],
) -> list[Optional[int]]:
    """Resolve a real start-ms for each writer section.

    The writer emits one section per clustered (already financial-filtered) event,
    in the order it received them, so the base mapping is positional:
    ``sections[i] -> cluster_starts[i]``. Two refinements harden it against the LLM
    merging or adding sections:

    - If the writer echoed a ``start_time`` that EXACTLY matches a known cluster
      start, trust it (covers the writer reordering sections).
    - Positional assignment is clamped to the available range and forced
      monotonic non-decreasing, so chapters never jump backwards.

    Returns ``None`` for a section when no real offset exists (e.g. the clusterer
    produced no timed events) so the caller omits the marker instead of emitting a
    bogus 00:00.
    """
    if not sections:
        return []

    valid = sorted({int(s) for s in cluster_starts if isinstance(s, (int, float))})
    if not valid:
        return [None] * len(sections)
    valid_set = set(valid)

    resolved: list[Optional[int]] = []
    last = -1
    for i, section in enumerate(sections):
        echoed = section.get("start_time")
        # Trust an echoed value only if it is a real cluster start — this rejects
        # the ordinal/placeholder values the model sometimes invents (1, 2, 3, …).
        if isinstance(echoed, (int, float)) and int(echoed) in valid_set:
            ms = int(echoed)
        else:
            ms = valid[i] if i < len(valid) else valid[-1]
        # Keep chapters monotonic; downstream de-dupes identical timestamps.
        if ms < last:
            ms = last
        last = ms
        resolved.append(ms)
    return resolved


def transform_to_markdown(state: PipelineState) -> dict[str, Any]:
    """Transform structured writer output into a markdown string."""
    writer_output = state.get("writer_output", {})
    if not writer_output:
        return {"markdown_report": ""}

    sections = writer_output.get("sections", []) or []
    # Anchor against the SAME list the writer turned into sections: the
    # consolidated ``chapter_events`` when present, else the fine
    # ``clustered_events`` (regen/legacy). The writer emits one section per event
    # in order, so this stays positionally aligned.
    anchor_events = state.get("chapter_events") or state.get("clustered_events", [])
    cluster_starts = [
        e.get("start")
        for e in anchor_events
        if e.get("start") is not None
    ]
    section_times = _anchor_section_times(sections, cluster_starts)

    parts = []

    if writer_output.get("title"):
        parts.append(f"# {writer_output['title']}\n")

    if writer_output.get("executive_summary"):
        parts.append(f"{writer_output['executive_summary']}\n")

    for section, start_ms in zip(sections, section_times):
        heading = section.get("heading", "").lstrip("# ").strip()

        if heading:
            if start_ms is not None:
                parts.append(f"## {heading} (#time:{start_ms})\n")
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
