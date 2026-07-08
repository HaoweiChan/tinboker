"""Summary chapter timestamps must be anchored to real cluster ms, not the LLM echo.

Regression coverage for the production bug where episode summary chapters either
collapsed to 00:00 (the writer echoed section ordinals 1/2/3/4 as ``#time``) or
disappeared entirely (the writer omitted ``start_time``), forcing the UI to fall
back to raw transcript sentences. The clusterer always knows the real millisecond
offset; ``transform_to_markdown`` must use that and ignore bogus echoed values.

Also covers A2 (EP677 fix plan): sections carry an ``event_id`` (E1, E2, ...) the
writer echoes back, which anchoring keys off FIRST — the real fix for the case
where the writer drops or merges a section and positional mapping would shift
every later chapter.
"""

from __future__ import annotations

import re

from src.podcast.content_builder.nodes.markdown_transform import (
    _anchor_sections,
    transform_to_markdown,
)


def _times(markdown: str) -> list[int]:
    return [int(m) for m in re.findall(r"#time:(\d+)", markdown)]


def test_ordinal_echoes_are_replaced_with_real_cluster_ms():
    """The img2 bug: writer wrote #time:1..4; output must carry the real offsets."""
    state = {
        "clustered_events": [
            {"start": 0}, {"start": 120000}, {"start": 305000}, {"start": 540000},
        ],
        "writer_output": {
            "title": "T",
            "sections": [
                {"heading": "A", "start_time": 1, "content": "a"},
                {"heading": "B", "start_time": 2, "content": "b"},
                {"heading": "C", "start_time": 3, "content": "c"},
                {"heading": "D", "start_time": 4, "content": "d"},
            ],
        },
    }
    md = transform_to_markdown(state)["markdown_report"]
    assert _times(md) == [0, 120000, 305000, 540000]


def test_missing_echoes_are_filled_positionally():
    """The img1 bug: writer omitted start_time; chapters must still be anchored."""
    state = {
        "clustered_events": [{"start": 5000}, {"start": 88000}, {"start": 210000}],
        "writer_output": {
            "sections": [
                {"heading": "A", "content": "a"},
                {"heading": "B", "content": "b"},
                {"heading": "C", "content": "c"},
            ],
        },
    }
    assert _times(transform_to_markdown(state)["markdown_report"]) == [5000, 88000, 210000]


def test_valid_echo_is_trusted_even_when_out_of_array_order():
    """A correct ms echo that matches a known cluster start is honoured."""
    resolved = _anchor_sections(
        [{"start_time": 305000}, {"start_time": 0}, {"start_time": 120000}],
        [{"start": 0}, {"start": 120000}, {"start": 305000}],
    )
    starts = [r["start_ms"] for r in resolved]
    # First section legitimately maps to the 305000 cluster; order is then clamped
    # monotonic so later chapters never jump backwards.
    assert starts[0] == 305000
    assert starts == sorted(starts)


def test_no_cluster_times_emits_no_markers():
    """Without timed clusters we omit markers rather than fabricate 00:00 chapters."""
    state = {
        "clustered_events": [],
        "writer_output": {"sections": [{"heading": "A", "content": "a", "start_time": 2}]},
    }
    md = transform_to_markdown(state)["markdown_report"]
    assert "#time:" not in md
    assert "## A" in md


def test_more_sections_than_clusters_stay_monotonic():
    resolved = _anchor_sections(
        [{}, {}, {}, {}],  # writer added an extra editorial section
        [{"start": 0}, {"start": 60000}],
    )
    starts = [r["start_ms"] for r in resolved]
    assert starts == [0, 60000, 60000, 60000]
    assert starts == sorted(starts)


def test_event_id_anchors_correctly_when_a_section_is_dropped():
    """A2's real target: the writer drops event E3 of 4; ids keep the rest correct.

    Positional mapping would shift E4's section onto E3's timestamp; id-matching
    keeps every remaining section on its real event regardless of the gap.
    """
    events = [
        {"event_id": "E1", "start": 0},
        {"event_id": "E2", "start": 60000},
        {"event_id": "E3", "start": 120000},
        {"event_id": "E4", "start": 300000},
    ]
    # Writer dropped E3 entirely — only 3 sections for 4 events.
    sections = [
        {"heading": "A", "event_id": "E1", "content": "a"},
        {"heading": "B", "event_id": "E2", "content": "b"},
        {"heading": "D", "event_id": "E4", "content": "d"},
    ]
    resolved = _anchor_sections(sections, events)
    assert [r["start_ms"] for r in resolved] == [0, 60000, 300000]


def test_qa_segment_type_flows_through_to_anchor():
    """Anchoring surfaces the matched event's segment_type for the Q&A heading (A5)."""
    events = [{"event_id": "E1", "start": 0, "segment_type": "analysis"},
              {"event_id": "E2", "start": 60000, "segment_type": "qa"}]
    sections = [{"event_id": "E1"}, {"event_id": "E2"}]
    resolved = _anchor_sections(sections, events)
    assert [r["segment_type"] for r in resolved] == ["analysis", "qa"]


def test_qa_chapters_get_a_deterministic_heading_prefix():
    """The heading prefix is code-side (keyed off the real segment_type), never
    left for the LLM to author — see A5."""
    state = {
        "chapter_events": [
            {"event_id": "E1", "start": 0, "segment_type": "analysis"},
            {"event_id": "E2", "start": 60000, "segment_type": "qa"},
        ],
        "writer_output": {
            "sections": [
                {"heading": "台積電展望", "event_id": "E1", "content": "..."},
                {"heading": "記憶體報價提問", "event_id": "E2", "content": "..."},
            ],
        },
    }
    md = transform_to_markdown(state)["markdown_report"]
    assert "## 台積電展望 (#time:0)" in md
    assert "## Q&A：記憶體報價提問 (#time:60000)" in md
