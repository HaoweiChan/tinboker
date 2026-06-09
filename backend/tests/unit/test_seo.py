"""Unit tests for SEO: dynamic sitemap generation + Search Console config gating."""
from datetime import datetime

import pytest

from src.config import settings
from src.models.podcast import Episode
from src.routers import seo
from src.services.search_console_service import SearchConsoleService, _row


def _ep(ep_id: str) -> Episode:
    return Episode(
        id=ep_id,
        podcast_name="股癌",
        episode_title="重點",
        created_time=int(datetime.utcnow().timestamp() * 1000),
    )


@pytest.mark.asyncio
async def test_sitemap_lists_static_routes_and_episodes(monkeypatch):
    async def _fake_recent(*args, **kwargs):
        return [_ep("EP600"), _ep("EP601")]

    monkeypatch.setattr(seo.podcast_service, "get_recent_episodes", _fake_recent)
    monkeypatch.setattr(settings, "site_url", "https://tinboker.com")

    resp = await seo.sitemap(limit=1000)
    body = resp.body.decode()

    assert resp.media_type == "application/xml"
    assert body.startswith('<?xml version="1.0" encoding="UTF-8"?>')
    assert "<loc>https://tinboker.com/</loc>" in body
    assert "<loc>https://tinboker.com/episode/EP600</loc>" in body
    assert "<loc>https://tinboker.com/episode/EP601</loc>" in body
    assert body.count("<url>") == len(seo.STATIC_PATHS) + 2


@pytest.mark.asyncio
async def test_sitemap_survives_episode_fetch_failure(monkeypatch):
    async def _boom(*args, **kwargs):
        raise RuntimeError("firestore down")

    monkeypatch.setattr(seo.podcast_service, "get_recent_episodes", _boom)
    resp = await seo.sitemap(limit=1000)
    body = resp.body.decode()
    # Static routes still render; no 500 to Googlebot.
    assert "<loc>https://tinboker.com/</loc>" in body
    assert body.count("<url>") == len(seo.STATIC_PATHS)


def test_search_console_not_configured_without_site_url(monkeypatch):
    monkeypatch.setattr(settings, "gsc_site_url", None)
    assert SearchConsoleService().is_configured is False
    monkeypatch.setattr(settings, "gsc_site_url", "sc-domain:tinboker.com")
    assert SearchConsoleService().is_configured is True


def test_gsc_row_normalization():
    raw = {"keys": ["台積電"], "clicks": 12, "impressions": 340, "ctr": 0.0353, "position": 4.27}
    assert _row(raw) == {
        "key": "台積電",
        "clicks": 12,
        "impressions": 340,
        "ctr": 0.0353,
        "position": 4.3,
    }
