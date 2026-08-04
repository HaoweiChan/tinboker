"""Unit tests for the episode-doc `tags` gap fix (firestore-contract.md §2.1:
``tags: string[]`` must be on every episode doc, always).

Guards two things:
  1. `_normalize_tags` — the single vocabulary-filtering boundary. The
     ``tags/{slug}/episodes`` fan-out it also used to feed is gone (P4), so the
     episode doc's own array is now the only place a hallucinated slug could
     land — and the only thing the backend's GIN-indexed tag queries read.
  2. `persist_episode` stamps the normalized list onto `episode.tags` BEFORE
     calling `episode.to_firestore_dict()`, so the stored document and any later
     consumer of the same PodcastEpisode object (e.g. the ticker-insights step,
     which runs right after on the same object) agree.
"""

from __future__ import annotations

import psycopg
from src.pipeline.steps import postgres_episode
from src.pipeline.steps.postgres_episode import persist_episode
from src.service.upload_to_firebase import _normalize_tags


class _FakeCursor:
    def __init__(self):
        self.executed: list[tuple[str, tuple]] = []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchone(self):
        return None  # brand-new episode

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
    podcast_name = "股癌"
    episode = None

    def __init__(self, tags):
        self.tags = tags


def _mock_vocabulary(monkeypatch, allowed: set[str]) -> None:
    monkeypatch.setattr(
        "src.podcast.content_builder.tag_vocabulary.canonical_tag_slug",
        lambda t: t if t in allowed else None,
    )
    monkeypatch.setattr(
        "src.podcast.content_builder.tag_vocabulary.normalize_tag_slug",
        lambda t: (t or "").lower(),
    )


def _persist(monkeypatch, tags):
    """Run the persist step against a fake Postgres; return (episode, stored doc)."""
    from src.models.podcast_models import PodcastEpisode

    episode = PodcastEpisode(
        mp3_url="gs://b/m", transcript_url="gs://b/t",
        summary_url="gs://b/s", summary_image_url="gs://b/i",
        podcast_name="股癌", episode_title="EP1",
    )
    monkeypatch.setattr(postgres_episode, "create_episode_object", lambda **kw: episode)
    monkeypatch.setenv("EPISODE_DATABASE_URL", "postgresql://x/y")
    cur = _FakeCursor()
    monkeypatch.setattr(psycopg, "connect", lambda *a, **k: _FakeConn(cur))

    persist_episode(_Config(), _Services(), _EpisodeData(tags))

    (_, params) = [(s, p) for s, p in cur.executed if "INSERT INTO" in s][0]
    return episode, params[-1].obj


# --- _normalize_tags ---------------------------------------------------------

def test_normalize_tags_filters_vocabulary_dedupes_and_sorts(monkeypatch):
    _mock_vocabulary(monkeypatch, allowed={"AI", "supplychain"})
    result = _normalize_tags(["AI", "ai", "supplychain", "junk-not-in-vocab", None, ""])
    assert result == ["ai", "supplychain"]


def test_normalize_tags_handles_none_and_empty():
    assert _normalize_tags(None) == []
    assert _normalize_tags([]) == []


# --- persist_episode: episode.tags is stamped before the doc is built --------

def test_persist_stamps_tags_on_the_episode_object_and_the_doc(monkeypatch):
    _mock_vocabulary(monkeypatch, allowed={"AI"})

    episode, doc = _persist(monkeypatch, ["AI", "junk"])

    # 1. The episode object itself carries the final tags — what any later
    #    to_firestore_dict() call on the same object would see.
    assert episode.tags == ["ai"]
    assert episode.to_firestore_dict()["tags"] == ["ai"]
    # 2. The stored document carried them, in the same write.
    assert doc["tags"] == ["ai"]


def test_persist_writes_empty_tags_when_none_given(monkeypatch):
    """Contract §2.1: `tags` must be present (may be empty) on EVERY episode doc,
    even one with zero tags."""
    _mock_vocabulary(monkeypatch, allowed=set())

    _, doc = _persist(monkeypatch, None)

    assert doc["tags"] == []
