"""Unit tests for GET /api/episodes/by-sector/{exposure_id}.

Tests the pure service-layer helper get_episodes_by_sector by mocking
FirestoreService.query_collection (and cache) so no real Firebase connection
is needed.
"""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.podcast import Episode
from src.services.podcast import PodcastService


# ── Fixtures ────────────────────────────────────────────────────────────

def _ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


NOW_MS = _ms(datetime(2026, 6, 19, 12, 0, 0))


def _raw_doc(
    episode_id: str,
    podcast_name: str = "Gooaye 股癌",
    exposure_id: str = "sector_passive_components",
    display_name: str = "被動元件",
    exposure_type: str = "sector",
    tickers: list | None = None,
    released_at_ms: int | None = None,
    summary_content: str = "摘要內容",
) -> dict:
    """Minimal raw Firestore episode dict."""
    if tickers is None:
        tickers = [{"ticker": "2327", "name": "國巨", "name_en": None, "market": "TW", "source": "curated"}]
    return {
        "id": episode_id,
        "podcast_name": podcast_name,
        "episode_title": f"Episode {episode_id}",
        "created_time": NOW_MS - 3600_000,
        "released_at_ms": released_at_ms or NOW_MS,
        "summary_content": summary_content,
        "key_insights": ["insight A"],
        "sector_exposure_ids": [exposure_id],
        "sector_exposures": [
            {
                "exposure_id": exposure_id,
                "exposure_type": exposure_type,
                "display_name": display_name,
                "resolved_tickers": tickers,
                "confidence": 1.0,
                "total_matches": 2,
            }
        ],
        "tags": [],
        "related_tickers": [],
    }


# ── Tests ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_empty_result_returns_defaults():
    """No matching episodes -> 200 with empty lists and display_name == exposure_id."""
    mock_fs = MagicMock()
    mock_fs.query_collection.return_value = []

    svc = PodcastService(firestore_service=mock_fs)

    with (
        patch("src.services.podcast.cache_get", new=AsyncMock(return_value=None)),
        patch("src.services.podcast.cache_set", new=AsyncMock()),
        patch.object(svc, "_allowed_podcast_names", new=AsyncMock(return_value=None)),
    ):
        result = await svc.get_episodes_by_sector("sector_unknown")

    assert result["exposure_id"] == "sector_unknown"
    assert result["display_name"] == "sector_unknown"
    assert result["exposure_type"] == "sector"
    assert result["resolved_tickers"] == []
    assert result["episodes"] == []
    assert result["total"] == 0


@pytest.mark.asyncio
async def test_returns_matched_episodes_and_metadata():
    """Matching episodes yield correct display_name, exposure_type, and tickers."""
    doc1 = _raw_doc("ep-001", tickers=[
        {"ticker": "2327", "name": "國巨", "name_en": None, "market": "TW", "source": "curated"},
    ])
    doc2 = _raw_doc("ep-002", tickers=[
        {"ticker": "2327", "name": "國巨", "name_en": None, "market": "TW", "source": "curated"},
        {"ticker": "2330", "name": "台積電", "name_en": "TSMC", "market": "TW", "source": "curated"},
    ])

    mock_fs = MagicMock()
    mock_fs.query_collection.return_value = [doc1, doc2]

    svc = PodcastService(firestore_service=mock_fs)

    with (
        patch("src.services.podcast.cache_get", new=AsyncMock(return_value=None)),
        patch("src.services.podcast.cache_set", new=AsyncMock()),
        patch.object(svc, "_allowed_podcast_names", new=AsyncMock(return_value=None)),
    ):
        result = await svc.get_episodes_by_sector("sector_passive_components")

    assert result["display_name"] == "被動元件"
    assert result["exposure_type"] == "sector"
    assert len(result["episodes"]) == 2
    assert result["total"] == 2

    tickers = {t["ticker"] for t in result["resolved_tickers"]}
    assert tickers == {"2327", "2330"}


@pytest.mark.asyncio
async def test_deduplicates_tickers_preserving_first_seen_order():
    """Ticker seen in multiple episodes appears only once, in first-seen order."""
    doc1 = _raw_doc("ep-001", tickers=[
        {"ticker": "2327", "name": "國巨", "name_en": None, "market": "TW", "source": "curated"},
    ])
    doc2 = _raw_doc("ep-002", tickers=[
        {"ticker": "2327", "name": "國巨", "name_en": None, "market": "TW", "source": "curated"},
        {"ticker": "2330", "name": "台積電", "name_en": "TSMC", "market": "TW", "source": "curated"},
    ])

    mock_fs = MagicMock()
    mock_fs.query_collection.return_value = [doc1, doc2]

    svc = PodcastService(firestore_service=mock_fs)

    with (
        patch("src.services.podcast.cache_get", new=AsyncMock(return_value=None)),
        patch("src.services.podcast.cache_set", new=AsyncMock()),
        patch.object(svc, "_allowed_podcast_names", new=AsyncMock(return_value=None)),
    ):
        result = await svc.get_episodes_by_sector("sector_passive_components")

    ticker_list = [t["ticker"] for t in result["resolved_tickers"]]
    assert ticker_list == ["2327", "2330"]  # 2327 first, no duplicate


@pytest.mark.asyncio
async def test_release_scope_applied():
    """Episodes outside the language allowlist are excluded."""
    doc_tw = _raw_doc("ep-tw", podcast_name="Gooaye 股癌")
    doc_en = _raw_doc("ep-en", podcast_name="CNBC Fast Money")

    mock_fs = MagicMock()
    mock_fs.query_collection.return_value = [doc_tw, doc_en]

    svc = PodcastService(firestore_service=mock_fs)
    allowed = frozenset({"Gooaye 股癌"})

    with (
        patch("src.services.podcast.cache_get", new=AsyncMock(return_value=None)),
        patch("src.services.podcast.cache_set", new=AsyncMock()),
        patch.object(svc, "_allowed_podcast_names", new=AsyncMock(return_value=allowed)),
    ):
        result = await svc.get_episodes_by_sector("sector_passive_components")

    assert result["total"] == 1
    assert result["episodes"][0]["podcast_name"] == "Gooaye 股癌"


@pytest.mark.asyncio
async def test_firestore_query_uses_array_contains():
    """query_collection is called with the array-contains filter on sector_exposure_ids."""
    mock_fs = MagicMock()
    mock_fs.query_collection.return_value = []

    svc = PodcastService(firestore_service=mock_fs)

    with (
        patch("src.services.podcast.cache_get", new=AsyncMock(return_value=None)),
        patch("src.services.podcast.cache_set", new=AsyncMock()),
        patch.object(svc, "_allowed_podcast_names", new=AsyncMock(return_value=None)),
    ):
        await svc.get_episodes_by_sector("sector_passive_components", limit=20, offset=0)

    mock_fs.query_collection.assert_called_once()
    call_args = mock_fs.query_collection.call_args
    collection_arg = call_args[0][0]
    filters_arg = call_args[0][1]
    assert collection_arg == "episodes"
    assert any(
        f[0] == "sector_exposure_ids" and f[1] == "array-contains" and f[2] == "sector_passive_components"
        for f in filters_arg
    )


@pytest.mark.asyncio
async def test_pagination_offset_and_limit():
    """offset and limit slice the scoped episode list correctly."""
    docs = [_raw_doc(f"ep-{i:03d}") for i in range(10)]

    mock_fs = MagicMock()
    mock_fs.query_collection.return_value = docs

    svc = PodcastService(firestore_service=mock_fs)

    with (
        patch("src.services.podcast.cache_get", new=AsyncMock(return_value=None)),
        patch("src.services.podcast.cache_set", new=AsyncMock()),
        patch.object(svc, "_allowed_podcast_names", new=AsyncMock(return_value=None)),
    ):
        result = await svc.get_episodes_by_sector("sector_passive_components", limit=3, offset=2)

    # total = full matched count (for pagination); episodes = this page slice.
    assert result["total"] == 10
    assert len(result["episodes"]) == 3
