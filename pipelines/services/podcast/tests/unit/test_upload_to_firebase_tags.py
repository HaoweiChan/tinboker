"""Unit tests for the episode-doc `tags` gap fix (firestore-contract.md §2.1:
``tags: string[]`` must be on every episode doc, always).

Guards two things:
  1. `_normalize_tags` — the single vocabulary-filtering boundary shared by the
     episode-doc stamp and the `tags/{slug}/episodes` fan-out.
  2. `upload_podcast_data` stamps the normalized list onto `episode.tags` BEFORE
     calling `episode.to_firestore_dict()` — not just as a side Firestore write —
     because `pipeline.steps.postgres_episode`'s mirror step (Step 5c) runs right
     after this one (Step 5) and reads the SAME PodcastEpisode object, not a fresh
     Firestore doc. A side-write-only fix would leave the Postgres mirror stale.

No real Firestore: a small hand-rolled fake models the `collection().document()`
chain (keyed by name/id, unlike a bare MagicMock whose `.return_value` would
collapse every collection/doc into the same object).
"""

from __future__ import annotations

from unittest.mock import MagicMock

from src.models.podcast_models import PodcastEpisode
from src.service.upload_to_firebase import FirebaseService, _normalize_tags


class _FakeDoc:
    def __init__(self):
        self.data = None  # None until the first .set() — mirrors a missing doc
        self.set_calls: list[tuple[dict, bool]] = []
        self._subcollections: dict[str, "_FakeCollection"] = {}

    def get(self):
        snap = MagicMock()
        snap.exists = self.data is not None
        snap.to_dict.return_value = self.data or {}
        return snap

    def set(self, data, merge=False):
        self.set_calls.append((dict(data), merge))
        if merge and self.data:
            self.data.update(data)
        else:
            self.data = dict(data)

    def collection(self, name):
        return self._subcollections.setdefault(name, _FakeCollection())


class _FakeCollection:
    def __init__(self):
        self.docs: dict[str, _FakeDoc] = {}

    def document(self, doc_id):
        return self.docs.setdefault(doc_id, _FakeDoc())


class _FakeDB:
    def __init__(self):
        self.collections: dict[str, _FakeCollection] = {}

    def collection(self, name):
        return self.collections.setdefault(name, _FakeCollection())


def _fake_service() -> FirebaseService:
    """A FirebaseService with a fake `.db` — bypasses __init__'s real
    firebase_admin bootstrap entirely."""
    svc = FirebaseService.__new__(FirebaseService)
    svc.db = _FakeDB()
    return svc


def _episode() -> PodcastEpisode:
    return PodcastEpisode(
        mp3_url="gs://b/m", transcript_url="gs://b/t",
        summary_url="gs://b/s", summary_image_url="gs://b/i",
        podcast_name="股癌", episode_title="EP1",
    )


def _mock_vocabulary(monkeypatch, allowed: set[str]) -> None:
    monkeypatch.setattr(
        "src.podcast.content_builder.tag_vocabulary.canonical_tag_slug",
        lambda t: t if t in allowed else None,
    )
    monkeypatch.setattr(
        "src.podcast.content_builder.tag_vocabulary.normalize_tag_slug",
        lambda t: (t or "").lower(),
    )


# --- _normalize_tags ---------------------------------------------------------

def test_normalize_tags_filters_vocabulary_dedupes_and_sorts(monkeypatch):
    _mock_vocabulary(monkeypatch, allowed={"AI", "supplychain"})
    result = _normalize_tags(["AI", "ai", "supplychain", "junk-not-in-vocab", None, ""])
    assert result == ["ai", "supplychain"]


def test_normalize_tags_handles_none_and_empty():
    assert _normalize_tags(None) == []
    assert _normalize_tags([]) == []


# --- upload_podcast_data: episode.tags is stamped, not just Firestore-written ----

def test_upload_podcast_data_stamps_tags_before_mirror_can_read_them(monkeypatch):
    _mock_vocabulary(monkeypatch, allowed={"AI"})
    svc = _fake_service()
    episode = _episode()

    svc.upload_podcast_data(podcast_name="股癌", episode=episode, tags=["AI", "junk"], tickers=[])

    # 1. The episode object itself carries the final tags (what a later
    #    to_firestore_dict() call — e.g. from the Postgres mirror step — would see).
    assert episode.tags == ["ai"]
    assert episode.to_firestore_dict()["tags"] == ["ai"]

    # 2. The Firestore doc write also carried them, in the SAME call.
    (episode_doc,) = svc.db.collections["episodes"].docs.values()
    assert episode_doc.data["tags"] == ["ai"]


def test_upload_podcast_data_writes_empty_tags_when_none_given(monkeypatch):
    """Contract §2.1: `tags` must be present (may be empty) on EVERY episode doc,
    even one with zero tags and zero tickers."""
    _mock_vocabulary(monkeypatch, allowed=set())
    svc = _fake_service()
    episode = _episode()

    svc.upload_podcast_data(podcast_name="股癌", episode=episode, tags=None, tickers=None)

    (episode_doc,) = svc.db.collections["episodes"].docs.values()
    assert episode_doc.data["tags"] == []


def test_upload_podcast_data_update_path_merges_tags_not_protected(monkeypatch):
    """The existing-episode (merge=True) branch must not drop `tags` — it isn't in
    the protected-field list (created_time/modified_*)."""
    _mock_vocabulary(monkeypatch, allowed={"AI"})
    svc = _fake_service()
    episode = _episode()
    episode_id = svc._generate_episode_id("股癌", episode)
    svc.db.collection("episodes").document(episode_id).set({"podcast_name": "股癌"})

    svc.upload_podcast_data(podcast_name="股癌", episode=episode, tags=["AI"], tickers=[])

    episode_doc = svc.db.collections["episodes"].docs[episode_id]
    data, merge = episode_doc.set_calls[-1]
    assert data["tags"] == ["ai"]
    assert merge is True


# --- upload_tags_and_tickers reuses the SAME normalization -------------------

def test_upload_tags_and_tickers_uses_shared_normalize_tags(monkeypatch):
    """Regression guard for the refactor: the fan-out must filter through the exact
    same vocabulary boundary as the episode-doc stamp (single source of truth)."""
    _mock_vocabulary(monkeypatch, allowed={"AI"})
    svc = _fake_service()

    svc.upload_tags_and_tickers(
        episode_id="ep_1", tags=["AI", "junk"], tickers=[],
        episode_data={"episode_title": "EP1", "podcast_name": "股癌"},
    )

    tags_collection = svc.db.collections["tags"]
    assert set(tags_collection.docs.keys()) == {"ai"}
    fanned_out = tags_collection.docs["ai"].collection("episodes").docs
    assert set(fanned_out.keys()) == {"ep_1"}
