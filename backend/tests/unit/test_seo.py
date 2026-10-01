"""Unit tests for SEO: dynamic sitemap generation + Search Console config gating."""
from datetime import datetime

import pytest

from src.config import settings
from src.models.podcast import Episode
from src.routers import seo
from src.services.search_console_service import SearchConsoleService, _row


def _ep(ep_id: str, tickers: list[str] | None = None, tags: list[str] | None = None) -> Episode:
    return Episode(
        id=ep_id,
        podcast_name="股癌",
        episode_title="重點",
        created_time=int(datetime.utcnow().timestamp() * 1000),
        related_tickers=tickers or [],
        tags=tags or [],
    )


@pytest.fixture(autouse=True)
def _no_insight_store(monkeypatch):
    """No test here may reach the content store for insight counts; the ones that care
    about the stock floor install their own counts."""
    async def _unavailable(*args, **kwargs):
        raise RuntimeError("insight store not available in unit tests")

    monkeypatch.setattr(seo.insight_service, "free_insight_counts", _unavailable)


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
    assert "<loc>https://tinboker.com/articles</loc>" not in body
    # + 1: the /weekly page for the week both episodes fall in
    assert body.count("<url>") == len(seo.STATIC_PATHS) + 2 + 1


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


@pytest.mark.asyncio
async def test_sitemap_lists_visible_sectors_and_skips_hidden_tags(monkeypatch):
    """Sector pages ship; admin-hidden sectors and tags stay out.

    Sector pages were absent from the sitemap entirely, which is why they never got
    indexed. The two exclusions matter as much as the inclusion: the site hides those
    from its own listings, so a crawler that follows them lands on an empty page.
    """
    async def _no_episodes(*args, **kwargs):
        return []

    async def _sectors(*args, **kwargs):
        return [
            {"exposure_id": "sector_mlcc", "count": 12},
            {"exposure_id": "sector_retired", "count": 40},
            {"exposure_id": "sector_thin", "count": 1},  # served, but one episode is not a page
        ]

    async def _tags(*args, **kwargs):
        return [{"id": "ai"}, {"id": "junk_tag"}]

    monkeypatch.setattr(seo.podcast_service, "get_recent_episodes", _no_episodes)
    monkeypatch.setattr(seo.podcast_service, "list_sectors", _sectors)
    monkeypatch.setattr(seo.podcast_service, "get_all_tags", _tags)
    monkeypatch.setattr(seo, "served_sector_exposure_ids", lambda db: {"sector_mlcc", "sector_thin"})
    monkeypatch.setattr(seo, "auto_register_sectors", lambda db, sectors: 0)
    monkeypatch.setattr(settings, "site_url", "https://tinboker.com")

    body = (await seo.sitemap(limit=10, db=object())).body.decode()

    assert "<loc>https://tinboker.com/sector/sector_mlcc</loc>" in body
    assert "sector_retired" not in body
    assert "sector_thin" not in body

    # With no episodes there are no tag pages to list; the /topics index stays.
    assert "/topics/" not in body
    assert "<loc>https://tinboker.com/topics</loc>" in body


@pytest.mark.asyncio
async def test_sitemap_lists_stock_pages_that_have_free_insights_to_show(monkeypatch):
    """/stock pages are listed on what the page renders, not on episode counts.

    A ticker can sit in three episodes' related_tickers and still have no readable 觀點
    (no insight row, or only paywalled ones) — a title and a footer. 19 such pages were
    in the sitemap on 2026-10-01.
    """
    async def _recent(*args, **kwargs):
        return [_ep("E1", ["2330", "NVDA", "6981"]), _ep("E2", ["2330", "6981"]), _ep("E3", ["2330", "6981"])]

    async def _free(*args, **kwargs):
        # 6981: discussed in three episodes, nothing readable. 9999: readable rows but
        # outside the scoped episode list, so it has no live episode to link to.
        return {"2330": 5, "NVDA": seo.MIN_STOCK_INSIGHTS - 1, "9999": 8}

    monkeypatch.setattr(seo.podcast_service, "get_recent_episodes", _recent)
    monkeypatch.setattr(seo.insight_service, "free_insight_counts", _free)
    monkeypatch.setattr(settings, "site_url", "https://tinboker.com")

    body = (await seo.sitemap(limit=1000)).body.decode()

    assert "<loc>https://tinboker.com/stock/2330</loc>" in body
    for thin in ("/stock/NVDA", "/stock/6981", "/stock/9999"):
        assert thin not in body
    # 3 episodes + 1 stock page + 1 weekly page
    assert body.count("<url>") == len(seo.STATIC_PATHS) + 3 + 1 + 1


@pytest.mark.asyncio
async def test_sitemap_falls_back_to_the_episode_floor_when_insights_are_unavailable(monkeypatch):
    """A failed insight query must not empty the sitemap of stock pages for an hour."""
    async def _recent(*args, **kwargs):
        return [_ep("E1", ["2330", "NVDA"]), _ep("E2", ["2330"])]

    async def _boom(*args, **kwargs):
        raise RuntimeError("mirror down")

    monkeypatch.setattr(seo.podcast_service, "get_recent_episodes", _recent)
    monkeypatch.setattr(seo.insight_service, "free_insight_counts", _boom)
    monkeypatch.setattr(settings, "site_url", "https://tinboker.com")

    body = (await seo.sitemap(limit=1000)).body.decode()

    assert "<loc>https://tinboker.com/stock/2330</loc>" in body
    assert "/stock/NVDA" not in body


@pytest.mark.asyncio
async def test_sitemap_lists_tags_above_the_floor_and_the_weeks_with_episodes(monkeypatch):
    """A tag page is listed once >= MIN_TAG_EPISODES scoped episodes carry it; every
    week with a scoped episode gets its /weekly page."""
    async def _recent(*args, **kwargs):
        return [_ep(f"E{i}", tags=["ai"] + (["niche"] if i == 0 else [])) for i in range(5)]

    monkeypatch.setattr(seo.podcast_service, "get_recent_episodes", _recent)
    monkeypatch.setattr(settings, "site_url", "https://tinboker.com")

    body = (await seo.sitemap(limit=1000)).body.decode()

    assert "<loc>https://tinboker.com/topics/ai</loc>" in body
    assert "/topics/niche" not in body
    assert "<loc>https://tinboker.com/weekly</loc>" in body
    assert body.count("<loc>https://tinboker.com/weekly/20") == 1
