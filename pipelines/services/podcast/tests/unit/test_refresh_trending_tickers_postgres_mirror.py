"""Unit tests for ``scripts/refresh_trending_tickers.py``'s Postgres dual-write
(``_mirror_trending_to_postgres``) — the live hourly refresh must upsert every
recomputed ticker doc into ``firestore_mirror.trending_tickers`` AND prune rows
whose ticker fell out of this run's full recompute. The Firestore write itself
(``write_trending``) is untouched — these tests only exercise the added mirror.
"""

from __future__ import annotations

import psycopg
from scripts.refresh_trending_tickers import _mirror_trending_to_postgres


class _FakeCursor:
    def __init__(self, rowcount: int = 0):
        self.executed: list[tuple[str, tuple]] = []
        self.rowcount = rowcount

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

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


def test_mirror_skips_without_episode_database_url(monkeypatch):
    monkeypatch.delenv("EPISODE_DATABASE_URL", raising=False)

    def _must_not_connect(*a, **k):
        raise AssertionError("must not connect without EPISODE_DATABASE_URL")

    monkeypatch.setattr(psycopg, "connect", _must_not_connect)

    _mirror_trending_to_postgres({"2330": {"ticker": "2330"}})


def test_mirror_skips_and_never_prunes_when_docs_empty(monkeypatch):
    """Guards against wiping the whole table: an empty recompute must not connect
    (and therefore never issue the 'delete everything not in []' prune)."""
    monkeypatch.setenv("EPISODE_DATABASE_URL", "postgresql://x/y")

    def _must_not_connect(*a, **k):
        raise AssertionError("must not connect with no docs to write")

    monkeypatch.setattr(psycopg, "connect", _must_not_connect)

    _mirror_trending_to_postgres({})


def test_mirror_upserts_all_and_prunes_using_the_recomputed_keys(monkeypatch):
    monkeypatch.setenv("EPISODE_DATABASE_URL", "postgresql://x/y")
    cur = _FakeCursor(rowcount=2)
    monkeypatch.setattr(psycopg, "connect", lambda *a, **k: _FakeConn(cur))

    docs = {
        "2330": {"ticker": "2330", "count_all_time": 5},
        "NVDA": {"ticker": "NVDA", "count_all_time": 3},
    }
    _mirror_trending_to_postgres(docs)

    assert any("CREATE TABLE" in sql for sql, _ in cur.executed)
    upserts = [params for sql, params in cur.executed if "INSERT INTO" in sql]
    assert {p[0] for p in upserts} == {"2330", "NVDA"}

    deletes = [params for sql, params in cur.executed if "DELETE FROM" in sql]
    assert len(deletes) == 1
    (keep,) = deletes[0]
    assert set(keep) == {"2330", "NVDA"}


def test_mirror_swallows_connection_errors(monkeypatch):
    """Best-effort: a Postgres outage must not raise out of the refresh script."""
    monkeypatch.setenv("EPISODE_DATABASE_URL", "postgresql://x/y")

    def _boom(*a, **k):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(psycopg, "connect", _boom)

    _mirror_trending_to_postgres({"2330": {"ticker": "2330"}})  # must not raise
