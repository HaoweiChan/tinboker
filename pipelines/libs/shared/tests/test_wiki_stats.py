"""Tests for the content-derived aggregates in shared.wiki_builder.stats."""

from datetime import date

import pytest
from shared.wiki_builder import InMemoryWikiRepository, ingest_episode, stats


def _rec(ticker: str, sentiment: str) -> dict:
    return {
        "ticker": ticker,
        "sentiment": sentiment,
        "sentiment_score": 7,
        "time_horizon": "中期",
        "bluf_thesis": f"thesis for {ticker}",
    }


@pytest.fixture()
def repo() -> InMemoryWikiRepository:
    r = InMemoryWikiRepository()
    # latest day (2026-05-12): 2 episodes
    ingest_episode(
        podcast_name="股癌", episode_number=1, title="E1", date="2026-05-12",
        tickers=["2330.TW", "NVDA"], tags=["半導體", "AI 基建"], summary_text="s",
        ticker_insights={
            "ticker_insights": [_rec("2330.TW", "bullish"), _rec("NVDA", "bull")]
        },
        repository=r,
    )
    ingest_episode(
        podcast_name="財報狗", episode_number=2, title="E2", date="2026-05-12",
        tickers=["NVDA", "AMD"], tags=["半導體"], summary_text="s",
        ticker_insights={
            "ticker_insights": [_rec("NVDA", "bullish"), _rec("AMD", "bearish")]
        },
        repository=r,
    )
    # 2026-05-10 (in a 7-day window from 05-12)
    ingest_episode(
        podcast_name="股癌", episode_number=3, title="E3", date="2026-05-10",
        tickers=["2330.TW"], tags=["半導體"], summary_text="s",
        ticker_insights={"ticker_insights": [_rec("2330.TW", "neutral")]},
        repository=r,
    )
    # 2026-05-03 / 05-02 — outside the current 7-day window, inside the previous one
    ingest_episode(
        podcast_name="股癌", episode_number=4, title="E4", date="2026-05-03",
        tickers=["2330.TW"], tags=["台股"], summary_text="s",
        ticker_insights={"ticker_insights": [_rec("2330.TW", "bull")]},
        repository=r,
    )
    ingest_episode(
        podcast_name="M觀點", episode_number=5, title="E5", date="2026-05-02",
        tickers=["TSLA"], tags=["電動車"], summary_text="s",
        ticker_insights={"ticker_insights": [_rec("TSLA", "bearish")]},
        repository=r,
    )
    return r


def test_top_tickers(repo):
    rows = stats.top_tickers(repo, days=7, limit=10)
    by_sym = {r["sym"]: r for r in rows}
    assert set(by_sym) == {"2330", "NVDA", "AMD"}  # TSLA is outside the 7-day window
    tsmc, nvda, amd = by_sym["2330"], by_sym["NVDA"], by_sym["AMD"]
    assert tsmc["mentions"] == 2 and tsmc["name"] == "台積電" and tsmc["market"] == "TW"
    assert tsmc["dist"] == {"bull": 1, "bear": 0, "neut": 1}
    assert nvda["mentions"] == 2 and nvda["dist"] == {"bull": 2, "bear": 0, "neut": 0}
    assert amd["mentions"] == 1 and amd["dist"] == {"bull": 0, "bear": 1, "neut": 0}
    # limit is honored, ranking is by mention count
    assert [r["sym"] for r in stats.top_tickers(repo, days=7, limit=1)] == [rows[0]["sym"]]


def test_top_shows(repo):
    rows = stats.top_shows(repo, days=7, limit=10)
    by_show = {r["podcast"]: r for r in rows}
    assert by_show["股癌"]["episodes"] == 2 and by_show["財報狗"]["episodes"] == 1
    # 股癌 had 1 episode in the previous 7-day window (E4) -> +100%
    assert by_show["股癌"]["prev_episodes"] == 1 and by_show["股癌"]["delta_pct"] == 100
    assert by_show["財報狗"]["prev_episodes"] == 0 and by_show["財報狗"]["delta_pct"] is None


def test_topics(repo):
    rows = stats.topics(repo)  # all-time
    by_tag = {r["tag"]: r for r in rows}
    assert by_tag["半導體"]["count"] == 3 and by_tag["半導體"]["weight"] == 1.0
    assert by_tag["AI 基建"]["count"] == 1 and by_tag["AI 基建"]["weight"] == round(1 / 3, 3)
    assert by_tag["電動車"]["sentiment"] == "bear"  # only E5, TSLA bearish
    assert all(r["sentiment"] in ("bull", "bear", "neut") for r in rows)
    # name comes from the topic page (== the tag if untranslated)
    assert by_tag["台股"]["name"] == "台股"


def test_pulse(repo):
    p = stats.pulse(repo)  # latest day = 2026-05-12
    assert p["date"] == "2026-05-12"
    assert p["episode_count"] == 2
    assert p["ticker_count"] == 3  # 2330, NVDA, AMD
    assert p["sentiment"] == {"bull": 3, "bear": 1, "neut": 0, "dominant": "bull"}
    # an explicit older date
    assert stats.pulse(repo, on_date=date(2026, 5, 2))["episode_count"] == 1


def test_entity_aggregate(repo):
    agg = stats.entity_aggregate(repo, "2330")
    assert agg["name"] == "台積電" and agg["market"] == "TW"
    assert agg["total_mentions"] == 3  # E1, E3, E4
    assert agg["mentions"] == 3  # days=None -> all
    assert agg["last_mentioned_at"] == "2026-05-12"
    assert agg["dist"] == {"bull": 2, "bear": 0, "neut": 1}
    assert [e["slug"] for e in agg["recent_episodes"]][:1] == ["股癌_ep1"]
    # windowed
    assert stats.entity_aggregate(repo, "2330", days=7)["mentions"] == 2  # E1, E3
    assert stats.entity_aggregate(repo, "nonexistent") is None
