"""Chapter consolidation must collapse fine events into length-scaled chapters.

Regression coverage for the img2 bug: a 20-minute episode produced 50+ summary
sections/chapters because the writer emitted one section per fine extractor event.
``consolidate_chapters`` merges the kept ``clustered_events`` into a handful of
reader-facing ``chapter_events`` whose count scales with the episode duration, and
the writer + ``markdown_transform`` consume that coarse list instead.
"""

from __future__ import annotations

from src.podcast.content_builder.nodes.chapter_consolidator import (
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
