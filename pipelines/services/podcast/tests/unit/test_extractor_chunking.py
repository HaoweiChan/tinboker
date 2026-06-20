"""Unit tests for the extractor's long-episode chunking.

Long transcripts overflow a single extractor LLM call (the JSON reply truncates
and the episode falls back to a placeholder summary). ``extract_events`` chunks
such transcripts by sentence position and merges the events, offsetting each
chunk's 0-based local ranges back to global positions so the clusterer (which
indexes the full sentence list positionally) still resolves them.
"""

from __future__ import annotations

from unittest.mock import patch

from src.podcast.content_builder.nodes import extractor


def _sentences(n: int) -> list[dict]:
    return [{"index": i, "content": f"s{i}", "start": i * 1000, "end": i * 1000 + 900} for i in range(n)]


def test_short_transcript_uses_single_call_unchanged():
    state = {"sentences": _sentences(100), "source": "X", "episode_title": "E"}
    reply = {"events": [{"start_index": 0, "end_index": 99, "segment_type": "analysis", "section_topic": "t"}]}
    with patch.object(extractor, "invoke_json", return_value=reply) as mock:
        out = extractor.extract_events(state)
    assert mock.call_count == 1
    assert len(out["events"]) == 1
    assert out["events"][0]["start_index"] == 0
    assert out["events"][0]["end_index"] == 99


def test_long_transcript_chunks_and_offsets_to_global_indices():
    # 2000 sentences, CHUNK_SIZE 800 -> 3 chunks at offsets 0, 800, 1600.
    state = {"sentences": _sentences(2000), "source": "X", "episode_title": "E"}
    per_chunk = {"events": [{"start_index": 0, "end_index": 5, "segment_type": "analysis", "section_topic": "t"}]}
    with patch.object(extractor, "invoke_json", return_value=per_chunk) as mock:
        out = extractor.extract_events(state)

    assert mock.call_count == 3
    starts = [e["start_index"] for e in out["events"]]
    ends = [e["end_index"] for e in out["events"]]
    assert starts == [0, 800, 1600]      # offset back to global positions
    assert ends == [5, 805, 1605]
    # All events still normalized (segment_type/is_substantive present).
    assert all("is_substantive" in e for e in out["events"])


def test_long_transcript_reindexes_each_chunk_to_local_zero_based():
    # The sentences handed to build_messages for each chunk must be re-indexed to
    # 0-based local positions, matching the prompt's "0-based index" contract.
    state = {"sentences": _sentences(1700), "source": "X", "episode_title": "E"}
    seen_first_indices: list[int] = []

    def _capture(role, messages):
        # Recover the chunk size from the rendered user message is overkill; instead
        # assert via the sub_state path by spying on build_messages below.
        return {"events": []}

    real_build = extractor.build_messages

    def _spy_build(sub_state):
        sents = sub_state.get("sentences", [])
        seen_first_indices.append(sents[0]["index"] if sents else -1)
        return real_build(sub_state)

    with patch.object(extractor, "invoke_json", side_effect=_capture), \
         patch.object(extractor, "build_messages", side_effect=_spy_build):
        extractor.extract_events(state)

    # 1700 sentences -> chunks at 0, 800, 1600; each chunk's local index starts at 0.
    assert seen_first_indices == [0, 0, 0]
