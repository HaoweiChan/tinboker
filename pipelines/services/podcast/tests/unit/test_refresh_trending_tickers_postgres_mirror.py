"""Unit tests for ``scripts/refresh_trending_tickers.py``.

Since P4 both ends are Postgres: the hourly refresh reads every
``firestore_mirror.ticker_insights`` doc, then upserts the recomputed rows into
``firestore_mirror.trending_tickers`` AND prunes tickers that fell out of the
full recompute. It is the only writer, so failures must surface (red systemd
unit) rather than leave a frozen table behind a warning.
"""

from __future__ import annotations

import psycopg
import pytest
from scripts.refresh_trending_tickers import _read_all_insights, _write_trending_to_postgres


class _FakeCursor:
    def __init__(self, rowcount: int = 0, rows: list | None = None):
        self.executed: list[tuple[str, tuple]] = []
        self.rowcount = rowcount
        self._rows = rows or []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchall(self):
        return self._rows

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _FakeConn:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_raises_without_episode_database_url(monkeypatch):
    monkeypatch.delenv("EPISODE_DATABASE_URL", raising=False)

    def _must_not_connect(*a, **k):
        raise AssertionError("must not connect without EPISODE_DATABASE_URL")

    monkeypatch.setattr(psycopg, "connect", _must_not_connect)

    with pytest.raises(RuntimeError, match="EPISODE_DATABASE_URL"):
        _write_trending_to_postgres({"2330": {"ticker": "2330"}})


def test_skips_and_never_prunes_when_docs_empty(monkeypatch):
    """Guards against wiping the whole table: an empty recompute must not connect
    (and therefore never issue the 'delete everything not in []' prune)."""
    monkeypatch.setenv("EPISODE_DATABASE_URL", "postgresql://x/y")

    def _must_not_connect(*a, **k):
        raise AssertionError("must not connect with no docs to write")

    monkeypatch.setattr(psycopg, "connect", _must_not_connect)

    _write_trending_to_postgres({})


def test_upserts_all_and_prunes_using_the_recomputed_keys(monkeypatch):
    monkeypatch.setenv("EPISODE_DATABASE_URL", "postgresql://x/y")
    cur = _FakeCursor(rowcount=2)
    monkeypatch.setattr(psycopg, "connect", lambda *a, **k: _FakeConn(cur))

    docs = {
        "2330": {"ticker": "2330", "count_all_time": 5},
        "NVDA": {"ticker": "NVDA", "count_all_time": 3},
    }
    _write_trending_to_postgres(docs)

    assert any("CREATE TABLE" in sql for sql, _ in cur.executed)
    upserts = [params for sql, params in cur.executed if "INSERT INTO" in sql]
    assert {p[0] for p in upserts} == {"2330", "NVDA"}

    deletes = [params for sql, params in cur.executed if "DELETE FROM" in sql]
    assert len(deletes) == 1
    (keep,) = deletes[0]
    assert set(keep) == {"2330", "NVDA"}


def test_write_failure_propagates(monkeypatch):
    """Sole write since P4 — swallowing a Postgres outage would silently serve a
    stale trending table for hours."""
    monkeypatch.setenv("EPISODE_DATABASE_URL", "postgresql://x/y")

    def _boom(*a, **k):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(psycopg, "connect", _boom)

    with pytest.raises(RuntimeError, match="connection refused"):
        _write_trending_to_postgres({"2330": {"ticker": "2330"}})


def test_reads_insight_docs_from_the_mirror_not_firestore(monkeypatch):
    """The aggregation source moved with the writes: ticker_insights are no longer
    in Firestore, so a collection-group stream would aggregate a frozen snapshot."""
    monkeypatch.setenv("EPISODE_DATABASE_URL", "postgresql://x/y")
    rows = [({"ticker": "2330", "sentiment_score": 0.7},), ({"ticker": "NVDA"},), (None,)]
    cur = _FakeCursor(rows=rows)
    monkeypatch.setattr(psycopg, "connect", lambda *a, **k: _FakeConn(cur))

    insights = _read_all_insights()

    assert insights == [{"ticker": "2330", "sentiment_score": 0.7}, {"ticker": "NVDA"}]
    assert any("ticker_insights" in sql for sql, _ in cur.executed)
