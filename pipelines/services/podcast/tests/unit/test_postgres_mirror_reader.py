"""Unit tests for ``src.service.postgres_mirror_reader`` — the P2 read-flip that
repoints pipeline Firestore READS (shows list/single, episode dedup lookups,
regen candidate scans) onto ``firestore_mirror`` in Postgres. Firestore WRITES
are untouched; this module and its tests are reads only.

Fake psycopg connection/cursor, same idiom as
``test_ticker_insights_export_step.py`` / ``test_refresh_trending_tickers_postgres_mirror.py``,
extended to return canned SELECT results via fetchone/fetchall.
"""

from __future__ import annotations

import psycopg
import pytest
from src.service import postgres_mirror_reader as reader


class _FakeCursor:
    """Replays canned results for successive ``execute()`` calls, in order."""

    def __init__(self, results: list):
        self._results = list(results)
        self.executed: list[tuple[str, object]] = []
        self._last = None

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        self._last = self._results.pop(0) if self._results else None
        return self

    def fetchone(self):
        return self._last

    def fetchall(self):
        return self._last or []

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


def _connect(monkeypatch, results, *, url="postgresql://x/y"):
    monkeypatch.setenv("EPISODE_DATABASE_URL", url)
    cur = _FakeCursor(results)
    monkeypatch.setattr(psycopg, "connect", lambda *a, **k: _FakeConn(cur))
    return cur


# --- fails loudly, no silent Firestore fallback ------------------------------


def test_raises_when_episode_database_url_unset(monkeypatch):
    monkeypatch.delenv("EPISODE_DATABASE_URL", raising=False)

    def _must_not_connect(*a, **k):
        raise AssertionError("must not connect without EPISODE_DATABASE_URL")

    monkeypatch.setattr(psycopg, "connect", _must_not_connect)

    with pytest.raises(RuntimeError, match="EPISODE_DATABASE_URL"):
        reader.get_episode_by_id("ep_1")


# --- shows list/single --------------------------------------------------------


def test_get_all_podcast_shows_injects_id_from_pk(monkeypatch):
    rows = [("Gooaye_股癌", {"podcast_name": "Gooaye 股癌", "publisher": "X"})]
    _connect(monkeypatch, [rows])

    shows = reader.get_all_podcast_shows()

    assert shows == [{"podcast_name": "Gooaye 股癌", "publisher": "X", "id": "Gooaye_股癌"}]


def test_get_podcast_show_sanitizes_slash_like_upsert_podcast_show(monkeypatch):
    cur = _connect(monkeypatch, [("A_B", {"podcast_name": "A/B"})])

    show = reader.get_podcast_show("A/B")

    assert show == {"podcast_name": "A/B", "id": "A_B"}
    # the lookup key must match what upsert_podcast_show would have written as the id
    assert cur.executed[0][1] == ("A_B",)


def test_get_podcast_show_returns_none_when_missing(monkeypatch):
    _connect(monkeypatch, [None])
    assert reader.get_podcast_show("Nope") is None


# --- episode dedup lookups (watcher / processor / fill-limit) ----------------


def test_get_episode_by_fields_found(monkeypatch):
    doc = {"episode_title": "EP1", "mp3_url": "gs://x/1.mp3"}
    cur = _connect(monkeypatch, [("ep_1", doc)])

    result = reader.get_episode_by_fields("Show", "EP1", 1)

    assert result == {"episode_title": "EP1", "mp3_url": "gs://x/1.mp3", "id": "ep_1"}
    sql, params = cur.executed[0]
    assert "podcast_name = %s AND episode_title = %s" in sql
    assert "episode_number = %s" in sql
    assert params == ["Show", "EP1", 1]


def test_get_episode_by_fields_not_found_returns_none(monkeypatch):
    _connect(monkeypatch, [None])
    assert reader.get_episode_by_fields("Show", "Nope") is None


def test_get_episode_by_fields_without_episode_number_omits_that_clause(monkeypatch):
    cur = _connect(monkeypatch, [None])
    reader.get_episode_by_fields("Show", "EP1")
    sql, params = cur.executed[0]
    assert "episode_number" not in sql
    assert params == ["Show", "EP1"]


def test_get_episode_by_title_and_number_omits_podcast_name_filter(monkeypatch):
    cur = _connect(monkeypatch, [("ep_1", {"episode_title": "EP1"})])
    result = reader.get_episode_by_title_and_number("EP1", 3)
    sql, params = cur.executed[0]
    assert "podcast_name" not in sql
    assert params == ["EP1", 3]
    assert result["id"] == "ep_1"


def test_episode_exists_true_and_false(monkeypatch):
    _connect(monkeypatch, [("ep_1", {})])
    assert reader.episode_exists("Show", "EP1") is True

    _connect(monkeypatch, [None])
    assert reader.episode_exists("Show", "Nope") is False


# --- regen candidate read (query_episodes) -----------------------------------


def test_query_episodes_with_podcast_name_filter(monkeypatch):
    rows = [("ep_1", {"episode_title": "A"}), ("ep_2", {"episode_title": "B"})]
    cur = _connect(monkeypatch, [rows])

    result = reader.query_episodes(podcast_name="Show", limit=8)

    assert [r["id"] for r in result] == ["ep_1", "ep_2"]
    sql, params = cur.executed[0]
    assert "WHERE podcast_name = %s" in sql
    assert "ORDER BY created_time DESC" in sql
    assert params == ["Show", 8]


def test_query_episodes_without_filter_scans_all_recent(monkeypatch):
    rows = [("ep_1", {"episode_title": "A"})]
    cur = _connect(monkeypatch, [rows])

    result = reader.query_episodes(limit=4)

    assert [r["id"] for r in result] == ["ep_1"]
    sql, params = cur.executed[0]
    assert "WHERE" not in sql
    assert params == [4]


def test_get_all_episodes_rejects_unsupported_order_by(monkeypatch):
    _connect(monkeypatch, [[]])
    with pytest.raises(ValueError, match="order_by"):
        reader.get_all_episodes(order_by="episode_number")


# --- tags/tickers membership (validate step) ---------------------------------


def test_validate_episode_in_tags_and_tickers_checks_doc_arrays(monkeypatch):
    doc = {"tags": ["ai", "semis"], "related_tickers": ["2330", "NVDA"]}
    _connect(monkeypatch, [("ep_1", doc)])

    result = reader.validate_episode_in_tags_and_tickers(
        "ep_1", tags=["AI", "missing-tag"], tickers=["2330", "AMD"]
    )

    assert result["tags_valid"] is False
    assert result["tickers_valid"] is False
    assert result["tags_details"] == {"ai": True, "missing-tag": False}
    assert result["tickers_details"] == {"2330": True, "AMD": False}


def test_validate_episode_in_tags_and_tickers_empty_inputs_are_valid(monkeypatch):
    _connect(monkeypatch, [("ep_1", {"tags": [], "related_tickers": []})])

    result = reader.validate_episode_in_tags_and_tickers("ep_1", tags=[], tickers=[])

    assert result == {
        "tags_valid": True,
        "tickers_valid": True,
        "tags_details": {},
        "tickers_details": {},
    }
