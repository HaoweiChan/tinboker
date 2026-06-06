"""Unit tests for the social_cards builder + its Firestore field + graph wiring.

Covers timestamp formatting, the cover+theme card assembly (one card per bulleted
slide, last bullet stamped with its [MM:SS]), the skip/cap/empty edge cases, the
merge-safe PodcastEpisode write, and that the LangGraph still compiles with the new
join node.
"""

from __future__ import annotations

from datetime import datetime

from src.models.podcast_models import PodcastEpisode
from src.podcast.content_builder.nodes import social_cards_builder as sc

# --- format_timestamp -------------------------------------------------------

def test_format_timestamp_minutes_seconds():
    assert sc.format_timestamp(67000) == "[01:07]"
    assert sc.format_timestamp(0) == "[00:00]"


def test_format_timestamp_hours():
    assert sc.format_timestamp(3661000) == "[01:01:01]"


def test_format_timestamp_unknown():
    assert sc.format_timestamp(None) == ""
    assert sc.format_timestamp(-5) == ""


# --- build_social_cards -----------------------------------------------------

def _state(marp_slides, key_insights):
    return {"marp_slides": marp_slides, "key_insights": key_insights, "episode_title": "EP"}


def test_cover_then_theme_cards_with_timestamp_on_last_bullet():
    state = _state(
        {"title": "本集重點", "slides": [
            {"heading": "台積電法說會", "bullet_points": ["營收創高", "AI 需求強"], "start_time": 67000},
            {"heading": "NVIDIA 合作", "bullet_points": ["RTX Spark 優化"], "start_time": 772000},
        ]},
        ["台積電優於預期", "AI 續強"],
    )
    cards = sc.build_social_cards(state)["social_cards"]

    assert cards[0] == {"kind": "cover", "title": "本集重點",
                        "bullets": ["台積電優於預期", "AI 續強"], "start_time_ms": None, "image_url": None}
    assert cards[1]["kind"] == "theme"
    assert cards[1]["title"] == "台積電法說會"
    assert cards[1]["bullets"] == ["營收創高", "AI 需求強 [01:07]"]   # stamp on last bullet only
    assert cards[1]["start_time_ms"] == 67000
    assert cards[2]["bullets"] == ["RTX Spark 優化 [12:52]"]
    assert all(c["image_url"] is None for c in cards)               # filled later by upload step


def test_bulletless_slide_is_skipped():
    # A Marp title slide (no bullets) must not become a card — it would desync indices.
    state = _state(
        {"title": "T", "slides": [
            {"heading": "封面", "bullet_points": []},
            {"heading": "真主題", "bullet_points": ["重點"], "start_time": 1000},
        ]},
        ["洞見"],
    )
    cards = sc.build_social_cards(state)["social_cards"]
    assert [c["kind"] for c in cards] == ["cover", "theme"]
    assert cards[1]["title"] == "真主題"


def test_caps_at_twenty_cards():
    slides = [{"heading": f"主題{i}", "bullet_points": [f"點{i}"], "start_time": i * 1000}
              for i in range(40)]
    cards = sc.build_social_cards(_state({"title": "T", "slides": slides}, ["洞見"]))["social_cards"]
    assert len(cards) == sc.MAX_CARDS == 20


def test_empty_when_no_insights_and_no_themes():
    cards = sc.build_social_cards(_state({"title": "T", "slides": []}, []))["social_cards"]
    assert cards == []


def test_missing_timestamp_leaves_bullets_unstamped():
    cards = sc.build_social_cards(
        _state({"title": "T", "slides": [{"heading": "H", "bullet_points": ["a", "b"]}]}, ["i"])
    )["social_cards"]
    assert cards[1]["bullets"] == ["a", "b"]
    assert cards[1]["start_time_ms"] is None


# --- persistence + graph wiring --------------------------------------------

def _episode(**kw) -> PodcastEpisode:
    base = dict(
        mp3_url="gs://b/a.mp3", transcript_url="", summary_url="gs://b/s.md",
        summary_image_url="", created_time=datetime(2026, 6, 1),
        episode_title="T", podcast_name="股癌",
    )
    base.update(kw)
    return PodcastEpisode(**base)


def test_episode_write_is_merge_safe():
    cards = [{"kind": "cover", "title": "x", "bullets": ["a"], "start_time_ms": None, "image_url": None}]
    assert _episode(social_cards=cards).to_firestore_dict()["social_cards"] == cards
    # Empty cards never written (won't clobber an existing value on merge update).
    assert "social_cards" not in _episode().to_firestore_dict()


def test_graph_compiles_with_join_node():
    from src.podcast.content_builder.graph import build_graph
    build_graph()  # raises if the fan-in edges / node are misconfigured
