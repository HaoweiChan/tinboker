"""Unit tests for sector_board() and GET /api/sectors/board.

Mocks FirestoreService.stream_documents_projected, get_eod_change_pct, and cache
so no real Firebase or DB connection is needed.  Mirrors the pattern established
in test_list_sectors.py.
"""
import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.podcast import PodcastService


def _patch_get_session(close_rows: list | None = None):
    """Patch get_session used inside _read_close_series to return fake DB rows.

    close_rows is a list of (ticker, date, close) tuples fed to the query mock.
    Pass None (default) for an empty result — series will be [] for all tickers.
    """
    if close_rows is None:
        close_rows = []

    mock_session = MagicMock()
    mock_query = MagicMock()
    mock_session.query.return_value = mock_query
    mock_query.filter.return_value = mock_query
    mock_query.order_by.return_value = mock_query
    mock_query.all.return_value = close_rows

    def _gen():
        yield mock_session

    return patch("src.services.podcast.get_session", side_effect=_gen)


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
    mock_fs.stream_documents_projected.return_value = docs
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
        _patch_get_session(),
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
        _patch_get_session(),
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
        _patch_get_session(),
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
        _patch_get_session(),
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
        _patch_get_session(),
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
        _patch_get_session(),
    ):
        result = await svc.sector_board()

    assert len(result) == 1
    assert result[0]["episode_count"] == 1


@pytest.mark.asyncio
async def test_excluded_exposure_dropped_from_board():
    """Suppressed umbrella exposures (e.g. sector_semiconductor) are not counted on
    the board even when episodes are stamped with them."""
    exposures = [
        {
            "exposure_id": "sector_semiconductor",
            "exposure_type": "sector",
            "display_name": "半導體",
            "resolved_tickers": [
                {"ticker": "2330", "name": "台積電", "market": "TW", "source": "curated"},
            ],
        },
        {
            "exposure_id": "sector_passive_components",
            "exposure_type": "sector",
            "display_name": "被動元件",
            "resolved_tickers": [
                {"ticker": "2327", "name": "國巨", "market": "TW", "source": "curated"},
            ],
        },
    ]
    docs = [_doc("ep-001", exposures=exposures)]
    svc, _ = _make_svc(docs)

    async def _fake_eod(ticker: str):
        return 1.0

    with (
        patch("src.services.podcast.cache_get", new=AsyncMock(return_value=None)),
        patch("src.services.podcast.cache_set", new=AsyncMock()),
        patch.object(svc, "_allowed_podcast_names", new=AsyncMock(return_value=None)),
        patch("src.services.stock_close_refresh.get_eod_change_pct", side_effect=_fake_eod),
        _patch_get_session(),
    ):
        result = await svc.sector_board()

    ids = {s["exposure_id"] for s in result}
    assert "sector_semiconductor" not in ids
    assert "sector_passive_components" in ids


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
        _patch_get_session(),
    ):
        result = await svc.sector_board()

    for s in result:
        assert 0.0 <= s["hotness"] <= 1.0


@pytest.mark.asyncio
async def test_member_and_sector_series_populated():
    """member.series carries last-12 closes; sector.series is the rebased aggregate."""
    docs = [_doc("ep-001")]
    svc, _ = _make_svc(docs)

    # Provide 5 daily closes for ticker 2327 (>= 2, so series is non-empty).
    closes_2327 = [100.0, 102.0, 101.0, 103.0, 105.0]
    close_rows = [("2327", f"2026-06-{14 + i:02d}", c) for i, c in enumerate(closes_2327)]

    async def _fake_eod(ticker: str):
        return {"2327": 2.0}.get(ticker)

    with (
        patch("src.services.podcast.cache_get", new=AsyncMock(return_value=None)),
        patch("src.services.podcast.cache_set", new=AsyncMock()),
        patch.object(svc, "_allowed_podcast_names", new=AsyncMock(return_value=None)),
        patch("src.services.stock_close_refresh.get_eod_change_pct", side_effect=_fake_eod),
        _patch_get_session(close_rows=close_rows),
    ):
        result = await svc.sector_board()

    assert len(result) == 1
    sector = result[0]

    # member series = the raw closes (all 5, within the 12-point cap)
    members = sector["members"]
    assert len(members) == 1
    assert members[0]["series"] == pytest.approx(closes_2327)

    # sector series = rebased to 100 at first close
    expected_sector_series = [c / closes_2327[0] * 100.0 for c in closes_2327]
    assert sector["series"] == pytest.approx(expected_sector_series)


# ── Refresh-ahead (warm cache off the request path) ─────────────────────────────

# ── Ticker-implied discussion heat (Phase 1) ───────────────────────────────────

_HEAT_INDEX = {
    # 3711 is a constituent of theme sector_hbm, whose parent industry is sector_ai_hardware.
    "ticker_to_sectors": {"3711": {"sector_hbm", "sector_ai_hardware"}},
    "attr_size": {"sector_hbm": 4, "sector_ai_hardware": 16},
    "meta": {
        "sector_hbm": {"display_name": "HBM", "exposure_type": "theme"},
        "sector_ai_hardware": {"display_name": "AI硬體", "exposure_type": "industry"},
    },
    "ticker_name": {"3711": "日月光"},
}


@pytest.mark.asyncio
async def test_ticker_implied_heat_and_parent_aggregation():
    """A NAMED mention feeds direct_heat; a CONSTITUENT mention (via related_tickers)
    feeds ticker_heat for the theme AND its parent industry. episode_count is the
    union, and heat blends the two with sub-linear size normalisation."""
    ep_named = _doc("ep-named", exposures=[{
        "exposure_id": "sector_hbm", "exposure_type": "theme", "display_name": "HBM",
        "resolved_tickers": [{"ticker": "3711", "name": "日月光", "market": "TW", "source": "curated"}],
    }])
    ep_ticker = _doc("ep-ticker", exposures=[])   # names no sector...
    ep_ticker["related_tickers"] = ["3711"]        # ...but mentions a constituent
    svc, _ = _make_svc([ep_named, ep_ticker])

    async def _fake_eod(ticker: str):
        return {"3711": 1.0}.get(ticker)

    with (
        patch("src.services.podcast.cache_get", new=AsyncMock(return_value=None)),
        patch("src.services.podcast.cache_set", new=AsyncMock()),
        patch.object(svc, "_allowed_podcast_names", new=AsyncMock(return_value=None)),
        patch.object(PodcastService, "_sector_membership_index", return_value=_HEAT_INDEX),
        patch("src.services.stock_close_refresh.get_eod_change_pct", side_effect=_fake_eod),
        # Freeze the decay clock to the docs' release time. The board decays heat against
        # wall-clock now (0.5^(age/7)), while these docs are pinned to a fixed NOW_MS — so
        # with a live clock the heat shrinks a little more every day and the components,
        # which the board rounds to 3 dp, lose precision RELATIVE to their own magnitude.
        # At ~25 days out that rounding error crossed the 2% rel tolerance below and the
        # test began flapping purely on what time CI happened to run (industry bucket:
        # 1.2% at 15:35Z → 2.4% at 17:37Z). Frozen, age=0 → weight=1.0 and every figure
        # here is exact, so this asserts the blend formula rather than the calendar.
        patch("time.time", return_value=NOW_MS / 1000),
        _patch_get_session(),
    ):
        result = await svc.sector_board()

    by_id = {s["exposure_id"]: s for s in result}
    assert set(by_id) == {"sector_hbm", "sector_ai_hardware"}

    hbm = by_id["sector_hbm"]
    ind = by_id["sector_ai_hardware"]

    # theme: named once (direct) + constituent once (ticker); union episode_count == 2
    assert hbm["direct_heat"] > 0 and hbm["ticker_heat"] > 0
    assert hbm["episode_count"] == 2
    # industry: never named, only implied via its child theme's constituent; count == 1
    assert ind["direct_heat"] == 0 and ind["ticker_heat"] > 0
    assert ind["episode_count"] == 1

    # blend: heat = 1·direct + 1·(ticker / attr_size**0.5)  (rel tol — components are 3-dp rounded)
    assert hbm["heat"] == pytest.approx(
        hbm["direct_heat"] + hbm["ticker_heat"] / (hbm["attr_size"] ** 0.5), rel=0.02)
    assert ind["heat"] == pytest.approx(
        ind["ticker_heat"] / (ind["attr_size"] ** 0.5), rel=0.02)
    # same raw weight, but the theme (size 4) normalises lighter than the industry (size 16)
    assert hbm["heat"] > ind["heat"]


@pytest.mark.asyncio
async def test_board_members_follow_live_registry_roster_without_episode_backfill():
    """A fresh board compute reads displayed members from the registry index, so a
    registry roster edit is visible even when episode snapshots are unchanged."""
    exposures = [
        {
            "exposure_id": "sector_live",
            "exposure_type": "theme",
            "display_name": "Live Sector",
            "resolved_tickers": [
                {"ticker": "OLD", "name": "Old Snapshot", "market": "US", "source": "curated"},
            ],
        }
    ]
    docs = [_doc("ep-001", exposures=exposures)]
    svc, _ = _make_svc(docs)

    base_index = {
        "ticker_to_sectors": {},
        "attr_size": {"sector_live": 2},
        "meta": {
            "sector_live": {"display_name": "Live Sector", "exposure_type": "theme"},
        },
        "ticker_name": {"NEW1": "New One", "NEW2": "New Two", "NEW3": "New Three"},
        "members": {
            "sector_live": [
                {"ticker": "NEW1", "name": "New One"},
                {"ticker": "NEW2", "name": "New Two"},
            ],
        },
    }
    changed_index = {
        **base_index,
        "attr_size": {"sector_live": 2},
        "members": {
            "sector_live": [
                {"ticker": "NEW1", "name": "New One"},
                {"ticker": "NEW3", "name": "New Three"},
            ],
        },
    }

    async def _fake_eod(ticker: str):
        return {"NEW1": 1.0, "NEW2": 2.0, "NEW3": 3.0, "OLD": 9.0}.get(ticker)

    with (
        patch("src.services.podcast.cache_get", new=AsyncMock(return_value=None)),
        patch("src.services.podcast.cache_set", new=AsyncMock()),
        patch.object(svc, "_allowed_podcast_names", new=AsyncMock(return_value=None)),
        patch.object(PodcastService, "_sector_membership_index", return_value=base_index),
        patch("src.services.stock_close_refresh.get_eod_change_pct", side_effect=_fake_eod),
        _patch_get_session(),
    ):
        first = await svc.sector_board()

    with (
        patch("src.services.podcast.cache_get", new=AsyncMock(return_value=None)),
        patch("src.services.podcast.cache_set", new=AsyncMock()),
        patch.object(svc, "_allowed_podcast_names", new=AsyncMock(return_value=None)),
        patch.object(PodcastService, "_sector_membership_index", return_value=changed_index),
        patch("src.services.stock_close_refresh.get_eod_change_pct", side_effect=_fake_eod),
        _patch_get_session(),
    ):
        second = await svc.sector_board()

    assert [m["ticker"] for m in first[0]["members"]] == ["NEW2", "NEW1"]
    assert [m["ticker"] for m in second[0]["members"]] == ["NEW3", "NEW1"]
    assert "OLD" not in {m["ticker"] for m in second[0]["members"]}


@pytest.mark.asyncio
async def test_sector_board_serves_cache_without_scanning():
    """On a cache hit, sector_board() returns the cached payload and never runs the
    expensive Firestore scan — this is what keeps the warm serving path fast."""
    docs = [_doc("ep-001")]
    svc, _ = _make_svc(docs)
    cached_payload = [{"exposure_id": "sector_cached", "hotness": 0.9}]

    with (
        patch("src.services.podcast.cache_get", new=AsyncMock(return_value=json.dumps(cached_payload))),
        patch("src.services.podcast.cache_set", new=AsyncMock()),
        patch.object(svc, "_allowed_podcast_names", new=AsyncMock(return_value=None)),
    ):
        result = await svc.sector_board()

    assert result == cached_payload
    svc.firestore_service.stream_documents_projected.assert_not_called()


@pytest.mark.asyncio
async def test_warm_sector_board_recomputes_ignoring_cache():
    """warm_sector_board() (used by the refresh-ahead loop) ignores any existing
    cached value, recomputes from the scan, and writes the fresh result to cache."""
    docs = [_doc("ep-001")]
    svc, _ = _make_svc(docs)

    async def _fake_eod(ticker: str):
        return {"2327": 1.5}.get(ticker)

    set_mock = AsyncMock()
    with (
        # A STALE cache value is present; warm must recompute regardless.
        patch("src.services.podcast.cache_get", new=AsyncMock(return_value=json.dumps([{"stale": True}]))),
        patch("src.services.podcast.cache_set", new=set_mock),
        patch.object(svc, "_allowed_podcast_names", new=AsyncMock(return_value=None)),
        patch("src.services.stock_close_refresh.get_eod_change_pct", side_effect=_fake_eod),
        _patch_get_session(),
    ):
        result = await svc.warm_sector_board()

    # Recomputed from the scan, not the stale cache.
    assert len(result) == 1
    assert result[0]["exposure_id"] == "sector_passive_components"
    # And the fresh board was written back to cache exactly once.
    assert set_mock.await_count == 1
    cached_written = json.loads(set_mock.await_args.args[1])
    assert cached_written[0]["exposure_id"] == "sector_passive_components"
