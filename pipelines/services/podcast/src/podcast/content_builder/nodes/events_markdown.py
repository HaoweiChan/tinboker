"""Events-to-markdown node: builds a simple event list with timestamps."""

from typing import Any

from ..state import PipelineState


def build_events_markdown(state: PipelineState) -> dict[str, Any]:
    """Build a markdown list of extracted events with timestamps."""
    events = state.get("events", [])
    sentences_list = state.get("sentences", [])

    if not events:
        return {"events_markdown": "# Events List\n\nNo events found."}

    parts = ["# Events List", ""]

    for event in events:
        start_index = event.get("start_index", 0)
        end_index = event.get("end_index", 0)
        section_topic = event.get("section_topic", "Untitled Event")

        start_time = None
        if start_index < len(sentences_list):
            sentence = sentences_list[start_index]
            if "start" in sentence:
                start_time = sentence.get("start")

        if start_time is not None:
            parts.append(f"## {section_topic} (#time:{start_time})")
        else:
            parts.append(f"## {section_topic}")
        parts.append(f"  - Indices: {start_index}-{end_index}")
        parts.append("")

    return {"events_markdown": "\n".join(parts)}
