"""Unit tests for ``pipeline.steps.postgres_episode.mirror_episode_to_postgres``
(P2 review follow-up MUST-FIX #2): the mirror is the P2 dedup authority and the
backend notification producer's high-water mark, so it must FAIL LOUDLY
(missing ``EPISODE_DATABASE_URL`` or a write error raises, not a silent
best-effort skip) and must never let a re-ingest advance ``created_time``
(contract § 2.1: immutable after first write) and re-fire notifications.

Fake psycopg connection/cursor, same idiom as
``test_ticker_insights_export_step.py``.
"""

from __future__ import annotations

import psycopg
import pytest
from src.pipeline.steps.postgres_episode import _UPSERT, mirror_episode_to_postgres


class _FakeCursor:
    def __init__(self):
        self.executed: list[tuple[str, tuple]] = []

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


class _Config:
    rerun_from = None


class _Episode:
    podcast_name = "Show"
    episode_number = 1
    episode_title = "EP1"
    created_time = "2026-01-01T00:00:00Z"
    num_likes = 3
    number_click = 5
    related_tickers = ["2330"]

    def to_firestore_dict(self):
        return {"episode_title": "EP1"}


class _FB:
    def _generate_episode_id(self, podcast_name, episode):
        return "ep_1"


class _Services:
    firebase_service = _FB()


class _EpisodeData:
    episode = _Episode()
    podcast_name = "Show"


# --- fails loudly, no best-effort silent skip --------------------------------


def test_raises_without_episode_database_url(monkeypatch):
    monkeypatch.delenv("EPISODE_DATABASE_URL", raising=False)

    def _must_not_connect(*a, **k):
        raise AssertionError("must not connect without EPISODE_DATABASE_URL")

    monkeypatch.setattr(psycopg, "connect", _must_not_connect)

    with pytest.raises(RuntimeError, match="EPISODE_DATABASE_URL"):
        mirror_episode_to_postgres(_Config(), _Services(), _EpisodeData())


def test_write_failure_propagates_instead_of_being_swallowed(monkeypatch):
    monkeypatch.setenv("EPISODE_DATABASE_URL", "postgresql://x/y")

    def _boom(*a, **k):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(psycopg, "connect", _boom)

    with pytest.raises(RuntimeError, match="connection refused"):
        mirror_episode_to_postgres(_Config(), _Services(), _EpisodeData())


# --- created_time immutable on conflict --------------------------------------


def test_upsert_sql_excludes_created_time_from_conflict_update():
    """Static guard on the shared SQL: a re-ingest's ON CONFLICT branch must
    never touch created_time, even if a future edit adds columns nearby."""
    _, update_clause = _UPSERT.split("DO UPDATE SET", 1)
    assert "created_time" not in update_clause
    # sanity: it IS still written on first insert (the INSERT column list)
    assert "created_time" in _UPSERT.split("DO UPDATE SET", 1)[0]


def test_mirror_write_omits_created_time_from_conflict_clause(monkeypatch):
    monkeypatch.setenv("EPISODE_DATABASE_URL", "postgresql://x/y")
    cur = _FakeCursor()
    monkeypatch.setattr(psycopg, "connect", lambda *a, **k: _FakeConn(cur))

    mirror_episode_to_postgres(_Config(), _Services(), _EpisodeData())

    upserts = [(sql, params) for sql, params in cur.executed if "INSERT INTO" in sql]
    assert len(upserts) == 1
    sql, params = upserts[0]
    assert "created_time" not in sql.split("DO UPDATE SET", 1)[1]
    # still supplied for the first-insert case (5th positional column)
    assert params[0] == "ep_1"
