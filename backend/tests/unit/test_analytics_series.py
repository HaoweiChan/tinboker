"""The analytics trend charts depend on per-day `series` being exposed by the GSC and
Facebook services (the data was already fetched but previously summed away). These pin
the series extraction so a refactor can't silently drop it.
"""
from src.services.facebook_insights_service import FacebookInsightsService
from src.services.search_console_service import SearchConsoleService


async def test_gsc_overview_exposes_sorted_daily_series(monkeypatch):
    svc = SearchConsoleService(site_url="sc-domain:example.com")

    async def fake_query(self, start, end, dimensions, row_limit=25):
        if dimensions == ["date"]:
            return [  # intentionally out of order — overview must sort ascending
                {"keys": ["2026-06-02"], "clicks": 5, "impressions": 50},
                {"keys": ["2026-06-01"], "clicks": 3, "impressions": 30},
            ]
        return []  # top queries / pages unused here

    monkeypatch.setattr(SearchConsoleService, "query", fake_query)
    data = await svc.overview(days=7)

    assert data["totals"]["clicks"] == 8
    assert [r["date"] for r in data["series"]] == ["2026-06-01", "2026-06-02"]
    assert data["series"][0] == {"date": "2026-06-01", "clicks": 3, "impressions": 30}


async def test_fb_summary_merges_daily_values_into_series(monkeypatch):
    svc = FacebookInsightsService(page_id="123", access_token="tok")

    async def fake_get(self, client, path, params):
        if path == "123":  # Page node (audience counts)
            return {"name": "P", "fan_count": 10, "followers_count": 12}
        return {  # insights, period=day
            "data": [
                {"name": "page_views_total", "values": [
                    {"value": 4, "end_time": "2026-06-01T07:00:00+0000"},
                    {"value": 6, "end_time": "2026-06-02T07:00:00+0000"},
                ]},
                {"name": "page_post_engagements", "values": [
                    {"value": 1, "end_time": "2026-06-01T07:00:00+0000"},
                    {"value": 2, "end_time": "2026-06-02T07:00:00+0000"},
                ]},
            ]
        }

    monkeypatch.setattr(FacebookInsightsService, "_get", fake_get)
    data = await svc.account_summary(days=7)

    assert data["followers"] == 12 and data["fans"] == 10
    assert data["metrics"]["page_views_total"] == 10  # summed total still works
    assert data["series"] == [
        {"date": "2026-06-01", "page_views_total": 4, "page_post_engagements": 1},
        {"date": "2026-06-02", "page_views_total": 6, "page_post_engagements": 2},
    ]
