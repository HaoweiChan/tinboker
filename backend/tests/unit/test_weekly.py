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

    monkeypatch.setattr(weekly.podcast_service, "get_recent_episodes", _recent)
    monkeypatch.setattr(weekly.insight_service, "get_by_podcaster", _by_podcaster)

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


def _row(ticker, episodes, now, prev):
    b, n, r = now
    pb, pn, pr = prev
    return {"ticker": ticker, "name": None, "episodes": episodes,
            "bull": b, "neu": n, "bear": r, "prev_bull": pb, "prev_neu": pn, "prev_bear": pr}


def test_flip_rows_needs_real_voices_not_a_share_that_moved():
    """Absolute counts, because podcasts are not a survey — see flip_rows' docstring."""
    rows = [
        _row("8046", 8, (1, 4, 3), (5, 2, 0)),    # 0 → 3 bear: a real turn
        _row("3037", 8, (4, 3, 4), (7, 1, 0)),    # 0 → 4 bear: a bigger one
        _row("2317", 7, (2, 5, 2), (2, 4, 2)),    # bear flat at 2 → never picked
        _row("SPCX", 7, (7, 8, 0), (0, 8, 0)),    # 0 → 7 bull
        _row("2330", 15, (15, 3, 0), (11, 4, 0)),  # +4 bull, but a smaller jump than SPCX
    ]
    picks = weekly.flip_rows(rows)
    assert [p["ticker"] for p in picks] == ["3037", "8046", "SPCX"]
    assert [p["direction"] for p in picks] == ["bear", "bear", "bull"]


def test_flip_rows_returns_nothing_when_nobody_actually_turned():
    """The common case. Over 2026-W32..36 a share-based rule invented a lead every week;
    printing "nobody changed their mind" beats manufacturing one."""
    quiet = [
        _row("TSLA", 8, (1, 5, 2), (0, 6, 1)),    # 1 → 2 bear, below FLIP_MIN_BEAR
        _row("2303", 9, (0, 6, 1), (3, 4, 1)),    # bear unmoved; only the bulls left
        _row("2383", 7, (4, 3, 1), (5, 2, 0)),    # a single bear voice
        _row("9999", 3, (0, 0, 5), (5, 0, 0)),    # violent, but too thinly covered
        _row("AAPL", 9, (4, 4, 0), (2, 5, 0)),    # +2 bull: below FLIP_MIN_BULL's jump
    ]
    assert weekly.flip_rows(quiet) == []


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
    assert why["3037"]["bull"] == {"thesis": "本週最新的看多說法", "podcaster": "B", "horizon": "長期"}
    assert why["3037"]["bear"]["podcaster"] == "C"
    assert "neu" not in why["3037"]
    assert "2330" not in why
