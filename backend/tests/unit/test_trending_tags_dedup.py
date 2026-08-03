"""Unit test for get_trending_tags()'s shared episode fetch.

The July 2026 GCP bill was dominated by this path re-fetching the same episode
docs once per tag (Firestore reads + us-central1 egress); the fix lists refs per
tag, then batch-fetches the deduped union exactly once. Mocks FirestoreService
and the Redis cache — no real Firebase or Redis needed.  Mirrors the pattern
established in test_sector_board.py.
"""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.podcast import PodcastService

NOW_MS = int(datetime(2026, 6, 19, 12, 0, 0).timestamp() * 1000)


def _episode(eid: str) -> dict:
    """Minimal raw Firestore episode dict that passes the content/scope guards."""
    return {
        "id": eid,
        "podcast_name": "Gooaye 股癌",
        "episode_title": f"Episode {eid}",
        "created_time": NOW_MS,
        "released_at_ms": NOW_MS,
        "summary_content": "摘要內容",
        "key_insights": [],
        "related_tickers": [],
    }


async def test_episode_docs_fetched_once_across_tags():
    refs = {
        "ai": [{"episode_id": "e1"}, {"episode_id": "e2"}],
        "semis": [{"episode_id": "e2"}, {"episode_id": "e3"}],
    }
    mock_fs = MagicMock()
    mock_fs.get_subcollection_documents.side_effect = (
        lambda collection, parent_doc_id, **kw: refs[parent_doc_id]
    )
    mock_fs.get_documents_batch.return_value = [_episode(e) for e in ("e1", "e2", "e3")]
    svc = PodcastService(firestore_service=mock_fs)

    with patch.object(PodcastService, "_get_topic_tags", return_value=["ai", "semis"]), \
         patch.object(PodcastService, "_allowed_podcast_names", AsyncMock(return_value=None)), \
         patch.object(PodcastService, "_recency_cutoff_ms", staticmethod(lambda: None)), \
         patch("src.services.podcast.cache_get", AsyncMock(return_value=None)), \
         patch("src.services.podcast.cache_set", AsyncMock()) as mock_set:
        tags = await svc.get_trending_tags()

    # The union {e1,e2,e3} is fetched in exactly ONE batch call, deduped + sorted —
    # per-tag re-fetching is the regression this test guards against.
    assert mock_fs.get_documents_batch.call_count == 1
    assert mock_fs.get_documents_batch.call_args.args == ("episodes", ["e1", "e2", "e3"])

    by_id = {t["id"]: t for t in tags}
    assert by_id["ai"]["scoped_count"] == 2
    assert by_id["semis"]["scoped_count"] == 2

    # Serving-cache TTL must outlive the 1h production refresh-ahead interval.
    assert mock_set.await_args.args[2] == PodcastService._TOPIC_BOARD_CACHE_TTL


async def test_empty_result_is_not_cached():
    """A transient upstream failure yields [] — pinning that for the 2h TTL would
    blank /topics for hours, so empties must never be written to the cache."""
    mock_fs = MagicMock()
    mock_fs.get_subcollection_documents.return_value = []
    svc = PodcastService(firestore_service=mock_fs)

    with patch.object(PodcastService, "_get_topic_tags", return_value=["ai"]), \
         patch.object(PodcastService, "_allowed_podcast_names", AsyncMock(return_value=None)), \
         patch.object(PodcastService, "_recency_cutoff_ms", staticmethod(lambda: None)), \
         patch("src.services.podcast.cache_get", AsyncMock(return_value=None)), \
         patch("src.services.podcast.cache_set", AsyncMock()) as mock_set:
        tags = await svc.get_trending_tags()
        await svc._cache_sector_board([])

    assert tags == []
    mock_set.assert_not_awaited()
