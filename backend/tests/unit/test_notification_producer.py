"""Self-check for the notification producer's first_seen_at watermark + cold-start guard."""
import asyncio
import datetime as dt
from types import SimpleNamespace

import src.services.notification_producer as prod


def _ts(n):
    return dt.datetime(2026, 8, 1, tzinfo=dt.timezone.utc) + dt.timedelta(minutes=n)


def _row(n, **doc):
    d = {"podcast_name": "P", "episode_title": f"t{n}", "summary_content": "s",
         "related_tickers": [], "tags": [], **doc}
    return (f"ep{n}", _ts(n), d)


async def _no_allowlist():
    return None


def _wire(rows):
    """Fake Redis marker + fake mirror query; return (store, notified ids)."""
    store = {}
    notified = []

    async def fake_get(k):
        return store.get(k)

    async def fake_set(k, v, ttl=300):
        store[k] = v
        return True

    def fake_fetch(mark):
        if mark is None:
            return (rows[-1][1] if rows else None), []
        newer = [r for r in rows if r[1].isoformat() > mark]
        return (newer[-1][1] if newer else None), newer

    def fake_notify(eps):
        notified.extend(e["id"] for e in eps)
        return len(eps)

    prod.settings = SimpleNamespace(use_postgres=True)
    prod.cache_get = fake_get
    prod.cache_set = fake_set
    prod._fetch_new_rows = fake_fetch
    prod._notify_for_episodes = fake_notify
    prod._podcast_service = SimpleNamespace(
        _allowed_podcast_names=_no_allowlist,
        _recency_cutoff_ms=lambda: None,
        _dict_release_ms=lambda d: 0,
    )
    return store, notified


def _refeed(rows):
    """Swap the fake mirror contents between cycles."""
    def fake_fetch(mark):
        newer = [r for r in rows if mark is None or r[1].isoformat() > mark]
        return (newer[-1][1] if newer else None), ([] if mark is None else newer)
    prod._fetch_new_rows = fake_fetch


def test_cold_start_sends_nothing_but_sets_marker():
    store, notified = _wire([_row(1), _row(2)])
    sent = asyncio.run(prod.scan_and_notify())
    assert sent == 0
    assert notified == []                                   # backlog not blasted
    assert store[prod._MARKER_KEY] == _ts(2).isoformat()    # marker = max first_seen_at


def test_only_rows_above_marker_notified():
    store, notified = _wire([_row(1), _row(2)])
    asyncio.run(prod.scan_and_notify())                     # cold start -> marker at ts(2)
    # Late ingest: ep3 is first-seen now even though its publish date is ancient —
    # the watermark orders on first_seen_at, so it still notifies.
    _refeed([_row(1), _row(2), _row(3, created_time="2020-01-01T00:00:00+00:00")])
    asyncio.run(prod.scan_and_notify())
    assert notified == ["ep3"]
    assert store[prod._MARKER_KEY] == _ts(3).isoformat()


def test_content_empty_row_skipped_but_marker_advances():
    store, notified = _wire([_row(1)])
    asyncio.run(prod.scan_and_notify())                     # cold start -> marker at ts(1)
    _refeed([_row(1), _row(2, summary_content=""), _row(3)])
    asyncio.run(prod.scan_and_notify())
    assert notified == ["ep3"]                              # placeholder ep2 not notified
    assert store[prod._MARKER_KEY] == _ts(3).isoformat()    # but never re-scanned either


if __name__ == "__main__":
    test_cold_start_sends_nothing_but_sets_marker()
    test_only_rows_above_marker_notified()
    test_content_empty_row_skipped_but_marker_advances()
    print("ok")
