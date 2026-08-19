"""exposures_performance() must survive NaN in any upstream numeric source.

Regression for the /topics bubble chart outage: a single NaN member value
(FinMind/numpy artifacts survive the JSON cache round-trip) poisoned a whole
exposure's sum and int(round(nan)) raised, 500ing GET /api/sectors/performance
in every environment.
"""
import math
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.podcast import PodcastService

NAN = float("nan")

BOARD = [
    {
        "exposure_id": "sector_x",
        "exposure_type": "industry",
        "display_name": "X",
        "color_hex": "#000000",
        "episode_count": 3,
        "heat": NAN,
        "avg_change": NAN,
        "members": [{"ticker": "2330"}, {"ticker": "2454"}],
    }
]


@pytest.mark.asyncio
async def test_nan_values_do_not_500_and_are_treated_as_zero():
    svc = PodcastService(firestore_service=MagicMock())
    svc.sector_board = AsyncMock(return_value=BOARD)
    svc._tw_institutional_net_windows_cached = AsyncMock(
        return_value={
            "total": {"5": {"2330": NAN, "2454": 100.0}},
            "foreign": {"5": {"2330": NAN, "2454": None}},
        }
    )
    svc._tw_market_caps_cached = AsyncMock(return_value={"2330": NAN, "2454": 50.0})
    svc._us_market_caps_cached = AsyncMock(return_value={})
    svc._tw_trading_value_windows_cached = AsyncMock(
        return_value={"1": {"2330": NAN, "2454": 200.0}}
    )
    svc._us_trading_value_windows_cached = AsyncMock(return_value={})

    out = await svc.exposures_performance()

    assert len(out) == 1
    row = out[0]
    # NaN member values count as 0; the finite members survive.
    assert row["trading_value_windows_twd"] == {"1": 200}
    assert row["net_buy_windows_twd"] == {"5": 100}
    assert row["foreign_net_windows_twd"] == {"5": 0}
    assert row["market_cap_twd"] == 50
    # NaN heat/avg become None, not NaN in the JSON payload.
    assert row["heat"] is None
    assert row["return_pct"] is None
    assert not any(
        isinstance(v, float) and math.isnan(v) for v in row.values() if v is not None
    )
