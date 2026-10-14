"""Invariant-gap: regeneration clears current scoped insight views, not other shows/scopes."""
import asyncio

import pytest
from fnmatch import fnmatchcase
from unittest.mock import AsyncMock

from src.services import podcast
from src.services.insight_service import _scope_tag


def test_invalidation_matches_current_keys_and_preserves_unrelated(monkeypatch):
    scope = _scope_tag()
    keys = {
        f'ticker_insights:by_ticker:{scope}:AMZN:2026-10-01:2026-10-14',
        f'ticker_insights:by_podcaster:v2:{scope}:曼報:2026-10-01:2026-10-14',
        f'ticker_insights:recent:v2:{scope}:20:now',
        f'ticker_insights:trending:{scope}:7:20',
    }
    unrelated = {f'ticker_insights:by_podcaster:v2:{scope}:other:2026-10-01:2026-10-14', 'ticker_insights:recent:v2:other-scope:20:now', 'stock:AMZN:price'}
    remaining = keys | unrelated

    async def delete(pattern):
        remaining.difference_update(key for key in list(remaining) if fnmatchcase(key, pattern))

    monkeypatch.setattr(podcast, 'cache_delete_pattern', AsyncMock(side_effect=delete))
    asyncio.run(podcast.PodcastService._invalidate_ticker_insight_cache(None, '曼報'))
    assert remaining == unrelated


@pytest.mark.asyncio
async def test_cache_only_patch_never_rewrites_content():
    from types import SimpleNamespace
    from unittest.mock import Mock
    service = SimpleNamespace(
        firestore_service=SimpleNamespace(get_document=Mock(return_value={'podcast_name': 'show'})),
        _write_episode_fields=AsyncMock(),
        _invalidate_episode_cache=AsyncMock(),
        _invalidate_ticker_insight_cache=AsyncMock(),
        _purge_api_host_cdn=AsyncMock(),
        get_episode_by_id=AsyncMock(return_value={'id': 'ep'}),
    )
    assert await podcast.PodcastService.patch_episode_fields(service, 'show', 'ep', {'invalidate_caches': True}) == {'id': 'ep'}
    service._write_episode_fields.assert_not_awaited()
    service._invalidate_episode_cache.assert_awaited_once_with('show', 'ep')
    service._invalidate_ticker_insight_cache.assert_awaited_once_with('show')
    service._purge_api_host_cdn.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize('updates', [{}, {'invalidate_caches': False}, {'invalidate_caches': 'true'}])
async def test_empty_or_invalid_cache_patch_rejected(updates):
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as error:
        await podcast.PodcastService.patch_episode_fields(None, 'show', 'ep', updates)
    assert error.value.status_code == 422
