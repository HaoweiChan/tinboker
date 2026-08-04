"""Unit tests for ``pipeline.steps.postgres_episode.persist_episode`` — the only
episode write since P4 (contract § 11.5).

Two things it must never get wrong:

  * FAIL LOUDLY. A missing ``EPISODE_DATABASE_URL`` or a write error raises;
    there is no Firestore copy left to fall back on, and the row is also the
    dedup authority + the backend notification producer's high-water mark.
  * PRESERVE what the platform owns. Firestore's ``set(..., merge=True)`` used
    to give this for free; now ``_merge_onto_stored`` has to. A re-ingest must
    not advance ``created_time`` (contract § 2.1), must not clobber the
    ``modified_*`` quad a user's summary edit wrote (§ 2.3 #3), and must not
    zero ``num_likes`` / reset admin-owned ``social_thread`` / ``social_cards``.

Fake psycopg connection/cursor, same idiom as
``test_ticker_insights_export_step.py``.
"""

from __future__ import annotations

import psycopg
import pytest
from src.pipeline.steps import postgres_episode
from src.pipeline.steps.postgres_episode import (
    _UPSERT,
    _merge_onto_stored,
    persist_episode,
)


class _FakeCursor:
    def __init__(self, stored: dict | None = None):
        self.executed: list[tuple[str, tuple]] = []
        self._stored = stored

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchone(self):
        return (self._stored,) if self._stored is not None else None

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
    num_likes = 0
    number_click = 0
    related_tickers = ["2330"]
    tags: list[str] = []

    def to_firestore_dict(self):
        return {
            "episode_title": "EP1",
            "podcast_name": "Show",
            "episode_number": 1,
            "created_time": self.created_time,
            "num_likes": 0,
            "number_click": 0,
            "related_tickers": ["2330"],
            "tags": [],
            "summary_content": "fresh summary",
            "retracted_at": None,
        }


class _FB:
    def _generate_episode_id(self, podcast_name, episode):
        return "ep_1"


class _Services:
    firebase_service = _FB()


class _EpisodeData:
    api_data = {"title": "EP1"}
    gcs_urls = {"mp3_url": "gs://b/m"}
    spotify_metadata = None
    summary_result = None
    podcast_name = "Show"
    tags: list[str] = []
    episode = None


def _stub_episode_build(monkeypatch):
    """Skip create_episode_object/_normalize_tags — this module's job is the
    persistence semantics, not the model assembly (covered elsewhere)."""
    monkeypatch.setattr(postgres_episode, "create_episode_object", lambda **kw: _Episode())
    monkeypatch.setattr(
        "src.service.upload_to_firebase._normalize_tags", lambda tags: list(tags or [])
    )


# --- fails loudly, no best-effort silent skip --------------------------------


def test_raises_without_episode_database_url(monkeypatch):
    _stub_episode_build(monkeypatch)
    monkeypatch.delenv("EPISODE_DATABASE_URL", raising=False)

    def _must_not_connect(*a, **k):
        raise AssertionError("must not connect without EPISODE_DATABASE_URL")

    monkeypatch.setattr(psycopg, "connect", _must_not_connect)

    with pytest.raises(RuntimeError, match="EPISODE_DATABASE_URL"):
        persist_episode(_Config(), _Services(), _EpisodeData())


def test_write_failure_propagates_instead_of_being_swallowed(monkeypatch):
    _stub_episode_build(monkeypatch)
    monkeypatch.setenv("EPISODE_DATABASE_URL", "postgresql://x/y")

    def _boom(*a, **k):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(psycopg, "connect", _boom)

    with pytest.raises(RuntimeError, match="connection refused"):
        persist_episode(_Config(), _Services(), _EpisodeData())


# --- created_time immutable on conflict --------------------------------------


def test_upsert_sql_excludes_created_time_from_conflict_update():
    """Static guard on the shared SQL: a re-ingest's ON CONFLICT branch must
    never touch created_time, even if a future edit adds columns nearby."""
    _, update_clause = _UPSERT.split("DO UPDATE SET", 1)
    assert "created_time" not in update_clause
    # sanity: it IS still written on first insert (the INSERT column list)
    assert "created_time" in _UPSERT.split("DO UPDATE SET", 1)[0]


def test_new_episode_inserts_the_built_doc(monkeypatch):
    _stub_episode_build(monkeypatch)
    monkeypatch.setenv("EPISODE_DATABASE_URL", "postgresql://x/y")
    cur = _FakeCursor(stored=None)
    monkeypatch.setattr(psycopg, "connect", lambda *a, **k: _FakeConn(cur))

    persist_episode(_Config(), _Services(), _EpisodeData())

    upserts = [(sql, params) for sql, params in cur.executed if "INSERT INTO" in sql]
    assert len(upserts) == 1
    sql, params = upserts[0]
    assert "created_time" not in sql.split("DO UPDATE SET", 1)[1]
    assert params[0] == "ep_1"
    assert params[-1].obj["summary_content"] == "fresh summary"
    assert params[-1].obj["retracted_at"] is None


# --- platform-owned fields survive a re-ingest -------------------------------


def test_reingest_preserves_user_edited_summary_and_platform_fields(monkeypatch):
    """The regression this whole mechanism exists for: a nightly re-ingest of an
    episode whose summary a user edited on the site must not wipe the edit."""
    _stub_episode_build(monkeypatch)
    monkeypatch.setenv("EPISODE_DATABASE_URL", "postgresql://x/y")
    stored = {
        "created_time": "2024-03-03T00:00:00Z",
        "modified_summary_url": "gs://b/edited.md",
        "modified_summary_content": "the human's version",
        "modified_by": "willy@example.com",
        "modified_at": 1234567890,
        "social_thread": {"post": "hi"},
        "social_cards": [{"image_url": "https://x/card.png"}],
        "num_likes": 42,
        "number_click": 99,
        "retracted_at": 1700000000,
        "some_frontend_owned_field": "keep me",
        "summary_content": "the old machine version",
    }
    cur = _FakeCursor(stored=stored)
    monkeypatch.setattr(psycopg, "connect", lambda *a, **k: _FakeConn(cur))

    persist_episode(_Config(), _Services(), _EpisodeData())

    (_, params) = [(s, p) for s, p in cur.executed if "INSERT INTO" in s][0]
    doc = params[-1].obj

    # the user's edit and every other platform-owned value survived
    assert doc["modified_summary_content"] == "the human's version"
    assert doc["modified_summary_url"] == "gs://b/edited.md"
    assert doc["modified_by"] == "willy@example.com"
    assert doc["modified_at"] == 1234567890
    assert doc["social_thread"] == {"post": "hi"}
    assert doc["social_cards"] == [{"image_url": "https://x/card.png"}]
    assert doc["num_likes"] == 42 and doc["number_click"] == 99
    assert doc["retracted_at"] == 1700000000
    # created_time is immutable (contract § 2.1) — the stored value wins
    assert doc["created_time"] == "2024-03-03T00:00:00Z"
    # merge=True semantics: keys this run didn't produce are not dropped
    assert doc["some_frontend_owned_field"] == "keep me"
    # ...but pipeline-owned content IS refreshed
    assert doc["summary_content"] == "fresh summary"
    # and the promoted counter columns follow the merged doc, not the fresh zeros
    assert params[5] == 42 and params[6] == 99


def test_merge_lets_a_real_regeneration_replace_platform_owned_lists():
    """Preservation is 'stored wins when this run produced nothing' — a run that
    genuinely rebuilt the social cards still lands them."""
    merged = _merge_onto_stored(
        {"social_cards": [{"title": "new"}], "num_likes": 0},
        {"social_cards": [{"title": "old"}], "num_likes": 7},
    )
    assert merged["social_cards"] == [{"title": "new"}]
    assert merged["num_likes"] == 7


def test_merge_never_blanks_podcast_name():
    merged = _merge_onto_stored({"podcast_name": ""}, {"podcast_name": "股癌"})
    assert merged["podcast_name"] == "股癌"
