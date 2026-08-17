"""The Threads copy the graph writes must survive the trip to the episode document.

Regression: ``write_social_copy`` ran on every ingest and its ``social_thread`` was
dropped three times over — the graph→dict bridge, the summarize result, and
``create_episode_object`` all mapped ``social_cards`` and not ``social_thread``. Every
episode therefore reached Postgres with ``social_thread`` null, and the publisher fell
back to the mechanical 【title】+ bullets compose instead of the written copy.
"""

from __future__ import annotations

from types import SimpleNamespace

from src.models.podcast_models import PodcastEpisode

_THREAD = {"post": "第一行\n\n第二行", "comments": [{"heading": "段落", "text": "重點"}]}


def test_the_graph_bridge_maps_social_thread(monkeypatch):
    import src.summarize.content_builder as cb

    monkeypatch.setenv("OPENROUTER_API_KEY", "dummy")
    monkeypatch.setattr(
        "src.podcast.content_builder.run_pipeline",
        lambda **kw: {"markdown_report": "# 標題\n\n內文", "social_thread": _THREAD},
    )

    out = cb.analyze_transcript_with_workflow_api(
        transcript="t", sentences=[], source="Gooaye 股癌", episode_title="EP688"
    )
    assert out["social_thread"] == _THREAD


def test_an_empty_thread_becomes_none_so_hand_edited_copy_survives(monkeypatch):
    """postgres_episode treats social_thread as platform-owned: a stored value is kept
    unless this run produced a non-empty one. Empty must therefore arrive as None."""
    import src.summarize.content_builder as cb

    monkeypatch.setenv("OPENROUTER_API_KEY", "dummy")
    monkeypatch.setattr(
        "src.podcast.content_builder.run_pipeline",
        lambda **kw: {"markdown_report": "# 標題\n\n內文", "social_thread": {}},
    )

    out = cb.analyze_transcript_with_workflow_api(
        transcript="t", sentences=[], source="s", episode_title="e"
    )
    assert out["social_thread"] is None


def test_create_episode_object_carries_it():
    from src.pipeline.utils import create_episode_object

    episode = create_episode_object(
        episode_data=SimpleNamespace(
            api_data={}, tickers=[], podcast_name="Gooaye 股癌", created_time=None
        ),
        gcs_urls={},
        spotify_metadata=None,
        summary_result={"summary_text": "x", "social_thread": _THREAD},
    )
    assert episode.social_thread == _THREAD


def _episode(**kw) -> PodcastEpisode:
    return PodcastEpisode(
        mp3_url="", transcript_url="", summary_url="", summary_image_url="", **kw
    )


def test_to_dict_emits_it_only_when_this_run_wrote_one():
    assert "social_thread" not in _episode(social_thread=None).to_firestore_dict()
    assert "social_thread" not in _episode(social_thread={}).to_firestore_dict()
    assert _episode(social_thread=_THREAD).to_firestore_dict()["social_thread"] == _THREAD


def test_from_firestore_dict_round_trips():
    restored = PodcastEpisode.from_firestore_dict({"social_thread": _THREAD})
    assert restored.social_thread == _THREAD
    assert PodcastEpisode.from_firestore_dict({}).social_thread is None
