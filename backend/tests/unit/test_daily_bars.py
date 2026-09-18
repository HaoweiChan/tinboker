"""Chart bars from Postgres with the upstream filling the tail (services/daily_bars.py).

Background, measured 2026-09-17: a Massive 429 storm after a deploy emptied NVDA's chart
while stock_daily_ohlc held the same year of bars (TW identical to FinMind, US identical to
Massive to the half-cent — except 2026-09-01, stored mid-session for four US tickers)."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlalchemy.dialects import postgresql

from src.services import daily_bars
from src.services.data_collection_service import DataCollectionService
from src.services.massive_service import MassiveAPIError


def _bars(start: str, n: int, close: float = 100.0):
    d0 = datetime.strptime(start, "%Y-%m-%d")
    return [{"date": (d0 + timedelta(days=i)).strftime("%Y-%m-%d"), "open": close, "high": close + 1,
             "low": close - 1, "close": close + i, "volume": 1000} for i in range(n)]


# ── pure planning ──────────────────────────────────────────────────────────

def test_covers_allows_a_holiday_run_at_the_window_start():
    assert daily_bars.covers(_bars("2025-09-24", 3), "2025-09-17")      # 7 days late: covered
    assert not daily_bars.covers(_bars("2025-10-10", 3), "2025-09-17")  # 23 days late: not
    assert not daily_bars.covers([], "2025-09-17")


def test_us_always_refetches_a_two_week_tail_to_heal_intraday_rows():
    stored = _bars("2025-09-17", 355)  # last stored 2026-09-06
    assert daily_bars.fetch_from(stored, "2025-09-17", "2026-09-17", us=True) == "2026-09-03"
    # a store that stopped long ago still resumes from its own last day
    old = _bars("2025-09-17", 300)     # last stored 2026-07-13
    assert daily_bars.fetch_from(old, "2025-09-17", "2026-09-17", us=True) == old[-1]["date"]


def test_tw_only_fetches_what_is_newer_than_the_store():
    stored = _bars("2025-09-17", 364)  # last stored 2026-09-15
    assert daily_bars.fetch_from(stored, "2025-09-17", "2026-09-17", us=False) == "2026-09-15"


def test_without_coverage_the_whole_window_is_fetched():
    assert daily_bars.fetch_from(_bars("2026-06-01", 50), "2025-09-17", "2026-09-17", us=True) == "2025-09-17"


def test_merge_lets_the_upstream_win_shared_dates():
    stored = _bars("2026-09-01", 3, close=10.0)
    fetched = [{**stored[0], "close": 99.0}, {**stored[2], "date": "2026-09-04", "close": 7.0}]
    merged = daily_bars.merge(stored, fetched)
    assert [(b["date"], b["close"]) for b in merged] == [
        ("2026-09-01", 99.0), ("2026-09-02", 11.0), ("2026-09-03", 12.0), ("2026-09-04", 7.0)]


# ── write-back ─────────────────────────────────────────────────────────────

def test_write_back_upserts_closed_sessions_only(monkeypatch):
    executed = []

    class _Db:
        def execute(self, stmt):
            executed.append(stmt)

        def commit(self):
            pass

    monkeypatch.setattr(daily_bars, "get_session", lambda: iter([_Db()]))
    today_ny = datetime.now(timezone.utc).astimezone(daily_bars_ny()).strftime("%Y-%m-%d")
    bars = [{"date": "2026-09-01", "open": 1, "high": 2, "low": 1, "close": 1.5, "volume": 10},
            {"date": "2099-01-01", "open": 1, "high": 2, "low": 1, "close": 1.5, "volume": 10},  # not traded yet
            {"date": today_ny, "open": 1, "high": 2, "low": 1, "close": 1.5, "volume": 10}]
    from src.services.stock_close_refresh import close_is_final

    n = daily_bars.write_bars("NVDA", bars, source="massive")
    compiled = executed[0].compile(dialect=postgresql.dialect())
    sql = str(compiled)
    assert "ON CONFLICT (ticker, date) DO UPDATE" in sql and "trading_value" not in sql.split("DO UPDATE")[1]
    dates = {v for k, v in compiled.params.items() if k.startswith("date")}
    assert "2026-09-01" in dates and "2099-01-01" not in dates
    # today's bar is written only once the 16:00 New York session has closed
    assert (today_ny in dates) == close_is_final("NVDA", today_ny) and n == len(dates)


def daily_bars_ny():
    from zoneinfo import ZoneInfo
    return ZoneInfo("America/New_York")


# ── wiring in DataCollectionService ────────────────────────────────────────

def _service():
    massive, finmind = Mock(), Mock()
    return DataCollectionService(massive_service=massive, finmind_service=finmind), massive, finmind


def _agg(date: str, close: float):
    ts = int(datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=daily_bars_ny()).timestamp() * 1000)
    return SimpleNamespace(timestamp=ts, open=close, high=close, low=close, close=close, volume=5)


def test_us_chart_reads_the_store_and_asks_massive_for_the_tail_only(monkeypatch):
    svc, massive, _ = _service()
    stored = _bars("2025-09-18", 350)  # covers the 1Y window
    monkeypatch.setattr(daily_bars, "read_bars", lambda *a: stored)
    written = []
    monkeypatch.setattr(daily_bars, "write_bars", lambda t, b, source: written.append((t, b, source)))
    massive.client.list_aggs.return_value = [_agg(stored[-1]["date"], 555.0)]

    history = SimpleNamespace(day=[], add_record=lambda r: history.day.append(r))
    svc._fill_us_daily("NVDA", history, "2025-09-17", "2026-09-17", 415)

    kwargs = massive.client.list_aggs.call_args.kwargs
    assert kwargs["from_"] >= "2026-09-01"  # a tail, not the whole year
    assert len(history.day) == 350 and history.day[-1].close == 555.0  # fetched value wins
    assert written and written[0][2] == "massive"


def test_us_chart_survives_a_massive_failure_on_stored_bars(monkeypatch):
    svc, massive, _ = _service()
    monkeypatch.setattr(daily_bars, "read_bars", lambda *a: _bars("2025-09-18", 350))
    monkeypatch.setattr(daily_bars, "write_bars", lambda *a, **k: pytest.fail("nothing to write"))
    massive.client.list_aggs.side_effect = RuntimeError("too many 429 error responses")

    history = SimpleNamespace(day=[], add_record=lambda r: history.day.append(r))
    svc._fill_us_daily("NVDA", history, "2025-09-17", "2026-09-17", 415)
    assert len(history.day) == 350


def test_us_failure_without_stored_coverage_still_raises(monkeypatch):
    svc, massive, _ = _service()
    monkeypatch.setattr(daily_bars, "read_bars", lambda *a: [])
    massive.client.list_aggs.side_effect = RuntimeError("429")
    history = SimpleNamespace(day=[], add_record=lambda r: history.day.append(r))
    with pytest.raises(RuntimeError):
        svc._fill_us_daily("NVDA", history, "2025-09-17", "2026-09-17", 415)


def test_tw_chart_asks_finmind_only_after_the_last_stored_day_and_never_writes(monkeypatch):
    svc, _, finmind = _service()
    stored = _bars("2025-09-18", 350)
    monkeypatch.setattr(daily_bars, "read_bars", lambda *a: stored)
    monkeypatch.setattr(daily_bars, "write_bars", lambda *a, **k: pytest.fail("TW store is fed by TWSE/TPEx"))
    finmind.get_daily_aggregates.return_value = []
    history = SimpleNamespace(day=[], add_record=lambda r: history.day.append(r))
    svc._fetch_finmind_daily_aggregates("2330", history, timeframe="1Y")
    assert finmind.get_daily_aggregates.call_args.kwargs["from_date"] == stored[-1]["date"]
    assert len(history.day) == 350


def test_provider_failure_falls_back_to_stored_bars_flagged_uncacheable(monkeypatch):
    svc, massive, _ = _service()
    massive.get_ticker_details.side_effect = MassiveAPIError("Could not fetch ticker details for NVDA")
    monkeypatch.setattr(daily_bars, "read_bars", lambda *a: _bars("2025-09-18", 250))
    monkeypatch.setattr(daily_bars, "display_name", lambda t: "輝達")
    stock = svc.collect_stock_data("NVDA", timeframe="1Y")
    assert stock and stock.from_stored_bars
    assert stock.metadata.stock_name == "輝達" and len(stock.stock_price_history.day) == 250
    assert stock.price == 100.0 + 249
    # intraday views don't fall back — a year of daily bars is not what they draw
    assert svc.collect_stock_data("NVDA", timeframe="1H") is None


@pytest.mark.asyncio
async def test_stock_service_serves_but_never_caches_a_stored_bar_fallback(monkeypatch):
    from unittest.mock import AsyncMock, patch
    from src.services.stock import StockService

    svc, massive, _ = _service()
    massive.get_ticker_details.side_effect = MassiveAPIError("429")
    # Dated from today backwards: a fixed start date drifts out of the 1Y window the
    # service filters on, and the test started failing on the day it aged past a year.
    recent = (datetime.now() - timedelta(days=249)).strftime("%Y-%m-%d")
    monkeypatch.setattr(daily_bars, "read_bars", lambda *a: _bars(recent, 250))
    monkeypatch.setattr(daily_bars, "display_name", lambda t: None)
    service = StockService(data_collection_service=svc)
    with patch("src.services.stock.cache_get", new_callable=AsyncMock, return_value=None), \
         patch("src.services.stock.cache_set", new_callable=AsyncMock) as cache_set:
        detail = await service.get_stock_info_async("NVDA", timeframe="1Y")
    assert detail is not None and len(detail.chartData) == 250
    cache_set.assert_not_awaited()


# ── one-off repair ─────────────────────────────────────────────────────────

class _FlakyClient:
    """list_aggs that 429s for tickers in ``fail`` (``times`` times each)."""

    def __init__(self, fail=(), times=1):
        self.fail, self.times, self.calls = dict.fromkeys(fail, times), times, []

    def list_aggs(self, ticker, **kw):
        self.calls.append((ticker, kw["from_"], kw["to"]))
        if self.fail.get(ticker, 0) > 0:
            self.fail[ticker] -= 1
            raise RuntimeError("too many 429 error responses")
        return [_agg("2026-07-24", 180.0), _agg("2026-09-01", 459.61)]


@pytest.mark.asyncio
async def test_repair_refetches_every_stored_us_ticker_and_upserts(monkeypatch):
    monkeypatch.setattr(daily_bars, "us_tickers_in_store", lambda: ["AMD", "MSFT", "NVDA"])
    written = []
    monkeypatch.setattr(daily_bars, "write_bars", lambda t, b, source: written.append((t, [x["date"] for x in b])) or len(b))
    client = _FlakyClient(fail=["MSFT"], times=1)   # one 429, then fine
    state = await daily_bars.repair_us_bars(days=400, gap_seconds=0, backoff_seconds=0, massive=SimpleNamespace(client=client))
    assert state["running"] is False and state["done"] == 3 and state["failed"] == []
    assert [t for t, _ in written] == ["AMD", "MSFT", "NVDA"]
    assert written[0][1] == ["2026-07-24", "2026-09-01"]  # the gap and the intraday row come back
    assert [c[0] for c in client.calls].count("MSFT") == 2  # retried once
    assert state["written"] == 6


@pytest.mark.asyncio
async def test_repair_records_a_ticker_that_fails_twice_and_carries_on(monkeypatch):
    monkeypatch.setattr(daily_bars, "us_tickers_in_store", lambda: ["AMD", "NVDA"])
    monkeypatch.setattr(daily_bars, "write_bars", lambda t, b, source: len(b))
    state = await daily_bars.repair_us_bars(gap_seconds=0, backoff_seconds=0, massive=SimpleNamespace(client=_FlakyClient(fail=["AMD"], times=2)))
    assert state["done"] == 2 and [f["ticker"] for f in state["failed"]] == ["AMD"] and state["written"] == 2


@pytest.mark.asyncio
async def test_repair_endpoint_starts_one_job_only(monkeypatch):
    import asyncio
    from src.routers import admin_stock_bars

    gate = asyncio.Event()
    starts = []

    async def _slow(days):
        starts.append(days)
        await gate.wait()
        return {}

    monkeypatch.setattr(daily_bars, "repair_us_bars", _slow)
    monkeypatch.setattr(admin_stock_bars, "_task", None)
    first = await admin_stock_bars.start_repair(days=400, _=None)
    second = await admin_stock_bars.start_repair(days=400, _=None)
    await asyncio.sleep(0)
    assert first["started"] is True and second["started"] is False and starts == [400]
    gate.set()
    await admin_stock_bars._task
