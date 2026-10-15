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


@pytest.mark.asyncio
async def test_clear_summary_image_clears_inline_and_both_urls_only():
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
    await podcast.PodcastService.patch_episode_fields(service, 'show', 'ep', {'clear_summary_image': True})
    service._write_episode_fields.assert_awaited_once_with('ep', {
        'summary_image': None, 'summary_image_url': None, 'summary_image_public_url': None,
    })
    service._invalidate_episode_cache.assert_awaited_once_with('show', 'ep')
    service._purge_api_host_cdn.assert_awaited_once()
    service._invalidate_ticker_insight_cache.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('updates', [
    {'clear_summary_image': 'true'}, {'clear_summary_image': 1},
    {'clear_summary_image': None}, {'clear_summary_image': False},
    {'summary_image_url': 'https://example.com/image.svg'},
    {'clear_summary_image': True, 'social_enabled': True},
])
async def test_image_cleanup_rejects_invalid_flags_and_unrelated_writes(updates):
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as error:
        await podcast.PodcastService.patch_episode_fields(None, 'show', 'ep', updates)
    assert error.value.status_code == 422


@pytest.mark.asyncio
async def test_image_cleanup_respects_episode_show_ownership():
    from types import SimpleNamespace
    from unittest.mock import Mock
    from fastapi import HTTPException
    service = SimpleNamespace(
        firestore_service=SimpleNamespace(get_document=Mock(return_value={'podcast_name': 'other'})),
        _write_episode_fields=AsyncMock(),
    )
    with pytest.raises(HTTPException) as error:
        await podcast.PodcastService.patch_episode_fields(service, 'show', 'ep', {'clear_summary_image': True})
    assert error.value.status_code == 404
    service._write_episode_fields.assert_not_awaited()
