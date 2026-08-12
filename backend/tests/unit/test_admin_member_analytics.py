"""Member analytics must read episode titles from the content seam, and must
still answer when that lookup fails (the Firestore-exit regression: a dead
content read 500'd the whole Members panel)."""
import pytest

from src.routers import admin_analytics


@pytest.fixture
def _no_cache(monkeypatch):
    async def _get(_key):
        return None

    async def _set(*_args, **_kwargs):
        return None

    monkeypatch.setattr(admin_analytics, "cache_get", _get)
    monkeypatch.setattr(admin_analytics, "cache_set", _set)


@pytest.fixture
def _one_user(monkeypatch):
    monkeypatch.setattr(
        admin_analytics,
        "_load_users",
        lambda: [{"created_at": None, "episode_bookmarks": ["ep1"], "watchlist": ["2330"]}],
    )
    monkeypatch.setattr(admin_analytics, "display_map", lambda _db: {})


class _Mirror:
    def get_documents_batch(self, collection, ids):
        assert collection == "episodes"
        return [{"id": i, "episode_title": f"title-{i}"} for i in ids]


class _Dead:
    def get_documents_batch(self, *_args):
        raise RuntimeError("Firestore is gone")


@pytest.mark.asyncio
async def test_titles_come_from_content_seam(monkeypatch, _no_cache, _one_user):
    monkeypatch.setattr(admin_analytics, "content_read_service", _Mirror)
    payload = await admin_analytics.get_member_analytics(top=10, admin=None, db=None)
    assert payload["top_episodes"] == [{"episode_id": "ep1", "title": "title-ep1", "count": 1}]


@pytest.mark.asyncio
async def test_dead_content_read_degrades_to_ids(monkeypatch, _no_cache, _one_user):
    monkeypatch.setattr(admin_analytics, "content_read_service", _Dead)
    payload = await admin_analytics.get_member_analytics(top=10, admin=None, db=None)
    assert payload["total_users"] == 1
    assert payload["top_episodes"] == [{"episode_id": "ep1", "title": "ep1", "count": 1}]
    assert payload["top_tickers"] == [{"ticker": "2330", "count": 1}]
