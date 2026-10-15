"""Intraday market-move posts: Yahoo parsing, the "big move" rule, the window, the hedge
wording, the card, and one tick end to end against the ledger."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import urllib.parse

import pytest

from src.services import market_moves as mm
from src.services import social_ledger, yahoo_chart
from src.services.intraday_card import intraday_card_svg, segments
from src.services.yahoo_chart import Intraday, Quote, YahooChartError

TPE = ZoneInfo("Asia/Taipei")


@pytest.fixture(autouse=True)
def _no_local_feeds(monkeypatch):
    """Unit tests never reach the RSS wires; tests that want headlines stub them."""
    from src.services import market_news

    async def none(market_id):
        return []
    monkeypatch.setattr(market_news, "headlines", none)
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
    spx = mm.Move(mm.Instrument("^GSPC", "S&P 500"), _day([97.0]), 1.0)  # -3%, 3 sigma
    sox = mm.Move(mm.Instrument("^SOX", "費城半導體"), _day([96.0]), 2.0)  # -4%, 2 sigma
    assert mm.headline_move([sox, spx]).index.id == "GSPC"


def test_the_post_is_one_plain_sentence_with_no_tag_and_no_price_block():
    sox = mm.Instrument("^SOX", "費城半導體", "費城半導體指數")
    text = mm.compose_text(mm.Move(sox, _day([95.81]), 1.0), "市場推測與輝達財測不如預期有關")
    assert text == "費城半導體指數盤中重挫逾4%，市場推測與輝達財測不如預期有關。"
    assert mm.compose_text(mm.Move(mm.Instrument("^TWII", "加權指數"), _day([102.3]), 1.0), "") == "加權指數盤中大漲逾2%。"
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
    lead = mm.Move(mm.Instrument("^TWII", "加權指數"), _day([97.0]), 1.0)
    out = await mm.find_cause(mm.MARKETS["TW"], mm.subject_of(mm.MARKETS["TW"], lead), NOW)
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
    lead = mm.Move(mm.Instrument("^TWII", "加權指數"), _day([97.0]), 1.0)
    out = await mm.find_cause(mm.MARKETS["TW"], mm.subject_of(mm.MARKETS["TW"], lead), NOW)
    assert (out["tier"], out["clause"], out["sources"]) == ("none", "", [])
    monkeypatch.setattr(mm.settings, "openrouter_api_key", None)
    assert (await mm.find_cause(mm.MARKETS["TW"], mm.subject_of(mm.MARKETS["TW"], lead), NOW))["error"] \
        == "no_openrouter_key"


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


def test_card_prints_the_reason_under_the_change_and_gives_up_chart_room_for_it():
    day = _day([101.0, 102.0, 101.5])
    plain = intraday_card_svg("加權指數", "TWII", day)
    told = intraday_card_svg("加權指數", "TWII", day, reason="主因美國公債殖利率急升，外資賣超擴大")
    assert "主因美國公債殖利率急升" in told and "主因" not in plain
    assert 'y="286"' in told and 'y="286"' not in plain             # the line sits under the change
    assert 'y1="340.0"' in told and 'y1="300.0"' in plain           # the top gridline moves down by one line


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
    monkeypatch.setattr(mm, "_retry_at", {})

    async def intraday(symbol):
        if symbol not in days:
            raise YahooChartError("down")
        return days[symbol]

    async def sigma(symbol):
        return (sigmas or {}).get(symbol, 1.0)

    async def cause(market, lead, now):
        return {"tier": "reported", "clause": "市場推測與美債殖利率走升有關", "cause": "美債殖利率走升",
                "sources": [{"publisher": "Reuters", "title": "Yields jump", "url": "https://r/1"}]}
    async def quotes(symbols):
        return {s: Quote(s, d.prev_close, d.last, d.last_ts) for s, d in days.items() if s in symbols}

    async def no_baskets(market, now):
        return []
    monkeypatch.setattr(mm.yahoo_chart, "intraday", intraday)
    monkeypatch.setattr(mm.yahoo_chart, "sigma", sigma)
    monkeypatch.setattr(mm.yahoo_chart, "quotes", quotes)
    monkeypatch.setattr(mm, "baskets", no_baskets)
    monkeypatch.setattr(mm, "_theme_scanned_at", {})
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
    assert image == (f"https://api.tinboker.com/api/og/market/TWII.png?until={twii.last_ts}"
                     f"&reason={urllib.parse.quote_plus('市場推測與美債殖利率走升有關')}")
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
async def test_no_reason_means_no_post_and_a_later_retry(temp_db, monkeypatch):
    fake = _wire(monkeypatch, {"^TWII": _day([97.0] * 31), "^TWOII": _day([98.0] * 31)})
    monkeypatch.setattr(mm, "_retry_at", {})
    asks = []

    async def no_cause(market, lead, now):
        asks.append(now)
        return {"tier": "none", "clause": "", "cause": "", "sources": [], "error": "no_fresh_headlines"}
    monkeypatch.setattr(mm, "find_cause", no_cause)
    t0 = OPEN + 1830
    assert await mm.publish_due(datetime.fromtimestamp(t0, timezone.utc)) == 0
    assert await mm.publish_due(datetime.fromtimestamp(t0 + 60, timezone.utc)) == 0
    assert fake.posts == [] and len(asks) == 1                      # backing off, not asking every minute
    assert social_ledger.already_posted("threads", "market_move:intraday:TW:2026-10-14") is False

    async def found(market, lead, now):
        return {"tier": "consensus", "clause": "主因美債殖利率急升", "cause": "美債殖利率急升", "sources": []}
    monkeypatch.setattr(mm, "find_cause", found)
    assert await mm.publish_due(datetime.fromtimestamp(t0 + 601, timezone.utc)) == 1
    assert fake.posts[0][0] == "台股加權指數盤中重挫3%，主因美債殖利率急升。"


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


# ── the giants lane ─────────────────────────────────────────────────────────

FLAT = {"^TWII": _day([100.2] * 31), "^TWOII": _day([100.1] * 31, symbol="^TWOII")}


def _tick(minutes):
    return datetime.fromtimestamp(OPEN + 1830 + minutes * 60, timezone.utc)


@pytest.mark.asyncio
async def test_a_giant_with_a_big_morning_posts_its_own_card(temp_db, monkeypatch):
    tsmc = _day([96.0] * 30 + [95.8], symbol="2330.TW")
    fake = _wire(monkeypatch, {**FLAT, "2330.TW": tsmc})
    assert await mm.publish_due(_tick(0)) == 1
    text, image = fake.posts[0]
    assert text == "台積電盤中重挫逾4%，市場推測與美債殖利率走升有關。"
    assert image == (f"https://api.tinboker.com/api/og/market/2330_TW.png?until={tsmc.last_ts}"
                     f"&reason={urllib.parse.quote_plus('市場推測與美債殖利率走升有關')}")
    row = social_ledger.list_posted("threads")[0]
    assert (row["episode_id"], row["subject"]) == ("market_move:stock:TW:2026-10-14:2330_TW", "2330_TW")
    assert await mm.publish_due(_tick(1)) == 0                      # once per stock per day


@pytest.mark.asyncio
async def test_a_stock_needs_the_bigger_floor(temp_db, monkeypatch):
    fake = _wire(monkeypatch, {**FLAT, "2330.TW": _day([97.6] * 31)}, sigmas={"2330.TW": 0.5})
    assert await mm.publish_due(_tick(0)) == 0                      # -2.4%: 4.8 sigma, still under 3%
    assert fake.posts == []


@pytest.mark.asyncio
async def test_index_first_then_giants_one_post_per_tick_and_a_daily_cap(temp_db, monkeypatch):
    days = {"^TWII": _day([97.0] * 31), "^TWOII": _day([98.0] * 31, symbol="^TWOII"),
            "2330.TW": _day([95.0] * 31, symbol="2330.TW"), "2317.TW": _day([94.0] * 31, symbol="2317.TW"),
            "2454.TW": _day([93.0] * 31, symbol="2454.TW")}
    fake = _wire(monkeypatch, days)
    for m in range(4):
        await mm.publish_due(_tick(m))
    subjects = [r["subject"] for r in sorted(social_ledger.list_posted("threads"), key=lambda r: r["media_id"])]
    assert subjects == ["TWII", "2454_TW", "2317_TW"]               # index, then most unusual giants; cap of 2
    assert len(fake.posts) == 3


@pytest.mark.asyncio
async def test_stock_reason_searches_by_its_own_name(monkeypatch):
    monkeypatch.setattr(mm.settings, "openrouter_api_key", "k")
    queries = []

    async def news(q, count=12):
        queries.append(q)
        return []
    monkeypatch.setattr(mm.yahoo_chart, "news", news)
    nvda = mm.BY_ID["NVDA"][1]
    out = await mm.find_cause(mm.MARKETS["US"], mm.subject_of(mm.MARKETS["US"], mm.Move(nvda, _day([95.0]), 2.0)), NOW)
    assert queries == ["Nvidia", "NVDA"] and out["error"] == "no_fresh_headlines (raw=0)"


@pytest.mark.asyncio
async def test_stock_card_compares_with_the_main_index(monkeypatch):
    from src.routers import og as og_router
    seen = {}

    async def intraday(symbol):
        return {"2330.TW": _day([96.0, 95.0]), "^TWII": _day([99.0, 98.5])}.get(symbol) or _day([100.0, 100.0])

    def svg(name, code, day, peers, peers_label="同市場", reason=""):
        seen.update(name=name, code=code, label=peers_label, reason=reason,
                    peers=[(n, round(p, 2)) for n, p in peers])
        return "<svg/>"
    monkeypatch.setattr(og_router.yahoo_chart, "intraday", intraday)
    monkeypatch.setattr(og_router, "intraday_card_svg", svg)
    monkeypatch.setattr(og_router, "svg_to_png", lambda s, w, h: b"png")
    await og_router.market_card_raster("2330_TW", until=None, reason="主因法說會下修毛利率")
    assert seen == {"name": "台積電", "code": "2330", "label": "大盤", "reason": "主因法說會下修毛利率",
                    "peers": [("加權指數", -1.5)]}


@pytest.mark.asyncio
async def test_preview_drafts_without_posting(temp_db, monkeypatch):
    fake = _wire(monkeypatch, {"^TWII": _day([100.3] * 31), "^TWOII": _day([100.1] * 31)})
    now = datetime.fromtimestamp(OPEN + 1830, timezone.utc)
    quiet = await mm.preview("tw", now=now)
    assert quiet["draft"] is None and quiet["in_window"] and quiet["rows"][0]["big"] is False
    forced = await mm.preview("TW", force=True, now=now)
    assert forced["draft"]["text"].startswith("台股加權指數盤中") and fake.posts == []
    with pytest.raises(KeyError):
        await mm.preview("XX", now=now)
    giants = await mm.preview("TW", lane="stock", force=True, now=now)
    assert giants["lane"] == "stock" and giants["draft"] is None   # no stock data wired → nothing to force


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

    def svg(name, code, day, peers, **_):
        seen.update(name=name, last=day.last, peers=peers)
        return "<svg/>"
    monkeypatch.setattr(og_router.yahoo_chart, "intraday", intraday)
    monkeypatch.setattr(og_router, "intraday_card_svg", svg)
    monkeypatch.setattr(og_router, "svg_to_png", lambda s, w, h: b"png")

    resp = await og_router.market_card_raster("TWII", until=OPEN + 60, reason="")
    assert resp.body == b"png" and resp.headers["cache-control"] == "public, max-age=86400"
    assert seen == {"name": "加權指數", "last": 102.0, "peers": []}
    with pytest.raises(HTTPException) as e:
        await og_router.market_card_raster("NOPE", until=None, reason="")
    assert e.value.status_code == 404


# ── watchlist ───────────────────────────────────────────────────────────────

def test_watchlist_is_the_weight_leaders_without_the_utility():
    tw = {i.code for i in mm.MARKETS["TW"].stocks}
    us = {i.code for i in mm.MARKETS["US"].stocks}
    assert "2412" not in tw and {"2330", "2454", "2308", "2317", "3711", "2383"} <= tw
    assert {"NVDA", "AAPL", "GOOGL", "MSFT", "AMZN", "TSM"} <= us
    assert len(mm.BY_ID) == sum(len(m.indices) + len(m.stocks) for m in mm.MARKETS.values())  # ids unique


# ── batch quotes ────────────────────────────────────────────────────────────

def test_parse_spark_reads_both_shapes_and_skips_empty_symbols():
    flat = {"NVDA": {"symbol": "NVDA", "timestamp": [1, 2], "close": [100.0, None], "chartPreviousClose": 95.0},
            "EMPTY": {"symbol": "EMPTY", "timestamp": [], "close": [], "chartPreviousClose": 10.0}}
    out = yahoo_chart.parse_spark(flat)
    assert list(out) == ["NVDA"] and out["NVDA"].last == 100.0 and round(out["NVDA"].pct, 2) == 5.26
    nested = {"spark": {"result": [{"symbol": "2330.TW", "response": [{
        "meta": {"symbol": "2330.TW", "previousClose": 1000.0}, "timestamp": [5],
        "indicators": {"quote": [{"close": [960.0]}]}}]}], "error": None}}
    q = yahoo_chart.parse_spark(nested)["2330.TW"]
    assert (q.prev_close, q.last, q.last_ts, round(q.pct, 1)) == (1000.0, 960.0, 5, -4.0)
    assert yahoo_chart.parse_spark([]) == {}


@pytest.mark.asyncio
async def test_quotes_batches_twenty_and_a_failed_batch_only_drops_itself(monkeypatch):
    calls = []

    async def get_json(url, params, retries=2):
        assert retries == 0                                          # a batch is never retried
        syms = params["symbols"].split(",")
        calls.append(len(syms))
        if len(calls) == 2:
            raise YahooChartError("429")
        return {s: {"timestamp": [1], "close": [11.0], "chartPreviousClose": 10.0} for s in syms}

    async def no_cache(*_a, **_k):
        return None
    monkeypatch.setattr(yahoo_chart, "_get_json", get_json)
    monkeypatch.setattr(yahoo_chart, "cache_get", no_cache)
    monkeypatch.setattr(yahoo_chart, "cache_set", no_cache)
    out = await yahoo_chart.quotes([f"S{i}" for i in range(45)])
    assert sorted(calls) == [5, 20, 20] and len(out) == 25


# ── the theme lane ──────────────────────────────────────────────────────────

def _basket(n=5, eid="theme_cooling", name="散熱"):
    codes = [("3017", "奇鋐"), ("3324", "雙鴻"), ("3653", "健策"), ("2421", "建準"), ("3483", "力致"), ("3338", "泰碩")]
    return mm.Basket(eid, name, [mm.Instrument(f"{c}.TW", nm) for c, nm in codes[:n]])


def _q(basket, pcts, ts=OPEN + 1800):
    return {m.symbol: Quote(m.symbol, 100.0, 100.0 + p, ts) for m, p in zip(basket.members, pcts)}


def test_a_theme_moves_on_its_median_with_most_members_agreeing():
    b = _basket()
    move = mm.theme_move(b, _q(b, [9.9, 6.0, 4.0, 3.5, -0.5]), floor_pct=3.0)
    assert move and move.median == 4.0 and [i.name for i in move.leaders] == ["奇鋐", "雙鴻"]
    assert mm.theme_move(b, _q(b, [9.9, 9.8, 1.0, 0.5, 0.2]), floor_pct=3.0) is None    # two names, not a theme
    assert mm.theme_move(b, _q(b, [6.0, 5.0, 4.0, -3.0, -4.0]), floor_pct=3.0) is None  # members disagree
    assert mm.theme_move(_basket(2), _q(_basket(2), [9.0, 9.0]), floor_pct=3.0) is None  # too few members
    down = mm.theme_move(b, _q(b, [-7.0, -5.0, -4.0, -3.2, -1.0]), floor_pct=3.0)
    assert down.median == -4.0 and down.leaders[0].name == "奇鋐"                      # biggest drop leads


def test_theme_post_names_the_theme_and_who_led_it():
    b = _basket()
    move = mm.theme_move(b, _q(b, [9.9, 6.0, 4.0, 3.5, -0.5]), floor_pct=3.0)
    assert mm.compose_theme_text(move, "主因輝達上修散熱規格") == "散熱族群盤中急漲，奇鋐、雙鴻領漲，主因輝達上修散熱規格。"
    down = mm.theme_move(b, _q(b, [-7.0, -5.0, -2.5, -2.2, -1.0]), floor_pct=2.0)
    assert mm.compose_theme_text(down, "") == "散熱族群盤中大跌，奇鋐、雙鴻領跌。"


def test_theme_card_payload_round_trips_and_rejects_junk():
    b = _basket()
    move = mm.theme_move(b, _q(b, [9.9, 6.0, 4.0, 3.5, -0.5]), floor_pct=3.0)
    d = mm.decode_theme_card(mm.encode_theme_card(mm.MARKETS["TW"], move, "主因輝達上修散熱規格"))
    assert (d["name"], d["tz"], d["median"], d["reason"]) == ("散熱", "Asia/Taipei", 4.0, "主因輝達上修散熱規格")
    assert d["rows"][0] == ("奇鋐", "3017", 9.9)
    for junk in ("abc", mm.encode_theme_card(mm.MARKETS["TW"], move)[:-6] + "zzzzzz"):
        with pytest.raises(ValueError):
            mm.decode_theme_card(junk)


def test_theme_card_draws_one_bar_per_member_and_the_reason_under_the_median():
    from src.services.intraday_card import theme_card_svg
    rows = [("奇鋐", "3017", 9.9), ("泰碩", "3338", -0.5)]
    svg = theme_card_svg("散熱", rows, 4.0, OPEN + 1800, "Asia/Taipei", reason="市場推測與輝達上修散熱規格有關")
    assert svg.count('rx="4"') == 2 and "散熱" in svg and "+9.90%" in svg and "-0.50%" in svg
    assert "中位數 +4.00%" in svg and "市場推測與輝達上修散熱規格有關" in svg and "檔同向" not in svg
    assert "台北時間" in svg and "TinBoker 題材" in svg
    assert "市場推測" not in theme_card_svg("散熱", rows, 4.0, OPEN + 1800, "Asia/Taipei")   # no reason, no line
    with pytest.raises(ValueError):
        theme_card_svg("散熱", [], 0, OPEN, "Asia/Taipei")


@pytest.mark.asyncio
async def test_a_theme_morning_posts_once_with_its_bar_card_and_scans_every_five_minutes(temp_db, monkeypatch):
    b = _basket()
    fake = _wire(monkeypatch, FLAT)
    scans = []

    async def baskets(market, now):
        scans.append(now)
        return [b] if market.id == "TW" else []

    async def quotes(symbols):
        return {**_q(b, [9.9, 6.0, 4.0, 3.5, -0.5]),
                **{s: Quote(s, d.prev_close, d.last, d.last_ts) for s, d in FLAT.items()}}
    monkeypatch.setattr(mm, "baskets", baskets)
    monkeypatch.setattr(mm.yahoo_chart, "quotes", quotes)

    assert await mm.publish_due(_tick(0)) == 1
    text, image = fake.posts[0]
    assert text == "散熱族群盤中急漲，奇鋐、雙鴻領漲，市場推測與美債殖利率走升有關。"
    assert image.startswith("https://api.tinboker.com/api/og/market-theme/") and image.endswith(".png")
    payload = image.rsplit("/", 1)[-1][:-len(".png")]
    assert mm.decode_theme_card(payload)["reason"] == "市場推測與美債殖利率走升有關"   # the card says what the post says
    row = social_ledger.list_posted("threads")[0]
    assert (row["episode_id"], row["subject"]) == ("market_move:theme:TW:2026-10-14:theme_cooling", "theme_cooling")

    other = _basket(eid="theme_other", name="其他")
    monkeypatch.setattr(mm, "baskets", lambda market, now: _async([b, other]))
    monkeypatch.setattr(mm, "_theme_scanned_at", {})
    assert await mm.publish_due(_tick(6)) == 0                       # daily theme budget (1) spent
    assert len(scans) == 1


@pytest.mark.asyncio
async def test_theme_scan_waits_five_minutes_between_looks(temp_db, monkeypatch):
    _wire(monkeypatch, FLAT)
    looks = []

    async def baskets(market, now):
        looks.append(now)
        return []
    monkeypatch.setattr(mm, "baskets", baskets)
    for m in (0, 1, 4, 5, 6):
        await mm.publish_due(_tick(m))
    assert [int((t - _tick(0)).total_seconds() // 60) for t in looks] == [0, 5]


def _async(value):
    async def f():
        return value
    return f()


def test_tw_venue_comes_from_the_warmed_bars(temp_db):
    from src.database import postgres as pg
    from src.database.models import StockDailyOHLC
    from src.database.postgres import get_session
    StockDailyOHLC.__table__.create(bind=pg.engine, checkfirst=True)
    for db in get_session():
        db.add_all([StockDailyOHLC(ticker="3324", date="2026-10-13", close=1.0, source="tpex"),
                    StockDailyOHLC(ticker="3017", date="2026-10-13", close=1.0, source="twse"),
                    StockDailyOHLC(ticker="6488", date="2026-10-01", close=1.0, source="twse"),
                    StockDailyOHLC(ticker="6488", date="2026-10-13", close=1.0, source="tpex")])
        db.commit()
    assert mm._tw_suffixes(["3324", "3017", "6488", "9999"]) == \
        {"3324": ".TWO", "3017": ".TW", "6488": ".TWO", "9999": ".TW"}


def test_baskets_come_from_registry_themes_split_by_market(monkeypatch):
    from src.services.podcast import PodcastService
    idx = {"meta": {"theme_ai": {"display_name": "AI伺服器", "exposure_type": "theme"},
                    "ind_semi": {"display_name": "半導體", "exposure_type": "industry"}},
           "members": {"theme_ai": [{"ticker": t, "name": n} for t, n in
                                    [("2382", "廣達"), ("3231", "緯創"), ("6669", "緯穎"), ("NVDA", "輝達"),
                                     ("SMCI", "美超微"), ("DELL", "戴爾"), ("8210", "勤誠")]],
                       "ind_semi": [{"ticker": "2330", "name": "台積電"}, {"ticker": "2303", "name": "聯電"},
                                    {"ticker": "2454", "name": "聯發科"}]}}
    monkeypatch.setattr(PodcastService, "_sector_membership_index", staticmethod(lambda: idx))
    monkeypatch.setattr(mm, "_tw_suffixes", lambda codes: {c: (".TWO" if c == "8210" else ".TW") for c in codes})
    out = mm._load_baskets()
    assert [b.exposure_id for b in out["TW"]] == ["theme_ai"]       # industries are not baskets
    assert [m.symbol for m in out["TW"][0].members] == ["2382.TW", "3231.TW", "6669.TW", "8210.TWO"]
    assert [m.symbol for m in out["US"][0].members] == ["NVDA", "SMCI", "DELL"]
    assert out["TW"][0].name == "AI伺服器"


@pytest.mark.asyncio
async def test_worker_loop_is_idle_when_off_and_survives_a_bad_tick(monkeypatch):
    ticks = []

    async def due(now=None):
        ticks.append(1)
        raise RuntimeError("yahoo down")

    class Stop(Exception):
        pass
    sleeps = []

    async def sleep(_s):
        sleeps.append(1)
        if len(sleeps) == 2:
            raise Stop
    monkeypatch.setattr(mm, "publish_due", due)
    monkeypatch.setattr(mm.asyncio, "sleep", sleep)
    monkeypatch.setattr(mm.settings, "market_move_markets", "")
    with pytest.raises(Stop):
        await mm.run_periodic()
    assert ticks == []                                              # off: never touches Yahoo
    sleeps.clear()
    monkeypatch.setattr(mm.settings, "market_move_markets", "TW")
    with pytest.raises(Stop):
        await mm.run_periodic()
    assert ticks == [1, 1]                                          # a failing tick does not end the loop


# ── failure alerts ──────────────────────────────────────────────────────────

def test_admins_are_told_once_per_outage_and_once_on_recovery(monkeypatch):
    sent = []
    monkeypatch.setattr(mm, "_notify_admins", lambda title, body: sent.append((title, body)) or 1)
    monkeypatch.setattr(mm, "_health", {"fails": 0, "alerted": False, "last": ""})
    for _ in range(mm.ALERT_AFTER - 1):
        assert mm.track_health(["Yahoo 指數報價全部失敗（TW）：HTTP 429"], active=True) is None
    assert mm.track_health(["Yahoo 指數報價全部失敗（TW）：HTTP 429"], active=True) == "failing"
    assert sent[0][0] == "盤中速報連續失敗" and "連續 5 分鐘" in sent[0][1] and "HTTP 429" in sent[0][1]
    for _ in range(10):
        mm.track_health(["still down"], active=True)
    assert len(sent) == 1                                            # one alert per outage, not per minute
    assert mm.track_health(["x"], active=False) is None              # outside every window: no evidence
    assert mm.track_health([], active=True) == "recovered" and sent[1][0] == "盤中速報已恢復"
    assert mm.track_health([], active=True) is None and len(sent) == 2


def test_a_blip_shorter_than_the_threshold_is_forgotten(monkeypatch):
    sent = []
    monkeypatch.setattr(mm, "_notify_admins", lambda title, body: sent.append(title) or 1)
    monkeypatch.setattr(mm, "_health", {"fails": 0, "alerted": False, "last": ""})
    for _ in range(mm.ALERT_AFTER - 1):
        mm.track_health(["blip"], active=True)
    mm.track_health([], active=True)
    for _ in range(mm.ALERT_AFTER - 1):
        mm.track_health(["blip"], active=True)
    assert sent == []


@pytest.mark.asyncio
async def test_yahoo_down_for_every_index_and_a_failed_publish_are_problems(temp_db, monkeypatch):
    from src.services.threads_service import ThreadsError
    _wire(monkeypatch, {})                                           # every symbol raises YahooChartError
    await mm.publish_due(_tick(0))
    assert any(p.startswith("Yahoo 指數報價全部失敗（TW）") for p in mm._problems)

    fake = _wire(monkeypatch, {"^TWII": _day([97.0] * 31), "^TWOII": _day([98.0] * 31)})

    async def boom(text, image_url=None):
        raise ThreadsError("token expired")
    monkeypatch.setattr(fake, "publish", boom)
    await mm.publish_due(_tick(0))
    assert any(p.startswith("Threads 發文失敗") and "token expired" in p for p in mm._problems)

    _wire(monkeypatch, {"^TWII": _day([100.2] * 31), "^TWOII": _day([100.1] * 31)})
    await mm.publish_due(_tick(30))
    assert mm._problems == []                                        # a quiet, healthy tick is not a failure


def test_alert_lands_in_every_admin_bell(temp_db, monkeypatch):
    from src.database import postgres as pg
    from src.database.models import User, UserNotification
    from src.database.postgres import session_scope
    for table in (User.__table__, UserNotification.__table__):
        table.create(bind=pg.engine, checkfirst=True)
    monkeypatch.setattr(mm.settings, "admin_emails", ["Boss@Example.com"])
    with session_scope() as db:
        db.add_all([User(id="u1", google_id="g1", email="boss@example.com"),
                    User(id="u2", google_id="g2", email="reader@example.com")])
    assert mm._notify_admins("盤中速報連續失敗", "Yahoo 掛了") == 1
    with session_scope() as db:
        rows = [(n.user_id, n.type, n.title) for n in db.query(UserNotification).all()]
    assert rows == [("u1", "system_alert", "盤中速報連續失敗")]



@pytest.mark.asyncio
async def test_quotes_drop_batches_that_miss_the_budget(monkeypatch):
    import asyncio

    async def get_json(url, params, retries=2):
        syms = params["symbols"].split(",")
        if syms[0] == "S20":                                          # the second batch hangs
            await asyncio.sleep(5)
        return {s: {"timestamp": [1], "close": [11.0], "chartPreviousClose": 10.0} for s in syms}

    async def no_cache(*_a, **_k):
        return None
    monkeypatch.setattr(yahoo_chart, "_get_json", get_json)
    monkeypatch.setattr(yahoo_chart, "cache_get", no_cache)
    monkeypatch.setattr(yahoo_chart, "cache_set", no_cache)
    out = await yahoo_chart.quotes([f"S{i}" for i in range(45)], budget=0.2)
    assert len(out) == 25 and "S20" not in out and "S40" in out    # one slow batch, not the scan


@pytest.mark.asyncio
async def test_scan_fetches_instruments_concurrently(monkeypatch):
    import asyncio
    import time
    us = mm.MARKETS["US"]

    async def intraday(symbol):
        await asyncio.sleep(0.2)
        return _day([100.1] * 3, symbol=symbol, tz="America/New_York")

    async def sigma(symbol):
        return 1.0
    monkeypatch.setattr(mm.yahoo_chart, "intraday", intraday)
    monkeypatch.setattr(mm.yahoo_chart, "sigma", sigma)
    t0 = time.monotonic()
    out = await mm.scan(us.indices, datetime.fromtimestamp(OPEN, ZoneInfo("America/New_York")).date(),
                        datetime.fromtimestamp(OPEN + 300, timezone.utc), 1.0)
    assert time.monotonic() - t0 < 0.6                              # four indices, not 4 x 0.2s
    assert [r["id"] for r in out["rows"]] == [i.id for i in us.indices]



class _Resp:
    def __init__(self, status, body=None):
        self.status_code, self._body = status, body or {}

    def json(self):
        return self._body


def _session(responses, seen):
    class Session:
        def __init__(self, **kw):
            seen.append(kw)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_a):
            return False

        async def get(self, url, params=None):
            r = responses.pop(0)
            if isinstance(r, Exception):
                raise r
            return r
    return Session


@pytest.mark.asyncio
async def test_yahoo_requests_impersonate_a_browser_and_retry_a_429(monkeypatch):
    seen = []
    monkeypatch.setattr(yahoo_chart, "AsyncSession", _session([_Resp(429), _Resp(200, {"ok": 1})], seen))

    async def no_sleep(_s):
        return None
    monkeypatch.setattr(yahoo_chart.asyncio, "sleep", no_sleep)
    assert await yahoo_chart._get_json("https://y/chart", {}) == {"ok": 1}
    assert [kw["impersonate"] for kw in seen] == ["chrome", "chrome"]


@pytest.mark.asyncio
async def test_yahoo_network_errors_and_hard_statuses_become_yahoo_errors(monkeypatch):
    from curl_cffi.requests.exceptions import RequestException

    async def no_sleep(_s):
        return None
    monkeypatch.setattr(yahoo_chart.asyncio, "sleep", no_sleep)
    monkeypatch.setattr(yahoo_chart, "AsyncSession", _session([RequestException("reset")], []))
    with pytest.raises(YahooChartError, match="RequestException"):
        await yahoo_chart._get_json("https://y/chart", {}, retries=0)
    responses = [_Resp(404), _Resp(200)]
    monkeypatch.setattr(yahoo_chart, "AsyncSession", _session(responses, []))
    with pytest.raises(YahooChartError, match="HTTP 404"):
        await yahoo_chart._get_json("https://y/chart", {})
    assert len(responses) == 1                                       # a 404 is not retried



# ── local-language headlines ────────────────────────────────────────────────

RSS = """<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>
<item><title>台股重挫逾400點 美債殖利率飆升</title><link>https://news.cnyes.com/a/1</link>
<pubDate>Thu, 15 Oct 2026 01:40:00 GMT</pubDate></item>
<item><title>no date</title><link>https://x/2</link></item>
<item><title></title><link>https://x/3</link><pubDate>Thu, 15 Oct 2026 01:40:00 GMT</pubDate></item>
</channel></rss>"""


def test_parse_rss_keeps_dated_titled_items():
    from src.services.market_news import parse_rss
    out = parse_rss(RSS, "鉅亨網")
    assert out == [{"title": "台股重挫逾400點 美債殖利率飆升", "publisher": "鉅亨網",
                    "url": "https://news.cnyes.com/a/1", "published": 1792028400}]
    assert parse_rss("<not xml", "x") == []


@pytest.mark.asyncio
async def test_tw_reason_reads_the_local_wires_even_when_yahoo_search_fails(monkeypatch):
    from src.services import market_news
    monkeypatch.setattr(mm.settings, "openrouter_api_key", "k")
    t = int(NOW.timestamp()) - 600

    async def wires(market_id):
        assert market_id == "TW"
        return [{"title": "台股重挫 美債殖利率飆升", "publisher": "鉅亨網", "url": "https://c/1", "published": t},
                {"title": "殖利率急升 台股失守", "publisher": "經濟日報", "url": "https://u/1", "published": t - 60}]

    async def yahoo_down(q, count=12):
        raise YahooChartError("429")
    seen = {}

    async def extract(market, subject, headlines):
        seen["publishers"] = [h["publisher"] for h in headlines]
        return {"cause": "美債殖利率飆升", "support": [0, 1]}
    monkeypatch.setattr(market_news, "headlines", wires)
    monkeypatch.setattr(mm.yahoo_chart, "news", yahoo_down)
    monkeypatch.setattr(mm, "_extract_cause", extract)
    lead = mm.Move(mm.Instrument("^TWII", "加權指數"), _day([97.0]), 1.0)
    out = await mm.find_cause(mm.MARKETS["TW"], mm.subject_of(mm.MARKETS["TW"], lead), NOW)
    assert seen["publishers"] == ["鉅亨網", "經濟日報"]                 # newest first
    assert (out["tier"], out["clause"]) == ("consensus", "主因美債殖利率飆升")   # two wires agree


def test_tw_index_lane_is_the_taiex_alone():
    assert [i.symbol for i in mm.MARKETS["TW"].indices] == ["^TWII"]    # ^TWOII is a Yahoo 404
