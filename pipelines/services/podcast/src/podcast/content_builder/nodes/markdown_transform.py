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

Matching a writer section back to its source event is tried in this order:
1. ``event_id`` (E1, E2, ...) echoed by the writer — a short ordinal id the model
   copies far more reliably than a 6-digit ms value (see A2 in the EP677 fix plan).
2. An echoed ``start_time`` that exactly matches a known event start ms
   (pre-event_id back-compat).
3. Position — clamped to the available range. Any section that falls back to
   position is exactly the failure mode that let a dropped/merged section shift
   every later chapter, so it is logged.
"""

import logging
from typing import Any, Optional

from ..state import PipelineState

logger = logging.getLogger(__name__)


def _anchor_sections(
    sections: list[dict[str, Any]],
    anchor_events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Resolve a real start-ms + segment_type for each writer section.

    Returns one ``{"start_ms": Optional[int], "segment_type": Optional[str]}`` dict
    per section, monotonic non-decreasing on ``start_ms`` so chapters never jump
    backwards. ``start_ms`` is ``None`` when no timed events exist at all (the
    caller omits the marker instead of fabricating 00:00).
    """
    if not sections:
        return []
    if not anchor_events:
        return [{"start_ms": None, "segment_type": None} for _ in sections]

    id_index = {e["event_id"]: i for i, e in enumerate(anchor_events) if e.get("event_id")}
    ms_index: dict[int, int] = {}
    for i, e in enumerate(anchor_events):
        start = e.get("start")
        if isinstance(start, (int, float)) and int(start) not in ms_index:
            ms_index[int(start)] = i

    resolved: list[dict[str, Any]] = []
    last = -1
    positional_fallbacks = 0
    for i, section in enumerate(sections):
        idx: Optional[int] = None
        event_id = section.get("event_id")
        if isinstance(event_id, str) and event_id in id_index:
            idx = id_index[event_id]
        else:
            echoed = section.get("start_time")
            if isinstance(echoed, (int, float)) and int(echoed) in ms_index:
                idx = ms_index[int(echoed)]
            else:
                positional_fallbacks += 1
                idx = min(i, len(anchor_events) - 1)

        event = anchor_events[idx]
        ms = event.get("start")
        if isinstance(ms, (int, float)):
            ms = int(ms)
            if ms < last:
                ms = last
            last = ms
        else:
            ms = None
        resolved.append({"start_ms": ms, "segment_type": event.get("segment_type")})

    if positional_fallbacks:
        logger.warning(
            "markdown_transform: %d/%d sections had no matching event_id/start_time "
            "echo and fell back to positional anchoring; chapter timestamps may be "
            "unreliable if the writer dropped, merged, or reordered sections.",
            positional_fallbacks,
            len(sections),
        )
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
    # in order, so this stays positionally aligned when id/ms echoes are absent.
    anchor_events = state.get("chapter_events") or state.get("clustered_events", [])
    anchors = _anchor_sections(sections, anchor_events)

    parts = []

    if writer_output.get("title"):
        parts.append(f"# {writer_output['title']}\n")

    if writer_output.get("executive_summary"):
        parts.append(f"{writer_output['executive_summary']}\n")

    for section, anchor in zip(sections, anchors):
        heading = section.get("heading", "").lstrip("# ").strip()
        # Deterministic Q&A marker: code-side, keyed off the matched event's real
        # segment_type — never left to the LLM to author (see A5).
        if heading and anchor.get("segment_type") == "qa" and not heading.startswith("Q&A"):
            heading = f"Q&A：{heading}"

        start_ms = anchor.get("start_ms")
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
