"""Unit tests for the main-pipeline ticker_insights export step
(``pipeline.steps.ticker_insights_export``).

Guards the regression where the step stamped ``podcast_launch_time`` with the
processing time (``now()``) instead of the episode's true publish date — the
``getattr(episode_data, "released_at_ms")`` read was dead (the pipeline EpisodeData has
no such field), so it fell through to an unset ``created_time`` and then to now(),
collapsing reprocessed back-catalogues onto the run date on /picks.
"""

from __future__ import annotations

from datetime import datetime, timezone

import psycopg
import pytest
from src.models.podcast_models import PodcastEpisode
from src.pipeline.episode_data import EpisodeData
from src.pipeline.steps.ticker_insights_export import export_ticker_insights
from src.podcast.exporters.ticker_insights import write_episode_insights_postgres

_FEED_MS = 1764849366000  # 2025-12-04 — a real back-catalogue publish date


class _Config:
    rerun_from = None


class _FB:
    db = object()


class _Services:
    firebase_service = _FB()


def _capture(monkeypatch, *, stub_writer: bool = True) -> dict:
    captured: dict = {}

    def fake_build(*, raw_payload, episode_id, podcaster, podcast_launch_time):
        captured["launch_time"] = podcast_launch_time
        return {"2330": {"ticker": "2330"}}

    monkeypatch.setattr(
        "src.podcast.exporters.ticker_insights.build_episode_insight_docs", fake_build
    )
    if stub_writer:
        monkeypatch.setattr(
            "src.podcast.exporters.ticker_insights.write_episode_insights_postgres",
            lambda episode_id, docs: len(docs),
        )
    return captured


def _episode_data(*, episode_model, created_time=None) -> EpisodeData:
    ed = EpisodeData(api_data={"title": "EP"}, podcast_name="財經一路發", language="zh")
    ed.episode_id = "ep_x"
    ed.summary_result = {"ticker_insights": [{"ticker": "2330", "sentiment_score": 0.7}]}
    ed.created_time = created_time
    ed.episode = episode_model
    return ed


def test_export_stamps_episode_publish_ms_not_now(monkeypatch):
    """Stamps the uploaded PodcastEpisode's resolved publish time (feed datePublished),
    NOT the processing time — even though the pipeline EpisodeData.created_time is unset
    (the exact condition that produced the now() regression)."""
    model = PodcastEpisode(
        mp3_url="gs://b/m", transcript_url="gs://b/t",
        summary_url="gs://b/s", summary_image_url="gs://b/i",
        feed_date_published_ms=_FEED_MS,
    )
    captured = _capture(monkeypatch)
    export_ticker_insights(_Config(), _Services(), _episode_data(episode_model=model))
    assert captured["launch_time"] == _FEED_MS


def test_export_falls_back_to_created_time_without_episode_model(monkeypatch):
    """Defensive: if the upload step never attached the episode model, the step still
    stamps the ingestion created_time rather than crashing or stamping now()."""
    created = datetime(2025, 5, 9, tzinfo=timezone.utc)
    captured = _capture(monkeypatch)
    export_ticker_insights(
        _Config(), _Services(), _episode_data(episode_model=None, created_time=created)
    )
    assert captured["launch_time"] == created


# --- the only write: firestore_mirror.ticker_insights -----------------------


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


def test_write_raises_without_episode_database_url(monkeypatch):
    """Sole store since P4 — a silent skip would lose the episode's picks."""
    monkeypatch.delenv("EPISODE_DATABASE_URL", raising=False)

    def _must_not_connect(*a, **k):
        raise AssertionError("must not connect without EPISODE_DATABASE_URL")

    monkeypatch.setattr(psycopg, "connect", _must_not_connect)

    with pytest.raises(RuntimeError, match="EPISODE_DATABASE_URL"):
        write_episode_insights_postgres("ep_1", {"2330": {"ticker": "2330"}})


def test_write_skips_when_docs_empty(monkeypatch):
    monkeypatch.setenv("EPISODE_DATABASE_URL", "postgresql://x/y")

    def _must_not_connect(*a, **k):
        raise AssertionError("must not connect with no docs to write")

    monkeypatch.setattr(psycopg, "connect", _must_not_connect)

    assert write_episode_insights_postgres("ep_1", {}) == 0


def test_write_upserts_each_ticker_doc(monkeypatch):
    monkeypatch.setenv("EPISODE_DATABASE_URL", "postgresql://x/y")
    cur = _FakeCursor()
    monkeypatch.setattr(psycopg, "connect", lambda *a, **k: _FakeConn(cur))

    docs = {"2330": {"ticker": "2330"}, "NVDA": {"ticker": "NVDA"}}
    write_episode_insights_postgres("ep_1", docs)

    assert any("CREATE TABLE" in sql for sql, _ in cur.executed)
    upserts = [params for sql, params in cur.executed if "INSERT INTO" in sql]
    assert len(upserts) == 2
    assert {p[0] for p in upserts} == {"ep_1"}
    assert {p[1] for p in upserts} == {"2330", "NVDA"}


def test_export_ticker_insights_writes_the_built_docs_to_postgres(monkeypatch):
    """The live pipeline step upserts exactly the docs it built — no Firestore
    copy exists to fall back on."""
    monkeypatch.setenv("EPISODE_DATABASE_URL", "postgresql://x/y")
    _capture(monkeypatch, stub_writer=False)  # build -> {"2330": {"ticker": "2330"}}
    cur = _FakeCursor()
    monkeypatch.setattr(psycopg, "connect", lambda *a, **k: _FakeConn(cur))

    model = PodcastEpisode(
        mp3_url="gs://b/m", transcript_url="gs://b/t",
        summary_url="gs://b/s", summary_image_url="gs://b/i",
        feed_date_published_ms=_FEED_MS,
    )
    export_ticker_insights(_Config(), _Services(), _episode_data(episode_model=model))

    upserts = [params for sql, params in cur.executed if "INSERT INTO" in sql]
    assert len(upserts) == 1
    episode_id, ticker, doc = upserts[0]
    assert episode_id == "ep_x"
    assert ticker == "2330"
    assert doc.obj == {"ticker": "2330"}


def test_resolved_publish_ms_matches_firestore_released_at_ms():
    """resolved_publish_ms() returns the SAME value to_firestore_dict writes as
    released_at_ms, so the insight date and the episode doc can never diverge."""
    model = PodcastEpisode(
        mp3_url="gs://b/m", transcript_url="gs://b/t",
        summary_url="gs://b/s", summary_image_url="gs://b/i",
        feed_date_published_ms=_FEED_MS,
    )
    assert model.resolved_publish_ms() == _FEED_MS
    assert model.to_firestore_dict().get("released_at_ms") == _FEED_MS
