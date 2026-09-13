"""Weekly rollup (TKB-013): week arithmetic and the aggregation over scoped episodes."""
from datetime import datetime, timezone

import pytest

from src.models.podcast import Episode
from src.routers import weekly


def _ms(iso: str) -> int:
    return int(datetime.fromisoformat(iso).replace(tzinfo=timezone.utc).timestamp() * 1000)


def _ep(ep_id: str, released: str, tickers: list[str], podcast: str = "股癌", sectors=None) -> Episode:
    return Episode(
        id=ep_id, podcast_name=podcast, episode_title=f"{ep_id} 標題", created_time=_ms(released),
        released_at_ms=_ms(released), related_tickers=tickers, key_insights=["一", "二", "三", "四"],
        sector_exposures=sectors or [],
    )


def test_week_bounds_and_week_of_ms_use_taipei_calendar():
    assert weekly.week_bounds("2026-W36") == (datetime(2026, 8, 31).date(), datetime(2026, 9, 6).date())
    # 2026-09-06 23:00 UTC is already Monday 07:00 in Taipei → next ISO week.
    assert weekly.week_of_ms(_ms("2026-09-06T23:00:00")) == "2026-W37"
    assert weekly.week_of_ms(_ms("2026-09-06T12:00:00")) == "2026-W36"
    with pytest.raises(ValueError):
        weekly.week_bounds("2026-36")


@pytest.mark.asyncio
async def test_build_week_aggregates_tickers_sectors_and_sentiment_shift(monkeypatch):
    eps = [
        _ep("E1", "2026-09-01T02:00:00", ["2330", "NVDA"], sectors=[
            {"exposure_id": "sector_mlcc", "display_name": "被動元件 MLCC", "resolved_tickers": [{"ticker": "2327", "name": "國巨"}]},
            {"exposure_id": "sector_mlcc", "display_name": "被動元件 MLCC", "resolved_tickers": []},  # same sector twice = one vote
            {"exposure_id": "sector_semiconductor", "display_name": "半導體", "resolved_tickers": []},  # umbrella → never listed
        ]),
        _ep("E2", "2026-09-03T02:00:00", ["2330"], podcast="財經一路發"),
        _ep("OLD", "2026-08-25T02:00:00", ["2330"]),  # previous week — excluded
    ]

    async def _recent(*a, **k):
        return eps

    async def _by_podcaster(podcaster, start_date=None, end_date=None):
        if start_date == "2026-08-31":  # this week
            return [{"ticker": "2330", "sentiment_label": "STRONG_BULLISH"}, {"ticker": "2330", "sentiment_label": "NEUTRAL"}] if podcaster == "股癌" else []
        return [{"ticker": "2330", "sentiment_label": "BEARISH"}]  # previous week, every podcaster

    async def _movers(week, *, allowed):
        return {"week": week, "as_of": "2026-09-06", "high": [], "low": []}

    async def _roster():
        return None

    monkeypatch.setattr(weekly.podcast_service, "get_recent_episodes", _recent)
    monkeypatch.setattr(weekly.insight_service, "get_by_podcaster", _by_podcaster)
    monkeypatch.setattr(weekly.podcast_service, "_allowed_podcast_names", _roster)
    monkeypatch.setattr(weekly, "attention_movers", _movers)

    wk = await weekly.build_week("2026-W36")
    assert wk["episode_count"] == 2
    assert wk["podcasts"] == [{"name": "股癌", "episodes": 1}, {"name": "財經一路發", "episodes": 1}]
    top = wk["tickers"][0]
    assert (top["ticker"], top["episodes"], top["bull"], top["neu"], top["bear"]) == ("2330", 2, 1, 1, 0)
    assert (top["prev_bull"], top["prev_bear"]) == (0, 2)  # two podcasters × one bearish insight
    assert wk["sectors"] == [{"exposure_id": "sector_mlcc", "episodes": 1, "display_name": "被動元件 MLCC", "icon_id": None, "color_hex": None}]
    assert [e["id"] for e in wk["episodes"]] == ["E2", "E1"]  # newest first
    assert wk["episodes"][0]["key_insights"] == ["一", "二", "三", "四"]
    assert wk["episodes"][0]["podcast_name"] == "財經一路發"  # full Episode shape
    assert wk["movers"]["as_of"] == "2026-09-06" and "flips" not in wk

    assert await weekly.build_week("2026-W30") is None


@pytest.mark.asyncio
async def test_list_weeks_counts_scoped_episodes_newest_first(monkeypatch):
    async def _recent(*a, **k):
        return [
            _ep("A", "2026-09-01T02:00:00", ["2330", "NVDA"], sectors=[{"exposure_id": "sector_mlcc", "display_name": "被動元件 MLCC", "resolved_tickers": [{"ticker": "2330", "name": "台積電"}]}]),
            _ep("B", "2026-09-02T02:00:00", ["2330"], podcast="財經一路發"),
            _ep("C", "2026-08-25T02:00:00", []),
        ]

    monkeypatch.setattr(weekly.podcast_service, "get_recent_episodes", _recent)
    weeks = await weekly.list_weeks()
    assert [(w["week"], w["episode_count"]) for w in weeks] == [("2026-W36", 2), ("2026-W35", 1)]
    assert weeks[0]["start"] == "2026-08-31"
    assert weeks[0]["podcast_count"] == 2
    assert weeks[0]["top_tickers"][0] == {"ticker": "2330", "name": "台積電", "episodes": 2}
    assert weeks[0]["top_sectors"] == [{"exposure_id": "sector_mlcc", "display_name": "被動元件 MLCC", "episodes": 1}]
    assert weeks[1]["top_tickers"] == [] and weeks[1]["podcast_count"] == 1


@pytest.mark.asyncio
async def test_movers_come_from_attention_with_the_roster_and_carry_the_stated_reason(monkeypatch):
    """The list is attention_movers' (one owner, same number as the stock page); the
    rollup only resolves the roster and attaches what a show actually said."""
    seen = {}

    async def _roster():
        return frozenset({"股癌"})

    async def _movers(week, *, allowed):
        seen["allowed"] = allowed
        return {"week": week, "as_of": "2026-09-06",
                "high": [{"ticker": "2408", "name": "南亞科", "level": 97, "mentions": 4, "shows": 3}],
                "low": [{"ticker": "2330", "name": "台積電", "level": 6, "mentions": 2, "shows": 2}]}

    monkeypatch.setattr(weekly.podcast_service, "_allowed_podcast_names", _roster)
    monkeypatch.setattr(weekly, "attention_movers", _movers)
    why = {"2408": {"bull": {"thesis": "DRAM 缺貨", "podcaster": "股癌", "horizon": "短期"}}}

    voices = {"2408": [{"podcaster": "股癌", "side": "看多", "thesis": "DRAM 缺貨。", "when": "2026-09-05"}]}
    movers = await weekly._movers("2026-W36", why, voices)
    assert seen["allowed"] == frozenset({"股癌"})
    assert movers["high"][0]["bull_why"]["thesis"] == "DRAM 缺貨"
    assert movers["high"][0]["bear_why"] is None
    assert movers["low"][0]["bull_why"] is None  # no stated reason → None, never invented
    assert "share" not in movers["high"][0]
    assert movers["high"][0]["voices"][0]["podcaster"] == "股癌" and movers["low"][0]["voices"] == []


@pytest.mark.asyncio
async def test_movers_failure_degrades_to_none_instead_of_breaking_the_public_page(monkeypatch):
    """/weekly/{week} is the crawled public page; an attention query must not 500 it."""
    async def _roster():
        return None

    async def _boom(week, *, allowed):
        raise RuntimeError("db down")

    monkeypatch.setattr(weekly.podcast_service, "_allowed_podcast_names", _roster)
    monkeypatch.setattr(weekly, "attention_movers", _boom)
    assert await weekly._movers("2026-W36", {}, {}) is None


def test_reasons_keeps_the_latest_stance_per_side_and_drops_neutral():
    """The thesis is what makes a count arguable; neutral rows carry no direction."""
    insights = [
        {"ticker": "3037", "sentiment_label": "BULLISH", "bluf_thesis": "舊的看多說法",
         "podcaster": "A", "time_horizon": "中期", "podcast_launch_time": "2026-09-01"},
        {"ticker": "3037", "sentiment_label": "STRONG_BULLISH", "bluf_thesis": "本週最新的看多說法",
         "podcaster": "B", "time_horizon": "長期", "podcast_launch_time": "2026-09-04"},
        {"ticker": "3037", "sentiment_label": "BEARISH", "bluf_thesis": "載板漲價動能不足",
         "podcaster": "C", "time_horizon": "短期", "podcast_launch_time": "2026-09-03"},
        {"ticker": "3037", "sentiment_label": "NEUTRAL", "bluf_thesis": "持平看待",
         "podcaster": "D", "podcast_launch_time": "2026-09-05"},
        {"ticker": "2330", "sentiment_label": "BULLISH", "bluf_thesis": "   ",  # empty → skipped
         "podcaster": "E", "podcast_launch_time": "2026-09-02"},
    ]
    why = weekly._reasons(insights)
    assert why["3037"]["bull"] == {"thesis": "本週最新的看多說法。", "podcaster": "B", "horizon": "長期"}
    assert why["3037"]["bear"]["podcaster"] == "C"
    assert "neu" not in why["3037"]
    assert "2330" not in why


def test_reasons_never_carry_a_forecast_or_advice_onto_the_brand_account():
    """2026-W37: 聯發科's latest thesis ended in an EPS estimate and a 上看 target."""
    assert weekly._descriptive(
        "聯發科8月營收年增44%，輝達以可轉債參與增資，ASIC業務前景看好，法人預估明年EPS可達140元、後年上看300元。"
    ) == "聯發科8月營收年增44%，輝達以可轉債參與增資，ASIC業務前景看好。"
    assert weekly._descriptive("欣興是載板族群，法人買進，但本益比高，建議往更上游看。") == "欣興是載板族群，法人買進，但本益比高。"
    assert weekly._descriptive("目標價上看 1200 元") == ""
    # a reported surprise is a fact, not a forecast — it stays
    assert weekly._descriptive("iPhone Duo 定價低於市場預期，有機會帶動市佔") == "iPhone Duo 定價低於市場預期，有機會帶動市佔。"

    # an all-forecast latest thesis falls back to the latest descriptive one, not to nothing
    why = weekly._reasons([
        {"ticker": "2454", "sentiment_label": "BULLISH", "bluf_thesis": "ASIC 設計能力強",
         "podcaster": "A", "podcast_launch_time": "2026-09-09"},
        {"ticker": "2454", "sentiment_label": "BULLISH", "bluf_thesis": "法人預估明年 EPS 可達 140 元",
         "podcaster": "B", "podcast_launch_time": "2026-09-11"},
    ])
    assert why["2454"]["bull"]["thesis"] == "ASIC 設計能力強。" and why["2454"]["bull"]["podcaster"] == "A"


def test_voices_give_each_show_its_own_latest_descriptive_sentence():
    """One quote for a ticker four shows discussed made the copy invent the other three."""
    ins = [
        {"ticker": "2454", "podcaster": "A", "sentiment_label": "BULLISH", "bluf_thesis": "舊說法", "podcast_launch_time": "2026-09-08"},
        {"ticker": "2454", "podcaster": "A", "sentiment_label": "NEUTRAL", "bluf_thesis": "新說法", "podcast_launch_time": "2026-09-10"},
        {"ticker": "2454", "podcaster": "B", "sentiment_label": "BEARISH", "bluf_thesis": "短線有壓力", "podcast_launch_time": "2026-09-09"},
        {"ticker": "2454", "podcaster": "C", "sentiment_label": "BULLISH", "bluf_thesis": "目標價上看 1500 元", "podcast_launch_time": "2026-09-11"},
    ]
    v = weekly._voices(ins)["2454"]
    assert [(x["podcaster"], x["side"], x["thesis"]) for x in v] == [("A", "中性", "新說法。"), ("B", "看空", "短線有壓力。")]
    assert len(weekly._voices([{**ins[0], "podcaster": f"S{i}", "podcast_launch_time": f"2026-09-0{i}"} for i in range(1, 8)])["2454"]) == weekly.VOICES_PER_MOVER
