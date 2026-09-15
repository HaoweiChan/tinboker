"""get_recent_episodes pushes the release scope into the mirror query.

Before, a cache miss pulled every stored episode (6,834 after the 2020 backfill) and
filtered to ~300 in Python on the event loop. The SQL filters here are a prefilter;
_scope_episodes still makes the exact release-time cut.
"""
import json
from datetime import datetime, timezone

from src.config import settings
from src.services import podcast as podcast_mod
from src.services.podcast import PodcastService


class _Store:
    def __init__(self):
        self.calls = []

    def query_collection(self, **kw):
        self.calls.append(kw)
        return []


def _service(monkeypatch, store, allowed):
    async def _allowed(self):
        return allowed

    async def _no_cache(key, compute, ttl, stale):
        return await compute()

    monkeypatch.setattr(podcast_mod, "cache_swr", _no_cache)
    monkeypatch.setattr(PodcastService, "_allowed_podcast_names", _allowed)
    return PodcastService(firestore_service=store)


async def test_scope_becomes_sql_filters(monkeypatch):
    monkeypatch.setattr(settings, "release_episode_max_age_days", 60)
    store = _Store()
    svc = _service(monkeypatch, store, frozenset({"股癌", "財報狗"}))
    await svc.get_recent_episodes(limit=60)

    (call,) = store.calls
    filters = {f[0]: f for f in call["filters"]}
    assert filters["podcast_name"] == ("podcast_name", "in", ["股癌", "財報狗"])
    field, op, since = filters["created_time"]
    assert op == ">=" and since.tzinfo is not None
    cutoff = datetime.fromtimestamp(PodcastService._recency_cutoff_ms() / 1000, tz=timezone.utc)
    assert 2 * 86400 - 5 <= (cutoff - since).total_seconds() <= 2 * 86400 + 5  # two days of slack
    assert call["limit"] is None  # the feed sorts by release time, so SQL can't page it


async def test_no_scope_keeps_the_plain_limited_query(monkeypatch):
    monkeypatch.setattr(settings, "release_episode_max_age_days", 0)
    store = _Store()
    svc = _service(monkeypatch, store, None)
    await svc.get_recent_episodes(limit=20)

    (call,) = store.calls
    assert call["filters"] is None and call["limit"] == 20


async def test_light_feed_drops_fields_no_card_reads(monkeypatch):
    """1.3 MB for 60 home cards, 47% of it sector_exposures the cards never render."""
    from src.models.podcast import Episode
    from src.routers import episodes as router

    ep = Episode(id="E1", podcast_name="股癌", episode_title="t", created_time=0, key_insights=["一"], summary_content="s",
                 sector_exposures=[{"exposure_id": "sector_ai"}], spotify_description="long")

    async def _recent(**kw):
        return [ep]

    monkeypatch.setattr(router.podcast_service, "get_recent_episodes", _recent)
    monkeypatch.setattr(router, "schedule_ticker_discovery", lambda eps: None)

    def _body(resp):
        return json.loads(resp.body) if hasattr(resp, "body") else resp

    light = _body(await router.get_recent_episodes(limit=1, offset=0, podcast_name=None, include_content=False))["episodes"][0]
    assert "sector_exposures" not in light and "spotify_description" not in light
    assert light["key_insights"] == ["一"] and light["summary_content"] == "s"  # what the card shows
    full = _body(await router.get_recent_episodes(limit=1, offset=0, podcast_name=None, include_content=True))["episodes"][0]
    assert full["sector_exposures"]
