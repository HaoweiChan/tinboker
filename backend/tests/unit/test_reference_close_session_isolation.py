"""Self-check for _get_reference_close: each concurrent call gets its own DB session.

The three batch-price routes fan this out over up to 300 tickers with
asyncio.gather. It used to take the request-scoped Session and query it inline,
which was only accidentally safe because the blocking call never yielded — the
event loop stalled instead. Offloading to threads without also giving each call
its own session would have swapped an event-loop stall for concurrent use of a
Session, which SQLAlchemy does not support.

These tests pin both halves: own session per call, and no loop blocking.
"""
import asyncio
import threading
import time
from types import SimpleNamespace

import pytest

import src.routers.stock as stock
import src.services.stock_close_refresh as close_refresh


def _install_fake_sessions(monkeypatch, close=123.0, delay=0.0, tickers=("2330.TW",)):
    """Replace get_session (in the module owning the warm-close reader) with a generator
    handing out a fresh recording session.

    Each session answers with two dated closes per ticker, the shape
    ``batch_read_latest_closes`` selects. Returns (sessions, touches) where touches is a
    list of (session_id, thread_id).
    """
    sessions = []
    touches = []
    lock = threading.Lock()
    rows = [] if close is None else [
        row for t in tickers
        for row in ((t, "2026-07-20", 100.0), (t, "2026-07-25", close))
    ]

    def fake_get_session():
        session = SimpleNamespace()
        sid = len(sessions)

        def query(*_a, **_k):
            with lock:
                touches.append((sid, threading.get_ident()))
            if delay:
                time.sleep(delay)
            chain = SimpleNamespace()
            chain.filter = lambda *a, **k: chain
            chain.order_by = lambda *a, **k: chain
            chain.all = lambda: rows
            return chain

        session.query = query
        sessions.append(session)
        yield session

    monkeypatch.setattr(close_refresh, "get_session", fake_get_session)
    return sessions, touches


def test_each_concurrent_call_gets_its_own_session(monkeypatch):
    sessions, touches = _install_fake_sessions(
        monkeypatch, delay=0.05, tickers=[f"T{i}" for i in range(8)]
    )

    async def _run():
        return await asyncio.gather(
            *[stock._get_reference_close(f"T{i}", "2026-07-27") for i in range(8)]
        )

    results = asyncio.run(_run())

    assert results == [123.0] * 8
    assert len(sessions) == 8, "expected one session per call, got %d" % len(sessions)

    # The property that actually matters: no single session was touched by two threads.
    per_session_threads = {}
    for sid, tid in touches:
        per_session_threads.setdefault(sid, set()).add(tid)
    shared = {s: t for s, t in per_session_threads.items() if len(t) > 1}
    assert not shared, f"session(s) used from multiple threads: {shared}"


def test_db_lookup_does_not_block_the_event_loop(monkeypatch):
    """A slow DB read must not stall other tasks — that was the original outage.

    Each call now reads both warm tables (two queries, 0.15 s each = 0.3 s in the thread);
    overlapped with the 0.3 s sleep that's ~0.3 s, while a blocked loop would take 0.6 s.
    """
    _install_fake_sessions(monkeypatch, delay=0.15)

    async def _run():
        start = time.monotonic()
        await asyncio.gather(
            stock._get_reference_close("2330.TW", "2026-07-27"),
            asyncio.sleep(0.3),
        )
        return time.monotonic() - start

    elapsed = asyncio.run(_run())
    assert elapsed < 0.5, f"event loop appears blocked — gather took {elapsed:.2f}s"


def test_miss_falls_through_to_the_cache_layer(monkeypatch):
    """No stored row -> must not short-circuit; it should consult Redis next.

    Rows with a NULL close are filtered out in SQL, so "no row" and "no price" are the
    same empty result.
    """
    _install_fake_sessions(monkeypatch, close=None)

    consulted = []

    async def fake_cache_get(key):
        consulted.append(key)
        return "456.0"

    monkeypatch.setattr(stock, "cache_get", fake_cache_get)

    result = asyncio.run(stock._get_reference_close("2330.TW", "2026-07-27"))

    assert consulted == ["stock:2330.TW:close:2026-07-27"]
    assert result == 456.0


# ── Market routing (step 3): only TW may reach FinMind ────────────────────────

def _stub_finmind(monkeypatch, calls):
    class _FakeFinMind:
        def list_daily_ticker_summary_range(self, ticker, start, end):
            calls.append(ticker)
            return []

    monkeypatch.setattr("src.services.finmind_service.FinMindAPIService", _FakeFinMind)


@pytest.fixture()
def cold(monkeypatch):
    """No warm row, no Redis entry — every lookup falls through to step 3. Returns the
    list of (key, value) pairs written back to Redis."""
    _install_fake_sessions(monkeypatch, close=None)
    written = []

    async def fake_cache_get(_key):
        return None

    async def fake_cache_set(key, value, ttl=0):
        written.append((key, value))
        return True

    monkeypatch.setattr(stock, "cache_get", fake_cache_get)
    monkeypatch.setattr(stock, "cache_set", fake_cache_set)
    return written


def test_tw_class_letter_etf_reaches_finmind(monkeypatch, cold):
    """00878B / 00632R are TW ETFs whose code carries a trailing share-class letter. The
    old `ticker.split(".")[0].isdigit()` check read that letter as a US symbol, so they
    were negative-cached forever and never got a price."""
    calls = []
    _stub_finmind(monkeypatch, calls)

    assert asyncio.run(stock._get_reference_close("00878B", "2026-07-27")) is None
    assert calls == ["00878B"], "TW class-letter ETF must still be routed to FinMind"


def test_six_digit_korean_code_never_reaches_finmind(monkeypatch, cold):
    """005930 (Samsung) is Korean. FinMind serves TW only, so it must stop at the
    negative cache instead of burning the shared hourly budget on a guaranteed miss."""
    calls = []
    _stub_finmind(monkeypatch, calls)

    assert asyncio.run(stock._get_reference_close("005930", "2026-07-27")) is None
    assert calls == [], f"KR code reached FinMind: {calls}"
    assert ("stock:005930:close:2026-07-27", "__null__") in cold
