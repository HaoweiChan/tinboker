"""Intraday market-move posts: Yahoo parsing, the "big move" rule, the window, the hedge
wording, the card, and one tick end to end against the ledger."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from src.services import market_moves as mm
from src.services import social_ledger, yahoo_chart
from src.services.intraday_card import intraday_card_svg, segments
from src.services.yahoo_chart import Intraday, YahooChartError

TPE = ZoneInfo("Asia/Taipei")
OPEN = int(datetime(2026, 10, 14, 9, 0, tzinfo=TPE).timestamp())
CLOSE = int(datetime(2026, 10, 14, 13, 30, tzinfo=TPE).timestamp())


def _day(values, prev=100.0, start=OPEN, step=60, symbol="^TWII", tz="Asia/Taipei", end=CLOSE):
    return Intraday(symbol, tz, prev, start, end, [(start + i * step, v) for i, v in enumerate(values)])


def _payload(prev=100.0, closes=(101.0, None, 102.0)):
    return {"chart": {"result": [{
        "meta": {"previousClose": prev, "exchangeTimezoneName": "Asia/Taipei",
                 "currentTradingPeriod": {"regular": {"start": OPEN, "end": CLOSE}}},
        "timestamp": [OPEN + 60 * i for i in range(len(closes))],
        "indicators": {"quote": [{"close": list(closes)}]},
    }], "error": None}}


# ── yahoo_chart ─────────────────────────────────────────────────────────────

def test_parse_intraday_drops_untraded_minutes_and_keeps_the_session():
    day = yahoo_chart.parse_intraday(_payload(), "^TWII")
    assert day.points == [(OPEN, 101.0), (OPEN + 120, 102.0)]
    assert (day.prev_close, day.session_start, day.session_end, day.tz) == (100.0, OPEN, CLOSE, "Asia/Taipei")
    assert round(day.pct, 2) == 2.0 and day.high == 102.0 and day.open == 101.0


def test_parse_intraday_without_bars_or_previous_close_is_an_error():
    with pytest.raises(YahooChartError):
        yahoo_chart.parse_intraday(_payload(closes=(None,)), "^TWII")
    with pytest.raises(YahooChartError):
        yahoo_chart.parse_intraday(_payload(prev=None), "^TWII")
    with pytest.raises(YahooChartError):
        yahoo_chart.parse_intraday({"chart": {"result": [], "error": {"code": "Not Found"}}}, "^NOPE")


def test_until_pins_the_day_to_the_minute_the_post_saw():
    day = _day([100, 101, 102, 103])
    assert day.until(OPEN + 60).last == 101 and day.until(None) is day
    with pytest.raises(YahooChartError):
        day.until(OPEN - 1)


def test_daily_sigma_needs_twenty_returns():
    assert yahoo_chart.daily_sigma([100.0] * 10) is None
    closes = [100.0, 101.0] * 15
    assert yahoo_chart.daily_sigma(closes) == pytest.approx(1.0, rel=0.05)


def test_parse_news_keeps_only_linked_headlines():
    out = yahoo_chart.parse_news({"news": [
        {"title": "Stocks slide", "publisher": "Reuters", "link": "https://r/1", "providerPublishTime": 5},
        {"title": "", "link": "https://x"}, {"title": "no link"}]})
    assert out == [{"title": "Stocks slide", "publisher": "Reuters", "url": "https://r/1", "published": 5}]


# ── the rules ───────────────────────────────────────────────────────────────

def test_big_needs_the_floor_and_the_sigma_multiple():
    day = _day([99.0, 98.0, 98.2])                                  # -1.8%
    assert mm.is_big(day, 1.0, k=1.5, floor_pct=1.0)
    assert not mm.is_big(day, 1.5, k=1.5, floor_pct=1.0)            # 1.8 < 2.25: an ordinary day for this index
    assert not mm.is_big(day, None, k=1.5, floor_pct=2.0)           # under the floor
    assert mm.is_big(day, None, k=1.5, floor_pct=1.0)               # no sigma → floor alone


def test_a_gap_that_has_already_filled_is_not_a_move():
    assert not mm.is_big(_day([96.0, 97.5, 98.5]), 0.5, k=1.5, floor_pct=1.0)   # -4% → -1.5%: less than half held
    assert mm.is_big(_day([96.0, 97.0, 97.9]), 0.5, k=1.5, floor_pct=1.0)       # -2.1% of -4%: still holding


def test_window_opens_after_the_delay_and_closes_after_the_window():
    tw = mm.MARKETS["TW"]
    at = lambda h, m, d=14: datetime(2026, 10, d, h, m, tzinfo=TPE)  # noqa: E731
    assert mm.window_date(tw, at(9, 29)) is None
    assert str(mm.window_date(tw, at(9, 30))) == "2026-10-14"
    assert mm.window_date(tw, at(10, 59)) is not None
    assert mm.window_date(tw, at(11, 0)) is None
    assert mm.window_date(tw, at(9, 45, d=17)) is None              # Saturday


def test_us_window_follows_new_york_daylight_saving():
    us = mm.MARKETS["US"]
    utc = lambda *a: datetime(*a, tzinfo=timezone.utc)  # noqa: E731
    assert mm.window_date(us, utc(2026, 10, 14, 14, 0)) is not None  # EDT: 10:00 NY
    assert mm.window_date(us, utc(2026, 11, 4, 14, 0)) is None       # EST: 09:00 NY, before the open
    assert mm.window_date(us, utc(2026, 11, 4, 15, 0)) is not None   # EST: 10:00 NY


def test_a_holiday_session_from_yesterday_is_not_today():
    day = _day([101.0, 102.0])
    today = datetime.fromtimestamp(OPEN, TPE).date()
    now = datetime.fromtimestamp(OPEN + 600, timezone.utc)
    assert mm.is_today(day, today, now)
    assert not mm.is_today(day, today.replace(day=15), now)
    assert not mm.is_today(day, today, datetime.fromtimestamp(OPEN + 3600, timezone.utc))  # tape stopped
    assert mm.is_today(day, today, datetime.fromtimestamp(OPEN + 25 * 60, timezone.utc))  # a delayed feed


def test_the_hedge_comes_from_publisher_count_not_the_model():
    assert mm.cause_text("美債殖利率走升。", {"reuters", "bloomberg"}) == ("consensus", "主因美債殖利率走升")
    assert mm.cause_text("美債殖利率走升", {"reuters"}) == ("reported", "市場推測與美債殖利率走升有關")
    assert mm.cause_text("美債殖利率走升", set()) == ("none", "")
    assert mm.cause_text("", {"a", "b"}) == ("none", "")
    assert mm.cause_text("很" * 40, {"a", "b"})[0] == "none"         # an essay is not a clause


def test_the_lead_is_the_most_unusual_index_not_the_biggest_percent():
    spx = mm.Move(mm.Index("^GSPC", "S&P 500"), _day([97.0]), 1.0)  # -3%, 3 sigma
    sox = mm.Move(mm.Index("^SOX", "費城半導體"), _day([96.0]), 2.0)  # -4%, 2 sigma
    assert mm.headline_move([sox, spx]).index.id == "GSPC"


def test_the_post_is_one_plain_sentence_with_no_tag_and_no_price_block():
    sox = mm.Index("^SOX", "費城半導體", "費城半導體指數")
    text = mm.compose_text(mm.Move(sox, _day([95.81]), 1.0), "市場推測與輝達財測不如預期有關")
    assert text == "費城半導體指數盤中重挫逾4%，市場推測與輝達財測不如預期有關。"
    assert mm.compose_text(mm.Move(mm.Index("^TWII", "加權指數"), _day([102.3]), 1.0), "") == "加權指數盤中大漲逾2%。"
    assert "盤中速報" not in text and "\n" not in text


def test_amount_reads_like_a_person_says_it():
    assert (mm.amount(-4.19), mm.amount(3.02), mm.amount(2.5), mm.amount(0.8)) == ("逾4%", "3%", "逾2%", "0.8%")


# ── the reason ──────────────────────────────────────────────────────────────

NOW = datetime.fromtimestamp(OPEN + 1800, timezone.utc)


def _headlines():
    t = int(NOW.timestamp()) - 3600
    return [{"title": "Taiwan stocks fall as yields jump", "publisher": "Reuters", "url": "https://r/1", "published": t},
            {"title": "Asia slides on Treasury yields", "publisher": "Bloomberg", "url": "https://b/1", "published": t},
            {"title": "Old story", "publisher": "CNBC", "url": "https://c/1", "published": t - 3 * 86400}]


@pytest.mark.asyncio
async def test_two_publishers_backing_the_cause_is_consensus_and_bad_ids_are_dropped(monkeypatch):
    monkeypatch.setattr(mm.settings, "openrouter_api_key", "k")
    seen = {}

    async def news(q, count=12):
        return _headlines()

    async def extract(market, lead, headlines):
        seen["n"] = len(headlines)
        return {"cause": "美債殖利率走升", "support": [0, 1, 1, 7, "x"]}
    monkeypatch.setattr(mm.yahoo_chart, "news", news)
    monkeypatch.setattr(mm, "_extract_cause", extract)
    lead = mm.Move(mm.Index("^TWII", "加權指數"), _day([97.0]), 1.0)
    out = await mm.find_cause(mm.MARKETS["TW"], lead, NOW)
    assert seen["n"] == 2                                          # the 3-day-old one and the duplicate query are gone
    assert out["tier"] == "consensus" and [s["publisher"] for s in out["sources"]] == ["Reuters", "Bloomberg"]


@pytest.mark.asyncio
async def test_a_failed_model_call_posts_without_a_reason(monkeypatch):
    monkeypatch.setattr(mm.settings, "openrouter_api_key", "k")

    async def news(q, count=12):
        return _headlines()

    async def boom(*_a):
        raise RuntimeError("timeout")
    monkeypatch.setattr(mm.yahoo_chart, "news", news)
    monkeypatch.setattr(mm, "_extract_cause", boom)
    lead = mm.Move(mm.Index("^TWII", "加權指數"), _day([97.0]), 1.0)
    out = await mm.find_cause(mm.MARKETS["TW"], lead, NOW)
    assert (out["tier"], out["clause"], out["sources"]) == ("none", "", [])
    monkeypatch.setattr(mm.settings, "openrouter_api_key", None)
    assert (await mm.find_cause(mm.MARKETS["TW"], lead, NOW))["error"] == "no_openrouter_key"


# ── the card ────────────────────────────────────────────────────────────────

def test_card_breaks_the_line_over_lunch_and_says_it_is_still_trading():
    tky = ZoneInfo("Asia/Tokyo")
    start = int(datetime(2026, 10, 14, 9, 0, tzinfo=tky).timestamp())
    end = int(datetime(2026, 10, 14, 15, 30, tzinfo=tky).timestamp())
    pts = [(start + 60 * m, 100 + m * 0.01) for m in range(150)] + \
          [(start + 60 * m, 101 + m * 0.01) for m in range(210, 240)]
    day = Intraday("^N225", "Asia/Tokyo", 99.0, start, end, pts)
    assert len(segments(day.points)) == 2
    svg = intraday_card_svg("日經225", "N225", day, peers=[("TOPIX", -0.5)])
    assert "午休" in svg and "盤中" in svg and "東京時間" in svg and "昨收 99.00" in svg
    assert "TOPIX" in svg and "-0.50%" in svg and "Yahoo Finance" in svg
    assert svg.count('stroke-linejoin="round"') == 2


def test_card_after_the_close_says_so_and_needs_two_bars():
    day = _day([101.0, 102.0], end=OPEN + 60)
    assert "收盤" in intraday_card_svg("加權指數", "TWII", day)
    with pytest.raises(ValueError):
        intraday_card_svg("加權指數", "TWII", _day([101.0]))


# ── one tick, end to end against the ledger ─────────────────────────────────

class _FakeThreads:
    is_configured = True

    def __init__(self):
        self.posts, self.replies = [], []

    async def publish(self, text, image_url=None):
        self.posts.append((text, image_url))
        return f"m{len(self.posts)}"

    async def publish_reply(self, text, reply_to_id, **_):
        self.replies.append((text, reply_to_id))
        return f"r{len(self.replies)}"


def _wire(monkeypatch, days, sigmas=None):
    monkeypatch.setattr(mm.settings, "market_move_markets", "TW")
    monkeypatch.setattr(mm.settings, "public_api_url", "https://api.tinboker.com")

    async def intraday(symbol):
        if symbol not in days:
            raise YahooChartError("down")
        return days[symbol]

    async def sigma(symbol):
        return (sigmas or {}).get(symbol, 1.0)

    async def cause(market, lead, now):
        return {"tier": "reported", "clause": "市場推測與美債殖利率走升有關", "cause": "美債殖利率走升",
                "sources": [{"publisher": "Reuters", "title": "Yields jump", "url": "https://r/1"}]}
    monkeypatch.setattr(mm.yahoo_chart, "intraday", intraday)
    monkeypatch.setattr(mm.yahoo_chart, "sigma", sigma)
    monkeypatch.setattr(mm, "find_cause", cause)
    fake = _FakeThreads()
    monkeypatch.setattr(mm, "ThreadsService", lambda: fake)
    return fake


@pytest.mark.asyncio
async def test_a_big_morning_posts_once_with_the_pinned_card_and_the_sources(temp_db, monkeypatch):
    twii = _day([97.5] * 30 + [97.0])
    fake = _wire(monkeypatch, {"^TWII": twii, "^TWOII": _day([98.0] * 31, symbol="^TWOII")})
    now = datetime.fromtimestamp(OPEN + 1830, timezone.utc)

    assert await mm.publish_due(now) == 1
    text, image = fake.posts[0]
    assert text == "台股加權指數盤中重挫3%，市場推測與美債殖利率走升有關。"
    assert image == f"https://api.tinboker.com/api/og/market/TWII.png?until={twii.last_ts}"
    assert fake.replies[0][0].startswith("消息來源：\n・Reuters：Yields jump") and fake.replies[0][1] == "m1"
    row = social_ledger.list_posted("threads")[0]
    assert (row["episode_id"], row["format"], row["subject"]) == \
        ("market_move:intraday:TW:2026-10-14", "market_move_intraday", "TWII")

    assert await mm.publish_due(now) == 0                           # once per market per day
    assert len(fake.posts) == 1


@pytest.mark.asyncio
async def test_a_quiet_morning_or_a_closed_window_posts_nothing(temp_db, monkeypatch):
    fake = _wire(monkeypatch, {"^TWII": _day([100.3] * 31), "^TWOII": _day([100.1] * 31)})
    assert await mm.publish_due(datetime.fromtimestamp(OPEN + 1830, timezone.utc)) == 0

    _wire(monkeypatch, {"^TWII": _day([95.0] * 31)})
    assert await mm.publish_due(datetime.fromtimestamp(OPEN + 600, timezone.utc)) == 0   # 09:10: too early
    monkeypatch.setattr(mm.settings, "market_move_markets", "")
    assert await mm.publish_due(datetime.fromtimestamp(OPEN + 1830, timezone.utc)) == 0  # off
    assert fake.posts == []


@pytest.mark.asyncio
async def test_a_failed_publish_releases_the_day_and_backs_off(temp_db, monkeypatch):
    from src.services.threads_service import ThreadsError
    fake = _wire(monkeypatch, {"^TWII": _day([97.0] * 31), "^TWOII": _day([98.0] * 31)})
    calls = []

    async def boom(text, image_url=None):
        calls.append(text)
        raise ThreadsError("image fetch failed")
    monkeypatch.setattr(fake, "publish", boom)
    monkeypatch.setattr(mm, "_retry_at", {})
    now = datetime.fromtimestamp(OPEN + 1830, timezone.utc)
    assert await mm.publish_due(now) == 0
    assert social_ledger.already_posted("threads", "market_move:intraday:TW:2026-10-14") is False
    assert await mm.publish_due(datetime.fromtimestamp(OPEN + 1890, timezone.utc)) == 0
    assert len(calls) == 1                                          # backing off, no second attempt
    await mm.publish_due(datetime.fromtimestamp(OPEN + 1830 + 601, timezone.utc))
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_preview_drafts_without_posting(temp_db, monkeypatch):
    fake = _wire(monkeypatch, {"^TWII": _day([100.3] * 31), "^TWOII": _day([100.1] * 31)})
    now = datetime.fromtimestamp(OPEN + 1830, timezone.utc)
    quiet = await mm.preview("tw", now=now)
    assert quiet["draft"] is None and quiet["in_window"] and quiet["indices"][0]["big"] is False
    forced = await mm.preview("TW", force=True, now=now)
    assert forced["draft"]["text"].startswith("台股加權指數盤中") and fake.posts == []
    with pytest.raises(KeyError):
        await mm.preview("XX", now=now)


# ── the card route ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_card_route_pins_the_day_and_tolerates_a_missing_peer(monkeypatch):
    from fastapi import HTTPException

    from src.routers import og as og_router
    seen = {}

    async def intraday(symbol):
        if symbol == "^TWOII":
            raise YahooChartError("down")
        return _day([101.0, 102.0, 103.0])

    def svg(name, code, day, peers):
        seen.update(name=name, last=day.last, peers=peers)
        return "<svg/>"
    monkeypatch.setattr(og_router.yahoo_chart, "intraday", intraday)
    monkeypatch.setattr(og_router, "intraday_card_svg", svg)
    monkeypatch.setattr(og_router, "svg_to_png", lambda s, w, h: b"png")

    resp = await og_router.market_card_raster("TWII", until=OPEN + 60)
    assert resp.body == b"png" and resp.headers["cache-control"] == "public, max-age=86400"
    assert seen == {"name": "加權指數", "last": 102.0, "peers": []}
    with pytest.raises(HTTPException) as e:
        await og_router.market_card_raster("NOPE", until=None)
    assert e.value.status_code == 404
