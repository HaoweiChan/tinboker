import json
from unittest.mock import AsyncMock, patch

import pytest

from src.routers.tags import get_sectors_by_ticker


def _index() -> dict:
    return {
        "ticker_to_sectors": {
            "2330": {"sector_semiconductor_equipment", "sector_ai_hardware", "sector_hbm"},
        },
        "meta": {
            "sector_ai_hardware": {
                "display_name": "AI 硬體",
                "exposure_type": "industry",
                "icon_id": "cpu",
                "color_hex": "#3B82F6",
                "group": None,
                "description": "AI 伺服器與硬體供應鏈。",
            },
            "sector_hbm": {
                "display_name": "HBM",
                "exposure_type": "theme",
                "icon_id": "memory-stick",
                "color_hex": "#10B981",
                "group": "sector_ai_hardware",
                "description": "高頻寬記憶體題材。",
            },
            "sector_semiconductor_equipment": {
                "display_name": "半導體設備",
                "exposure_type": "theme",
                "icon_id": "factory",
                "color_hex": "#F59E0B",
                "group": "sector_semiconductor",
                "description": None,
            },
            "sector_hidden_redirect_source": {
                "display_name": "隱藏來源",
                "exposure_type": "theme",
                "icon_id": "hash",
                "color_hex": "#111111",
                "group": None,
                "description": "Hidden rows should not be reachable when the index filters them.",
            },
        },
    }


@pytest.mark.asyncio
async def test_sectors_by_ticker_returns_known_memberships_sorted_with_reasons():
    async_mock_set = AsyncMock()

    def _reason(exposure_id: str, ticker: str) -> str | None:
        return {
            ("sector_ai_hardware", "2330"): "台積電供應 AI 晶片製造所需先進製程。",
            ("sector_hbm", "2330"): "台積電受惠 HBM 周邊先進封裝需求。",
        }.get((exposure_id, ticker))

    with (
        patch("src.routers.tags.cache_get", new=AsyncMock(return_value=None)),
        patch("src.routers.tags.cache_set", new=async_mock_set),
        patch("src.routers.tags.PodcastService._sector_membership_index", return_value=_index()),
        patch("src.routers.tags.reason_for", side_effect=_reason),
    ):
        response = await get_sectors_by_ticker(" 2330 ")

    assert [item.exposure_id for item in response.items] == [
        "sector_ai_hardware",
        "sector_hbm",
        "sector_semiconductor_equipment",
    ]
    assert response.items[0].exposure_type == "industry"
    assert response.items[1].exposure_type == "theme"
    assert response.items[1].reason == "台積電受惠 HBM 周邊先進封裝需求。"
    assert response.items[2].reason == ""
    assert response.items[0].description == "AI 伺服器與硬體供應鏈。"

    assert async_mock_set.await_count == 1
    assert async_mock_set.await_args.args[0] == "sectors:by-ticker:v1:2330"
    assert async_mock_set.await_args.args[2] == 3600
    cached_payload = json.loads(async_mock_set.await_args.args[1])
    assert cached_payload["items"][0]["exposure_id"] == "sector_ai_hardware"


@pytest.mark.asyncio
async def test_sectors_by_ticker_unknown_ticker_returns_empty_200_shape():
    with (
        patch("src.routers.tags.cache_get", new=AsyncMock(return_value=None)),
        patch("src.routers.tags.cache_set", new=AsyncMock()),
        patch("src.routers.tags.PodcastService._sector_membership_index", return_value=_index()),
        patch("src.routers.tags.reason_for", return_value=None),
    ):
        response = await get_sectors_by_ticker("ZZZZ")

    assert response.items == []


@pytest.mark.asyncio
async def test_sectors_by_ticker_uses_cached_response():
    cached = {
        "items": [
            {
                "exposure_id": "sector_cached",
                "exposure_type": "theme",
                "display_name": "快取題材",
                "icon_id": None,
                "color_hex": None,
                "group": None,
                "reason": "",
                "description": None,
            }
        ]
    }

    with (
        patch("src.routers.tags.cache_get", new=AsyncMock(return_value=json.dumps(cached))),
        patch("src.routers.tags.cache_set", new=AsyncMock()) as cache_set_mock,
        patch("src.routers.tags.PodcastService._sector_membership_index") as index_mock,
    ):
        response = await get_sectors_by_ticker("2330")

    assert response.items[0].exposure_id == "sector_cached"
    index_mock.assert_not_called()
    cache_set_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_sectors_by_ticker_hidden_rows_do_not_leak_from_filtered_index():
    filtered_index = _index()
    filtered_index["ticker_to_sectors"] = {"2330": {"sector_hbm"}}

    with (
        patch("src.routers.tags.cache_get", new=AsyncMock(return_value=None)),
        patch("src.routers.tags.cache_set", new=AsyncMock()),
        patch("src.routers.tags.PodcastService._sector_membership_index", return_value=filtered_index),
        patch("src.routers.tags.reason_for", return_value=None),
    ):
        response = await get_sectors_by_ticker("2330")

    assert [item.exposure_id for item in response.items] == ["sector_hbm"]
    assert "sector_hidden_redirect_source" not in {item.exposure_id for item in response.items}
