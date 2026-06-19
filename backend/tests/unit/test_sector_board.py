"""Unit tests for sector_board() and GET /api/sectors/board.

Mocks FirestoreService.get_all_documents, get_eod_change_pct, and cache so
no real Firebase or DB connection is needed.  Mirrors the pattern established
in test_list_sectors.py.
"""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.podcast import PodcastService


# ── Helpers ───────────────────────────────────────────────────────────────────

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
    """Minimal raw Firestore episode dict for sector_board tests."""
    if exposures is None:
        exposures = [
            {
                "exposure_id": "sector_passive_components",
                "exposure_type": "sector",
                "display_name": "被動元件",
                "resolved_tickers": [
                    {"ticker": "2327", "name": "國巨", "market": "TW", "source": "curated"},
                ],
                "confidence": 1.0,
            }
        ]
    doc: dict = {
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


# Convenience: build a PodcastService with a mock Firestore and patch cache + prices
def _make_svc(docs: list, price_map: dict | None = None) -> tuple:
    """Return (svc, price_map) ready for use inside a `with patch(...)` block."""
    mock_fs = MagicMock()
    mock_fs.get_all_documents.return_value = docs
    svc = PodcastService(firestore_service=mock_fs)
    if price_map is None:
        price_map = {}
    return svc, price_map


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_members_carry_change_percent():
    """Members include the mocked change_percent from get_eod_change_pct."""
    docs = [_doc("ep-001")]
    svc, _ = _make_svc(docs)

    async def _fake_eod(ticker: str):
        return {"2327": 1.5}.get(ticker)

    with (
        patch("src.services.podcast.cache_get", new=AsyncMock(return_value=None)),
        patch("src.services.podcast.cache_set", new=AsyncMock()),
        patch.object(svc, "_allowed_podcast_names", new=AsyncMock(return_value=None)),
        patch("src.services.stock_close_refresh.get_eod_change_pct", side_effect=_fake_eod),
    ):
        result = await svc.sector_board()

    assert len(result) == 1
    members = result[0]["members"]
    assert len(members) == 1
    assert members[0]["ticker"] == "2327"
    assert members[0]["change_percent"] == pytest.approx(1.5)


@pytest.mark.asyncio
async def test_avg_change_is_mean_of_non_null():
    """avg_change is the arithmetic mean of non-null member change_percent values."""
    exposures = [
        {
            "exposure_id": "sector_ai",
            "exposure_type": "theme",
            "display_name": "AI",
            "resolved_tickers": [
                {"ticker": "NVDA", "name": "NVIDIA", "market": "US", "source": "curated"},
                {"ticker": "AMD", "name": "AMD", "market": "US", "source": "curated"},
                {"ticker": "INTC", "name": "Intel", "market": "US", "source": "curated"},
            ],
        }
    ]
    docs = [_doc("ep-001", exposures=exposures)]
    svc, _ = _make_svc(docs)

    prices = {"NVDA": 3.0, "AMD": 1.0, "INTC": None}

    async def _fake_eod(ticker: str):
        return prices.get(ticker)

    with (
        patch("src.services.podcast.cache_get", new=AsyncMock(return_value=None)),
        patch("src.services.podcast.cache_set", new=AsyncMock()),
        patch.object(svc, "_allowed_podcast_names", new=AsyncMock(return_value=None)),
        patch("src.services.stock_close_refresh.get_eod_change_pct", side_effect=_fake_eod),
    ):
        result = await svc.sector_board()

    assert len(result) == 1
    # mean of 3.0 and 1.0 (INTC is None, excluded)
    assert result[0]["avg_change"] == pytest.approx(2.0)


@pytest.mark.asyncio
async def test_avg_change_none_when_all_prices_unavailable():
    """avg_change is None when no member has a price."""
    docs = [_doc("ep-001")]
    svc, _ = _make_svc(docs)

    async def _fake_eod(ticker: str):
        return None

    with (
        patch("src.services.podcast.cache_get", new=AsyncMock(return_value=None)),
        patch("src.services.podcast.cache_set", new=AsyncMock()),
        patch.object(svc, "_allowed_podcast_names", new=AsyncMock(return_value=None)),
        patch("src.services.stock_close_refresh.get_eod_change_pct", side_effect=_fake_eod),
    ):
        result = await svc.sector_board()

    assert result[0]["avg_change"] is None


@pytest.mark.asyncio
async def test_sectors_ordered_by_hotness_desc():
    """Sectors are sorted by hotness DESC (higher = first)."""
    # Two sectors: sector_ai has more episodes (higher mention score) AND higher avg_change.
    # It must appear first.
    exposures_ai = [
        {
            "exposure_id": "sector_ai",
            "exposure_type": "theme",
            "display_name": "AI",
            "resolved_tickers": [
                {"ticker": "NVDA", "name": "NVIDIA", "market": "US", "source": "curated"},
            ],
        }
    ]
    exposures_hw = [
        {
            "exposure_id": "sector_hardware",
            "exposure_type": "sector",
            "display_name": "Hardware",
            "resolved_tickers": [
                {"ticker": "AMD", "name": "AMD", "market": "US", "source": "curated"},
            ],
        }
    ]
    docs = [
        _doc("ep-001", exposures=exposures_ai),
        _doc("ep-002", exposures=exposures_ai),
        _doc("ep-003", exposures=exposures_hw),
    ]
    svc, _ = _make_svc(docs)

    prices = {"NVDA": 5.0, "AMD": -1.0}

    async def _fake_eod(ticker: str):
        return prices.get(ticker)

    with (
        patch("src.services.podcast.cache_get", new=AsyncMock(return_value=None)),
        patch("src.services.podcast.cache_set", new=AsyncMock()),
        patch.object(svc, "_allowed_podcast_names", new=AsyncMock(return_value=None)),
        patch("src.services.stock_close_refresh.get_eod_change_pct", side_effect=_fake_eod),
    ):
        result = await svc.sector_board()

    assert len(result) == 2
    assert result[0]["exposure_id"] == "sector_ai"
    assert result[1]["exposure_id"] == "sector_hardware"
    # Hotness must be in descending order
    assert result[0]["hotness"] >= result[1]["hotness"]


@pytest.mark.asyncio
async def test_members_sorted_change_percent_desc_none_last():
    """Members within a sector are sorted by change_percent DESC, None values last."""
    exposures = [
        {
            "exposure_id": "sector_tech",
            "exposure_type": "sector",
            "display_name": "Tech",
            "resolved_tickers": [
                {"ticker": "A", "name": "A Corp", "market": "US", "source": "curated"},
                {"ticker": "B", "name": "B Corp", "market": "US", "source": "curated"},
                {"ticker": "C", "name": "C Corp", "market": "US", "source": "curated"},
            ],
        }
    ]
    docs = [_doc("ep-001", exposures=exposures)]
    svc, _ = _make_svc(docs)

    prices = {"A": 1.0, "B": None, "C": 3.0}

    async def _fake_eod(ticker: str):
        return prices.get(ticker)

    with (
        patch("src.services.podcast.cache_get", new=AsyncMock(return_value=None)),
        patch("src.services.podcast.cache_set", new=AsyncMock()),
        patch.object(svc, "_allowed_podcast_names", new=AsyncMock(return_value=None)),
        patch("src.services.stock_close_refresh.get_eod_change_pct", side_effect=_fake_eod),
    ):
        result = await svc.sector_board()

    members = result[0]["members"]
    tickers_in_order = [m["ticker"] for m in members]
    assert tickers_in_order == ["C", "A", "B"]  # 3.0, 1.0, None


@pytest.mark.asyncio
async def test_retracted_and_out_of_scope_excluded():
    """Retracted docs and out-of-allowlist podcast docs are not counted."""
    docs = [
        _doc("ep-good", podcast_name="Gooaye 股癌"),
        _doc("ep-bad-retracted", retracted_at=NOW_MS - 1000),
        _doc("ep-bad-scope", podcast_name="English Podcast"),
    ]
    svc, _ = _make_svc(docs)
    allowed = frozenset({"Gooaye 股癌"})

    async def _fake_eod(ticker: str):
        return None

    with (
        patch("src.services.podcast.cache_get", new=AsyncMock(return_value=None)),
        patch("src.services.podcast.cache_set", new=AsyncMock()),
        patch.object(svc, "_allowed_podcast_names", new=AsyncMock(return_value=allowed)),
        patch("src.services.stock_close_refresh.get_eod_change_pct", side_effect=_fake_eod),
    ):
        result = await svc.sector_board()

    assert len(result) == 1
    assert result[0]["episode_count"] == 1


@pytest.mark.asyncio
async def test_empty_when_no_docs():
    """Empty Firestore result yields an empty board."""
    svc, _ = _make_svc([])

    with (
        patch("src.services.podcast.cache_get", new=AsyncMock(return_value=None)),
        patch("src.services.podcast.cache_set", new=AsyncMock()),
        patch.object(svc, "_allowed_podcast_names", new=AsyncMock(return_value=None)),
        patch("src.services.stock_close_refresh.get_eod_change_pct", new=AsyncMock(return_value=None)),
    ):
        result = await svc.sector_board()

    assert result == []


@pytest.mark.asyncio
async def test_hotness_between_zero_and_one():
    """All hotness values are in [0, 1]."""
    exposures_a = [
        {
            "exposure_id": "sector_a",
            "exposure_type": "sector",
            "display_name": "A",
            "resolved_tickers": [
                {"ticker": "X", "name": "X Co", "market": "US", "source": "curated"},
            ],
        }
    ]
    exposures_b = [
        {
            "exposure_id": "sector_b",
            "exposure_type": "sector",
            "display_name": "B",
            "resolved_tickers": [
                {"ticker": "Y", "name": "Y Co", "market": "US", "source": "curated"},
            ],
        }
    ]
    docs = [
        _doc("ep-001", exposures=exposures_a),
        _doc("ep-002", exposures=exposures_a),
        _doc("ep-003", exposures=exposures_b),
    ]
    svc, _ = _make_svc(docs)

    prices = {"X": 2.5, "Y": -0.5}

    async def _fake_eod(ticker: str):
        return prices.get(ticker)

    with (
        patch("src.services.podcast.cache_get", new=AsyncMock(return_value=None)),
        patch("src.services.podcast.cache_set", new=AsyncMock()),
        patch.object(svc, "_allowed_podcast_names", new=AsyncMock(return_value=None)),
        patch("src.services.stock_close_refresh.get_eod_change_pct", side_effect=_fake_eod),
    ):
        result = await svc.sector_board()

    for s in result:
        assert 0.0 <= s["hotness"] <= 1.0
