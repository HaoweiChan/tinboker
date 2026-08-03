"""Unit tests for the ``firestore_mirror.podcasts`` dual-write (P2 review
follow-up MUST-FIX #1): ``upsert_podcast_show`` (upload_to_firebase.py) writes
Firestore only unless this also runs, and ``get_podcast_show``/
``get_all_podcast_shows`` (read-flipped in P2) read the mirror — without the
dual-write, a show add/edit never reaches the :8003 /shows endpoints.

Fake psycopg connection/cursor, same idiom as
``test_ticker_insights_export_step.py``.
"""

from __future__ import annotations

import psycopg
from src.service.upload_to_firebase import _mirror_podcast_show_to_postgres


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


def test_skips_without_episode_database_url(monkeypatch):
    monkeypatch.delenv("EPISODE_DATABASE_URL", raising=False)

    def _must_not_connect(*a, **k):
        raise AssertionError("must not connect without EPISODE_DATABASE_URL")

    monkeypatch.setattr(psycopg, "connect", _must_not_connect)

    _mirror_podcast_show_to_postgres("Show_A", {"podcast_name": "Show A"})


def test_upserts_the_same_doc_dict_keyed_by_doc_id(monkeypatch):
    monkeypatch.setenv("EPISODE_DATABASE_URL", "postgresql://x/y")
    cur = _FakeCursor()
    monkeypatch.setattr(psycopg, "connect", lambda *a, **k: _FakeConn(cur))

    metadata = {"podcast_name": "Gooaye 股癌", "thumbnail_url": "https://x/y.png"}
    _mirror_podcast_show_to_postgres("Gooaye_股癌", metadata)

    assert any("CREATE TABLE" in sql for sql, _ in cur.executed)
    upserts = [params for sql, params in cur.executed if "INSERT INTO" in sql]
    assert len(upserts) == 1
    doc_id, doc = upserts[0]
    assert doc_id == "Gooaye_股癌"
    assert doc.obj == metadata


def test_write_failure_is_non_fatal(monkeypatch):
    """Show metadata isn't dedup-critical (unlike the episode mirror) — a
    failure here must not raise, only warn."""
    monkeypatch.setenv("EPISODE_DATABASE_URL", "postgresql://x/y")

    def _boom(*a, **k):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(psycopg, "connect", _boom)

    _mirror_podcast_show_to_postgres("Show_A", {"podcast_name": "Show A"})  # must not raise


def test_upsert_sql_merges_onto_existing_doc_on_conflict():
    """ON CONFLICT must jsonb-merge (mirrors Firestore's set(..., merge=True)),
    not blindly overwrite — a partial metadata update must preserve fields
    already on the mirrored doc that this call didn't touch."""
    from src.podcast.exporters.postgres_mirror import _UPSERT_PODCAST_SHOW

    assert "doc = " in _UPSERT_PODCAST_SHOW
    assert "||" in _UPSERT_PODCAST_SHOW
    assert "EXCLUDED.doc" in _UPSERT_PODCAST_SHOW
