"""Chapter consolidation must collapse fine events into length-scaled chapters.

Regression coverage for the img2 bug: a 20-minute episode produced 50+ summary
sections/chapters because the writer emitted one section per fine extractor event.
``consolidate_chapters`` merges the kept ``clustered_events`` into a handful of
reader-facing ``chapter_events`` whose count scales with the episode duration, and
the writer + ``markdown_transform`` consume that coarse list instead.
"""

from __future__ import annotations

from src.podcast.content_builder.nodes.chapter_consolidator import (
    _merge_group,
    _split_contiguous,
    _target_chapter_count,
    consolidate_chapters,
)

_MIN = 60_000  # one minute in ms


def _events(n: int, span_min: float) -> list[dict]:
    """n events evenly spaced across span_min minutes, each ~equal length."""
    span_ms = int(span_min * _MIN)
    step = span_ms // n
    return [
        {
            "section_topic": f"topic-{i}",
            "sentences": [{"text": f"s{i}", "start": i * step, "end": i * step + 10}],
            "start": i * step,
            "end": i * step + step,
        }
        for i in range(n)
    ]


def test_twenty_minute_episode_collapses_to_about_four_chapters():
    """The img2 case: ~50 fine events over 20 min -> ~4 chapters."""
    state = {"clustered_events": _events(50, span_min=20)}
    chapters = consolidate_chapters(state)["chapter_events"]
    assert len(chapters) == 4
    # Sentences are preserved (nothing dropped), just regrouped.
    assert sum(len(c["sentences"]) for c in chapters) == 50


def test_chapter_count_scales_with_duration():
    assert _target_chapter_count(span_ms=20 * _MIN, n_events=50) == 4
    assert _target_chapter_count(span_ms=53 * _MIN, n_events=50) == 11
    assert _target_chapter_count(span_ms=90 * _MIN, n_events=50) == 12  # capped
    assert _target_chapter_count(span_ms=8 * _MIN, n_events=50) == 4    # floored


def test_few_events_pass_through_unmerged():
    """Short episodes with already-few events are not force-split into 4."""
    events = _events(3, span_min=6)
    chapters = consolidate_chapters({"clustered_events": events})["chapter_events"]
    assert len(chapters) == 3
    assert [c["start"] for c in chapters] == [e["start"] for e in events]


def test_merged_chapter_anchors_to_first_subevent_start():
    """Each chapter's start must be its first sub-event's real offset (for #time)."""
    events = _events(12, span_min=30)
    chapters = consolidate_chapters({"clustered_events": events})["chapter_events"]
    # Chapters chronological; first chapter starts at the episode start.
    assert chapters[0]["start"] == events[0]["start"]
    starts = [c["start"] for c in chapters]
    assert starts == sorted(starts)
    # Topics are joined so the writer has the full hint.
    assert "、" in chapters[0]["section_topic"] or len(events) <= len(chapters)


def test_split_contiguous_partitions_completely():
    ranges = _split_contiguous(50, 4)
    assert ranges[0] == (0, 13) and ranges[-1][1] == 50
    # Contiguous, no gaps or overlaps.
    for (a_start, a_end), (b_start, _b_end) in zip(ranges, ranges[1:]):
        assert a_end == b_start
    sizes = [e - s for s, e in ranges]
    assert max(sizes) - min(sizes) <= 1  # near-equal


def test_empty_events_yield_empty_chapters():
    assert consolidate_chapters({"clustered_events": []})["chapter_events"] == []
    assert consolidate_chapters({})["chapter_events"] == []


def test_chapters_get_sequential_event_ids():
    """A2: every chapter is stamped E1, E2, ... regardless of merge/pass-through."""
    chapters = consolidate_chapters({"clustered_events": _events(3, span_min=6)})["chapter_events"]
    assert [c["event_id"] for c in chapters] == ["E1", "E2", "E3"]

    merged = consolidate_chapters({"clustered_events": _events(50, span_min=20)})["chapter_events"]
    assert [c["event_id"] for c in merged] == ["E1", "E2", "E3", "E4"]


def _typed_events(types: list[str], span_min: float = 20) -> list[dict]:
    events = _events(len(types), span_min=span_min)
    for e, t in zip(events, types):
        e["segment_type"] = t
    return events


def test_merge_group_picks_dominant_segment_type():
    """A5(i): the majority segment_type in a merged group survives, not be dropped."""
    group = [
        {"section_topic": "a", "sentences": [], "start": 0, "end": 10, "segment_type": "qa"},
        {"section_topic": "b", "sentences": [], "start": 10, "end": 20, "segment_type": "qa"},
        {"section_topic": "c", "sentences": [], "start": 20, "end": 30, "segment_type": "analysis"},
    ]
    assert _merge_group(group)["segment_type"] == "qa"


def test_consolidate_chapters_never_drops_segment_type():
    """End-to-end: every produced chapter carries a real segment_type."""
    events = _typed_events(["analysis"] * 8 + ["qa"] * 4, span_min=20)
    chapters = consolidate_chapters({"clustered_events": events})["chapter_events"]
    assert all(c.get("segment_type") for c in chapters)
    assert chapters[-1]["segment_type"] == "qa"


def test_trailing_qa_run_never_merges_with_preceding_chapter():
    """A5(ii): the trailing qa run never merges into the preceding non-qa chapter,
    even though the plain count-based split would otherwise blend them."""
    events = _typed_events(["analysis"] * 9 + ["qa"] * 3, span_min=6)
    chapters = consolidate_chapters({"clustered_events": events})["chapter_events"]
    head_topics = {f"topic-{i}" for i in range(9)}
    tail_topics = {f"topic-{i}" for i in range(9, 12)}
    for c in chapters:
        topics = set(c["section_topic"].split("、"))
        # No chapter straddles the boundary — head and tail topics never co-occur.
        assert not (topics & head_topics and topics & tail_topics)
    assert chapters[-1]["segment_type"] == "qa"


def test_interleaved_qa_does_not_explode_chapter_count():
    """A5(ii) guard: alternating qa/non-qa (not a trailing run) stays on the normal
    count-based split — must NOT get a hard boundary at every transition, or a
    qa-heavy show could blow past _MAX_CHAPTERS."""
    types = ["analysis", "qa"] * 20  # 40 alternating events, ends on qa
    events = _typed_events(types, span_min=90)  # long span -> would hit the cap
    chapters = consolidate_chapters({"clustered_events": events})["chapter_events"]
    assert len(chapters) <= 12  # _MAX_CHAPTERS
    assert len(chapters) >= 4   # _MIN_CHAPTERS


def test_all_qa_episode_has_no_boundary_split_artifact():
    """When EVERY event is qa, there's no preceding non-qa chapter to separate from
    — must behave like the normal (non-boundary) path, not produce an empty head."""
    events = _typed_events(["qa"] * 8, span_min=20)
    chapters = consolidate_chapters({"clustered_events": events})["chapter_events"]
    assert len(chapters) == 4
    assert all(c["segment_type"] == "qa" for c in chapters)
