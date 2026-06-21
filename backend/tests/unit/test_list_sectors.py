"""Unit tests for list_sectors() and GET /api/sectors.

Mocks FirestoreService.stream_documents_projected and cache so no real Firebase
connection is needed.  Mirrors the pattern of test_sector_exposure_endpoint.py.
"""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.podcast import PodcastService


# ── Helpers ──────────────────────────────────────────────────────────────────

def _ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


NOW_MS = _ms(datetime(2026, 6, 19, 12, 0, 0))


def _doc(
    episode_id: str,
    podcast_name: str = "Gooaye 股癌",
    exposures: list | None = None,
    released_at_ms: int | None = None,
    retracted_at=None,
) -> dict:
    """Minimal raw Firestore episode dict for list_sectors tests."""
    if exposures is None:
        exposures = [
            {
                "exposure_id": "sector_passive_components",
                "exposure_type": "sector",
                "display_name": "被動元件",
                "resolved_tickers": [],
                "confidence": 1.0,
            }
        ]
    doc = {
        "id": episode_id,
        "podcast_name": podcast_name,
        "episode_title": f"Episode {episode_id}",
        "created_time": NOW_MS - 3600_000,
        "released_at_ms": released_at_ms if released_at_ms is not None else NOW_MS,
        "summary_content": "摘要內容",
        "key_insights": [],
        "sector_exposure_ids": [e["exposure_id"] for e in exposures],
        "sector_exposures": exposures,
        "tags": [],
        "related_tickers": [],
    }
    if retracted_at is not None:
        doc["retracted_at"] = retracted_at
    return doc


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_returns_sectors_sorted_by_count_desc():
    """Sectors appear sorted by episode count descending."""
    docs = [
        _doc("ep-001", exposures=[
            {"exposure_id": "sector_ai", "exposure_type": "theme", "display_name": "AI", "resolved_tickers": []},
        ]),
        _doc("ep-002", exposures=[
            {"exposure_id": "sector_ai", "exposure_type": "theme", "display_name": "AI", "resolved_tickers": []},
        ]),
        _doc("ep-003", exposures=[
            {"exposure_id": "sector_passive_components", "exposure_type": "sector", "display_name": "被動元件", "resolved_tickers": []},
        ]),
    ]

    mock_fs = MagicMock()
    mock_fs.stream_documents_projected.return_value = docs
    svc = PodcastService(firestore_service=mock_fs)

    with (
        patch("src.services.podcast.cache_get", new=AsyncMock(return_value=None)),
        patch("src.services.podcast.cache_set", new=AsyncMock()),
        patch.object(svc, "_allowed_podcast_names", new=AsyncMock(return_value=None)),
    ):
        result = await svc.list_sectors()

    assert len(result) == 2
    assert result[0]["exposure_id"] == "sector_ai"
    assert result[0]["count"] == 2
    assert result[1]["exposure_id"] == "sector_passive_components"
    assert result[1]["count"] == 1


@pytest.mark.asyncio
async def test_same_count_sorts_by_exposure_id_asc():
    """When two sectors have equal counts they are sorted by exposure_id ascending."""
    docs = [
        _doc("ep-001", exposures=[
            {"exposure_id": "sector_z", "exposure_type": "sector", "display_name": "Z", "resolved_tickers": []},
        ]),
        _doc("ep-002", exposures=[
            {"exposure_id": "sector_a", "exposure_type": "sector", "display_name": "A", "resolved_tickers": []},
        ]),
    ]

    mock_fs = MagicMock()
    mock_fs.stream_documents_projected.return_value = docs
    svc = PodcastService(firestore_service=mock_fs)

    with (
        patch("src.services.podcast.cache_get", new=AsyncMock(return_value=None)),
        patch("src.services.podcast.cache_set", new=AsyncMock()),
        patch.object(svc, "_allowed_podcast_names", new=AsyncMock(return_value=None)),
    ):
        result = await svc.list_sectors()

    ids = [r["exposure_id"] for r in result]
    assert ids == ["sector_a", "sector_z"]


@pytest.mark.asyncio
async def test_retracted_docs_excluded():
    """Documents with a truthy retracted_at are not counted."""
    docs = [
        _doc("ep-good"),
        _doc("ep-bad", retracted_at=NOW_MS - 1000),
    ]

    mock_fs = MagicMock()
    mock_fs.stream_documents_projected.return_value = docs
    svc = PodcastService(firestore_service=mock_fs)

    with (
        patch("src.services.podcast.cache_get", new=AsyncMock(return_value=None)),
        patch("src.services.podcast.cache_set", new=AsyncMock()),
        patch.object(svc, "_allowed_podcast_names", new=AsyncMock(return_value=None)),
    ):
        result = await svc.list_sectors()

    assert len(result) == 1
    assert result[0]["count"] == 1


@pytest.mark.asyncio
async def test_out_of_scope_podcast_excluded():
    """Docs whose podcast_name is not in the allowlist are skipped."""
    docs = [
        _doc("ep-tw", podcast_name="Gooaye 股癌"),
        _doc("ep-en", podcast_name="CNBC Fast Money"),
    ]

    mock_fs = MagicMock()
    mock_fs.stream_documents_projected.return_value = docs
    svc = PodcastService(firestore_service=mock_fs)
    allowed = frozenset({"Gooaye 股癌"})

    with (
        patch("src.services.podcast.cache_get", new=AsyncMock(return_value=None)),
        patch("src.services.podcast.cache_set", new=AsyncMock()),
        patch.object(svc, "_allowed_podcast_names", new=AsyncMock(return_value=allowed)),
    ):
        result = await svc.list_sectors()

    assert len(result) == 1
    assert result[0]["count"] == 1


@pytest.mark.asyncio
async def test_display_name_and_exposure_type_from_first_seen():
    """display_name and exposure_type are taken from the first-seen entry per exposure_id."""
    exposures = [
        {"exposure_id": "sector_passive_components", "exposure_type": "sector", "display_name": "被動元件", "resolved_tickers": []},
    ]
    docs = [_doc(f"ep-{i}", exposures=exposures) for i in range(3)]

    mock_fs = MagicMock()
    mock_fs.stream_documents_projected.return_value = docs
    svc = PodcastService(firestore_service=mock_fs)

    with (
        patch("src.services.podcast.cache_get", new=AsyncMock(return_value=None)),
        patch("src.services.podcast.cache_set", new=AsyncMock()),
        patch.object(svc, "_allowed_podcast_names", new=AsyncMock(return_value=None)),
    ):
        result = await svc.list_sectors()

    assert len(result) == 1
    assert result[0]["display_name"] == "被動元件"
    assert result[0]["exposure_type"] == "sector"
    assert result[0]["count"] == 3


@pytest.mark.asyncio
async def test_empty_when_no_episodes():
    """Empty Firestore result yields an empty sectors list."""
    mock_fs = MagicMock()
    mock_fs.stream_documents_projected.return_value = []
    svc = PodcastService(firestore_service=mock_fs)

    with (
        patch("src.services.podcast.cache_get", new=AsyncMock(return_value=None)),
        patch("src.services.podcast.cache_set", new=AsyncMock()),
        patch.object(svc, "_allowed_podcast_names", new=AsyncMock(return_value=None)),
    ):
        result = await svc.list_sectors()

    assert result == []


@pytest.mark.asyncio
async def test_response_shape_has_required_keys():
    """Each item in the result has the required keys (incl. display visuals)."""
    docs = [_doc("ep-001")]
    mock_fs = MagicMock()
    mock_fs.stream_documents_projected.return_value = docs
    svc = PodcastService(firestore_service=mock_fs)

    with (
        patch("src.services.podcast.cache_get", new=AsyncMock(return_value=None)),
        patch("src.services.podcast.cache_set", new=AsyncMock()),
        patch.object(svc, "_allowed_podcast_names", new=AsyncMock(return_value=None)),
    ):
        result = await svc.list_sectors()

    assert len(result) == 1
    item = result[0]
    assert set(item.keys()) == {
        "exposure_id", "display_name", "exposure_type", "icon_id", "color_hex", "count",
    }
