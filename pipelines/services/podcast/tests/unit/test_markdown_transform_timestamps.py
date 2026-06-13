"""Summary chapter timestamps must be anchored to real cluster ms, not the LLM echo.

Regression coverage for the production bug where episode summary chapters either
collapsed to 00:00 (the writer echoed section ordinals 1/2/3/4 as ``#time``) or
disappeared entirely (the writer omitted ``start_time``), forcing the UI to fall
back to raw transcript sentences. The clusterer always knows the real millisecond
offset; ``transform_to_markdown`` must use that and ignore bogus echoed values.
"""

from __future__ import annotations

import re

from src.podcast.content_builder.nodes.markdown_transform import (
    _anchor_section_times,
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
    resolved = _anchor_section_times(
        [{"start_time": 305000}, {"start_time": 0}, {"start_time": 120000}],
        [0, 120000, 305000],
    )
    # First section legitimately maps to the 305000 cluster; order is then clamped
    # monotonic so later chapters never jump backwards.
    assert resolved[0] == 305000
    assert resolved == sorted(resolved)


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
    resolved = _anchor_section_times(
        [{}, {}, {}, {}],  # writer added an extra editorial section
        [0, 60000],
    )
    assert resolved == [0, 60000, 60000, 60000]
    assert resolved == sorted(resolved)
