"""``FirestoreService.get_document``/``query_collection`` dispatch (P2 read-flip):
``collection == "episodes"`` must read ``firestore_mirror.episodes`` instead of
Firestore — every live (non-script) caller (the social-copy endpoint, regen's
``start``/``find_candidates``) only ever queries that one collection. Other
collections are untouched (generic/script callers, unused today).

Constructs ``FirestoreService`` via ``object.__new__`` to skip ``__init__``
(which requires real Firebase credentials) — safe here because the "episodes"
branch never touches ``self.db``.
"""

from __future__ import annotations

import pytest
from src.service import postgres_mirror_reader as reader
from src.service.firestore_service import FirestoreService


def _service() -> FirestoreService:
    return object.__new__(FirestoreService)


def test_get_document_episodes_reads_mirror(monkeypatch):
    monkeypatch.setattr(
        reader, "get_episode_by_id", lambda episode_id: {"id": episode_id, "episode_title": "EP1"}
    )
    doc = _service().get_document("episodes", "ep_1")
    assert doc == {"id": "ep_1", "episode_title": "EP1"}


def test_get_document_other_collection_untouched(monkeypatch):
    def _boom(*a, **k):
        raise AssertionError("mirror reader must not be called for non-episodes collections")

    monkeypatch.setattr(reader, "get_episode_by_id", _boom)
    svc = _service()
    svc.db = None  # would blow up if the (unused-today) Firestore branch were reached without a real client
    with pytest.raises(Exception, match="Failed to get document"):
        svc.get_document("users", "u1")


def test_query_collection_episodes_translates_podcast_name_filter(monkeypatch):
    captured = {}

    def fake_query_episodes(*, podcast_name, order_by, descending, limit):
        captured.update(podcast_name=podcast_name, order_by=order_by, descending=descending, limit=limit)
        return [{"id": "ep_1"}]

    monkeypatch.setattr(reader, "query_episodes", fake_query_episodes)

    result = _service().query_collection(
        "episodes", filters=[("podcast_name", "==", "Show")], limit=80
    )

    assert result == [{"id": "ep_1"}]
    assert captured == {
        "podcast_name": "Show",
        "order_by": "created_time",
        "descending": True,
        "limit": 80,
    }


def test_query_collection_episodes_no_filter_scans_recent(monkeypatch):
    captured = {}

    def fake_query_episodes(*, podcast_name, order_by, descending, limit):
        captured.update(podcast_name=podcast_name, descending=descending)
        return []

    monkeypatch.setattr(reader, "query_episodes", fake_query_episodes)

    _service().query_collection("episodes", order_by="created_time", direction="DESCENDING", limit=80)

    assert captured == {"podcast_name": None, "descending": True}


def test_query_collection_episodes_rejects_unsupported_filter():
    with pytest.raises(ValueError, match="podcast_name"):
        _service().query_collection("episodes", filters=[("episode_title", "==", "X")])
