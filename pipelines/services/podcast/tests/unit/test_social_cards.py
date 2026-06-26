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


def test_cover_duplicate_memo_slide_is_dropped():
    # The marp_writer sometimes echoes the cover as a "PODCAST MEMO" slide carrying a
    # hallucinated show name (e.g. 股癌); it must never become a theme card.
    state = _state(
        {"title": "T", "slides": [
            {"heading": "PODCAST MEMO", "bullet_points": ["PODCAST MEMO", "股癌", "2026.06.26"], "start_time": 0},
            {"heading": "真主題", "bullet_points": ["重點"], "start_time": 1000},
        ]},
        ["洞見"],
    )
    cards = sc.build_social_cards(state)["social_cards"]
    assert [c["kind"] for c in cards] == ["cover", "theme"]
    assert cards[1]["title"] == "真主題"
    assert all("股癌" not in b for c in cards for b in c.get("bullets", []))


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


def test_theme_cards_capped():
    slides = [{"heading": f"主題{i}", "bullet_points": [f"點{i}"], "start_time": i * 1000}
              for i in range(40)]
    cards = sc.build_social_cards(_state({"title": "T", "slides": slides}, ["洞見"]))["social_cards"]
    themes = [c for c in cards if c["kind"] == "theme"]
    assert len(themes) == sc.MAX_THEME_CARDS == 4   # bulk capped to keep the deck tight


def test_empty_when_no_insights_and_no_themes():
    cards = sc.build_social_cards(_state({"title": "T", "slides": []}, []))["social_cards"]
    assert cards == []


def test_missing_timestamp_leaves_bullets_unstamped():
    cards = sc.build_social_cards(
        _state({"title": "T", "slides": [{"heading": "H", "bullet_points": ["a", "b"]}]}, ["i"])
    )["social_cards"]
    assert cards[1]["bullets"] == ["a", "b"]
    assert cards[1]["start_time_ms"] is None


# --- unified carousel: cover → ticker_table → themes → focus_list ----------

def test_build_social_cards_merges_ticker_deck():
    state = {
        "episode_title": "EP", "key_insights": ["洞見"],
        "marp_slides": {"title": "T", "slides": [
            {"heading": "主題A", "bullet_points": ["a"], "start_time": 1000},
            {"heading": "主題B", "bullet_points": ["b"], "start_time": 2000},
        ]},
        "ticker_insights": {"ticker_insights": [
            {"ticker": "2330", "sentiment_score": 0.85, "risks": [{"severity": "HIGH"}],
             "reasons": [{"title": "AI 需求", "description": "拉貨。", "start_time": 5000}]},
        ]},
    }
    kinds = [c["kind"] for c in sc.build_social_cards(state)["social_cards"]]
    # cover first, ticker overview next, then episode themes, aggregated focus last.
    assert kinds == ["cover", "ticker_table", "theme", "theme", "focus_list"]


def test_build_social_cards_without_tickers_is_cover_plus_themes():
    state = {"episode_title": "EP", "key_insights": ["洞見"],
             "marp_slides": {"title": "T", "slides": [
                 {"heading": "H", "bullet_points": ["a"], "start_time": 1000}]}}
    kinds = [c["kind"] for c in sc.build_social_cards(state)["social_cards"]]
    assert kinds == ["cover", "theme"]   # unchanged when no ticker_insights


# --- cards_from_ticker_insights (deterministic ticker deck) ----------------

def _insight(ticker, score, *, reasons=None, risks=None):
    return {"ticker": ticker, "sentiment_score": score,
            "reasons": reasons or [], "risks": risks or []}


def test_sentiment_enum_maps_to_exact_badge_and_zh():
    # score → 5-tier label → (zh chip, css class). Both bull tiers → 看多, etc.
    cases = [(0.95, "看多", "sent-bull"), (0.70, "看多", "sent-bull"),
             (0.50, "觀望", "sent-neutral"),
             (0.30, "看空", "sent-bear"), (0.05, "看空", "sent-bear")]
    for score, zh, cls in cases:
        text, klass = sc._sentiment_badge(score)
        assert (text, klass) == (zh, cls), f"{score} → {text}/{klass}"


def test_risk_factor_takes_worst_severity():
    assert sc._risk_factor([{"severity": "LOW"}, {"severity": "HIGH"}]) == "高"
    assert sc._risk_factor([{"severity": "medium"}]) == "中"
    assert sc._risk_factor([]) == "—"


def test_focus_list_item_pulls_from_top_reason():
    cards = sc.cards_from_ticker_insights({"ticker_insights": [
        _insight("NVDA", 0.8, reasons=[
            {"title": "板電升級", "description": "用量幾何成長。", "start_time": 60000}]),
    ]})
    fl = next(c for c in cards if c["kind"] == "focus_list")
    it = fl["items"][0]
    assert it["lead"] == "用量幾何成長。"          # description leads, title is fallback
    assert it["source"] == "[01:00]"
    assert (it["sentiment"], it["sentiment_class"]) == ("看多", "sent-bull")


def test_focus_list_batches_three_per_card_capped():
    insights = [_insight(f"T{i}", 0.9, reasons=[{"description": f"理由{i}", "start_time": 0}])
                for i in range(8)]
    cards = sc.cards_from_ticker_insights({"ticker_insights": insights})
    focus = [c for c in cards if c["kind"] == "focus_list"]
    assert len(focus) == sc.MAX_FOCUS_CARDS == 2                   # 8 tickers → 2 slides
    assert all(len(c["items"]) <= sc.FOCUS_PER_CARD == 3 for c in focus)


def test_ticker_table_paginates_and_caps_with_warning(caplog):
    import logging
    insights = [_insight(str(2300 + i), 0.7) for i in range(18)]   # >10 tickers
    with caplog.at_level(logging.WARNING):
        cards = sc.cards_from_ticker_insights({"ticker_insights": insights})
    tables = [c for c in cards if c["kind"] == "ticker_table"]
    assert len(tables) == sc.MAX_TABLE_CARDS == 1                  # single overview table
    assert sum(len(t["rows"]) for t in tables) == sc.ROWS_PER_TABLE == 8
    assert "dropping 10" in caplog.text                           # 18 - 8, not silent


def test_ticker_insights_empty_returns_no_cards():
    assert sc.cards_from_ticker_insights({}) == []
    assert sc.cards_from_ticker_insights(None) == []


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
