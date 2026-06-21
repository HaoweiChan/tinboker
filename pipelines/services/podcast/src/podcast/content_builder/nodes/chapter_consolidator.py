"""Chapter consolidation node: merge fine-grained events into reader-facing chapters.

The extractor deliberately produces GRANULAR topic events — one per Q&A question,
"err on the side of more granular topics" (see ``prompts/extractor.yaml``) — because
that granularity is what lets the clusterer's policy router drop ads/intro/outro/
chitchat accurately. The cost is that one summary section per fine event yields 50+
headings on a 20-minute episode, which is unreadable and defeats the point of an
editorial summary.

This node sits between the clusterer and the writer. It merges the KEPT
``clustered_events`` into a small set of ``chapter_events`` whose count scales with
the episode duration (~1 chapter per 5 minutes, floored at 4 and capped at 12), then
the writer emits one section per chapter and ``markdown_transform`` anchors each
chapter's ``#time`` to its first sub-event's real offset.

Only the summary path consumes ``chapter_events`` — ticker extraction, sector
exposures and the Marp slides keep reading the fine ``clustered_events`` so their
precision is unchanged. The merge preserves every kept sentence (concatenated in
order), so nothing the writer needs is lost; it just sees coarser topic units.
"""

from typing import Any

from ..state import PipelineState

# Pacing knobs for the length-scaled target. ~1 chapter per 5 minutes of audio,
# never fewer than 4 (so even short episodes read as a few distinct chapters) and
# never more than 12 (an hour-plus episode stays skimmable). A 20-min episode ->
# 4 chapters; ~53 min -> ~11; >=60 min -> 12.
_MS_PER_CHAPTER = 5 * 60 * 1000
_MIN_CHAPTERS = 4
_MAX_CHAPTERS = 12


def _target_chapter_count(span_ms: int, n_events: int) -> int:
    """Resolve how many chapters this episode should have.

    Never more than the number of source events (we merge, never split), and never
    below the event count when that is already small — forcing 4 chapters out of 2
    events would mean inventing empty ones.
    """
    if n_events <= _MIN_CHAPTERS:
        return n_events
    by_time = round(span_ms / _MS_PER_CHAPTER) if span_ms > 0 else _MIN_CHAPTERS
    target = max(_MIN_CHAPTERS, min(_MAX_CHAPTERS, by_time))
    return min(target, n_events)


def _split_contiguous(n: int, target: int) -> list[tuple[int, int]]:
    """Split ``n`` ordered items into ``target`` contiguous near-equal groups.

    Returns ``[(start, end), ...]`` half-open index ranges. The first ``n % target``
    groups get one extra item, so group sizes differ by at most one and order is
    preserved (chapters stay chronological, which the positional timestamp anchoring
    in ``markdown_transform`` relies on).
    """
    base, extra = divmod(n, target)
    ranges: list[tuple[int, int]] = []
    i = 0
    for k in range(target):
        size = base + (1 if k < extra else 0)
        ranges.append((i, i + size))
        i += size
    return ranges


def _merge_group(group: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge a contiguous run of events into a single chapter event.

    ``start`` is the first sub-event's start (the real offset the chapter anchors
    to), ``end`` the last sub-event's end. Sentences are concatenated in order so the
    writer has the full material; topics are joined distinct-and-ordered into a hint
    the writer rewrites into one editorial headline.
    """
    topics = list(
        dict.fromkeys(
            t for g in group if (t := (g.get("section_topic") or "").strip())
        )
    )
    sentences: list[dict[str, Any]] = []
    for g in group:
        sentences.extend(g.get("sentences", []) or [])
    return {
        "section_topic": "、".join(topics),
        "sentences": sentences,
        "start": group[0].get("start"),
        "end": group[-1].get("end"),
    }


def consolidate_chapters(state: PipelineState) -> dict[str, Any]:
    """Merge ``clustered_events`` into length-scaled ``chapter_events``.

    A no-op pass-through (events copied as-is) when there are already few enough
    events, so short episodes and the empty case keep working unchanged.
    """
    events = list(state.get("clustered_events", []) or [])
    if not events:
        return {"chapter_events": []}

    # Order chronologically so the count-split yields chronological chapters; other
    # consumers still read the original ``clustered_events`` ordering untouched.
    events.sort(key=lambda e: e.get("start") if e.get("start") is not None else 0)

    starts = [e.get("start") for e in events if e.get("start") is not None]
    ends = [e.get("end") for e in events if e.get("end") is not None]
    span_ms = (max(ends) - min(starts)) if starts and ends else 0

    target = _target_chapter_count(span_ms, len(events))
    if target >= len(events):
        return {"chapter_events": events}

    chapters = [_merge_group(events[s:e]) for s, e in _split_contiguous(len(events), target)]
    return {"chapter_events": chapters}
