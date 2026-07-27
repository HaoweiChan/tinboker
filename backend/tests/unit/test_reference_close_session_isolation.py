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

import src.routers.stock as stock


class _Row:
    def __init__(self, close):
        self.close = close


def _install_fake_sessions(monkeypatch, close=123.0, delay=0.0):
    """Replace get_session with a generator handing out a fresh recording session.

    Returns (sessions, touches) where touches is a list of (session_id, thread_id).
    """
    sessions = []
    touches = []
    lock = threading.Lock()

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
            chain.first = lambda: _Row(close) if close is not None else None
            return chain

        session.query = query
        sessions.append(session)
        yield session

    monkeypatch.setattr(stock, "get_session", fake_get_session)
    return sessions, touches


def test_each_concurrent_call_gets_its_own_session(monkeypatch):
    sessions, touches = _install_fake_sessions(monkeypatch, delay=0.05)

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
    """A slow DB read must not stall other tasks — that was the original outage."""
    _install_fake_sessions(monkeypatch, delay=0.3)

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

    close is NOT NULL in the model, so "no row" and "no price" are the same None.
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
