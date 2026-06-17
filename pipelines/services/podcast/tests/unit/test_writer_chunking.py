"""Unit tests for the writer's long-episode chunking.

The writer emits one section per clustered event, so its JSON article grows with
the episode and, past the threshold, overflows a single LLM call (the reply
truncates mid-string and the episode falls back to a placeholder summary). For
long episodes ``write_article`` writes in event-position chunks and merges the
sections, preserving the global event order so ``markdown_transform`` can still
anchor chapter timestamps positionally.
"""

from __future__ import annotations

from unittest.mock import patch

from src.podcast.content_builder.nodes import writer


def _events(n: int) -> list[dict]:
    return [{"section_topic": f"t{i}", "start": i * 1000, "end": i * 1000 + 900} for i in range(n)]


def _output(tag: str, n_sections: int, start: int = 0) -> dict:
    return {
        "title": f"title-{tag}",
        "executive_summary": f"summary-{tag}",
        "sections": [{"heading": f"h{start + i}", "content": f"c{start + i}"} for i in range(n_sections)],
        "conclusion": f"conclusion-{tag}",
        "stock_tickers": [{"display_name": tag, "symbol": tag}],
        "tags": [{"display_name": tag, "tag_name": tag}],
    }


def test_short_episode_uses_single_call_unchanged():
    state = {"clustered_events": _events(5), "source": "X", "episode_title": "E"}
    reply = _output("solo", 5)
    with patch.object(writer, "invoke_json", return_value=reply) as mock:
        out = writer.write_article(state)
    assert mock.call_count == 1
    assert out["writer_output"] is reply  # single-call path returns the reply as-is


def test_long_episode_chunks_and_merges_sections_in_order():
    # 24 events, CHUNK_SIZE 12 -> 2 chunks (12 + 12 events).
    state = {"clustered_events": _events(24), "source": "X", "episode_title": "E"}
    chunk1 = _output("a", 12, start=0)
    chunk2 = _output("b", 12, start=12)
    with patch.object(writer, "invoke_json", side_effect=[chunk1, chunk2]) as mock:
        out = writer.write_article(state)

    assert mock.call_count == 2
    merged = out["writer_output"]
    # Sections concatenated in chunk order -> matches the full event order.
    headings = [s["heading"] for s in merged["sections"]]
    assert headings == [f"h{i}" for i in range(24)]
    # title/executive_summary from the first chunk; conclusion from the last.
    assert merged["title"] == "title-a"
    assert merged["executive_summary"] == "summary-a"
    assert merged["conclusion"] == "conclusion-b"
    # tickers/tags unioned across chunks.
    assert {t["symbol"] for t in merged["stock_tickers"]} == {"a", "b"}
    assert {t["tag_name"] for t in merged["tags"]} == {"a", "b"}


def test_long_episode_passes_only_its_slice_to_each_chunk():
    # Each chunk's build_messages must see only its slice of clustered_events, so
    # each LLM reply stays small (the whole point of chunking).
    state = {"clustered_events": _events(25), "source": "X", "episode_title": "E"}
    seen_sizes: list[int] = []
    real_build = writer.build_messages

    def _spy_build(sub_state):
        seen_sizes.append(len(sub_state.get("clustered_events", [])))
        return real_build(sub_state)

    with patch.object(writer, "invoke_json", return_value=_output("x", 0)), \
         patch.object(writer, "build_messages", side_effect=_spy_build):
        writer.write_article(state)

    assert seen_sizes == [12, 12, 1]  # 25 events, CHUNK_SIZE 12 -> 12 + 12 + 1


def test_merge_tolerates_non_dict_and_missing_fields():
    # A chunk that returned a non-dict (degenerate reply) is skipped, not fatal.
    merged = writer._merge_writer_outputs([
        None,
        {"sections": [{"heading": "only"}]},
    ])
    assert [s["heading"] for s in merged["sections"]] == ["only"]
    assert merged["title"] == ""
