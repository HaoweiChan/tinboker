"""Old discovery caches must not re-expose development-only podcast sources."""
import json
from unittest.mock import AsyncMock, Mock

import pytest

from src.config import settings
from src.services import trending


@pytest.mark.parametrize("method,old_key", [("get_active_podcasters", "trending:podcasters:5"), ("get_trending_stocks", "trending:stocks:7:5:v4")])
async def test_discovery_ignores_pre_visibility_cache(monkeypatch, method, old_key):
    monkeypatch.setattr(settings, "environment", "production")
    stale = json.dumps([dict(id="podcast-曼報", type="podcast", title="曼報", link="/podcaster/曼報")])
    cache = AsyncMock(side_effect=lambda key: stale if key == old_key else None)
    monkeypatch.setattr(trending, "cache_get", cache)
    monkeypatch.setattr(trending, "cache_set", AsyncMock())
    monkeypatch.setattr(trending, "get_redis", AsyncMock(return_value=None))
    service = trending.TrendingService.__new__(trending.TrendingService)
    service.podcast_service = Mock(get_recent_episodes=AsyncMock(return_value=[]), get_all_podcasts=AsyncMock(return_value=[]))
    assert await getattr(service, method)() == []
    assert cache.await_args_list[0].args[0].endswith("visibility-v1:production")
