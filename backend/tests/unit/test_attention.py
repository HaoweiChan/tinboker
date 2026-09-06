"""Home-page attention: rolling windows, momentum floors, narrative rising slot."""
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.services.trending import TrendingService, momentum_score, pick_narratives

DAY = 86_400_000


NOW_MS = int(datetime.now().timestamp() * 1000)


def _ep(i, days_ago, tickers, tags=(), podcast="P1"):
    t = NOW_MS - int(days_ago * DAY)
    return SimpleNamespace(id=f"ep{i}", released_at_ms=t, created_time=t, related_tickers=list(tickers), tags=list(tags), podcast_name=podcast)


def test_momentum_score_prefers_volume_over_low_base_percent():
    assert momentum_score(18, 12) > momentum_score(6, 3)
    assert momentum_score(4, 4) == 0


def test_pick_narratives_top_plus_one_rising_slot():
    rows = [
        {"id": "a", "count_7d": 20, "prev_7d": 13},
        {"id": "b", "count_7d": 7, "prev_7d": 7},
        {"id": "c", "count_7d": 5, "prev_7d": 5},
        {"id": "d", "count_7d": 5, "prev_7d": 5},   # flat: never the rising slot
        {"id": "e", "count_7d": 4, "prev_7d": 2},   # +100%
        {"id": "f", "count_7d": 2, "prev_7d": 0},   # below the 3-mention floor
    ]
    out = pick_narratives(rows, 4)
    assert [r["id"] for r in out] == ["a", "b", "c", "e"]
    assert out[-1]["rising"] is True and "rising" not in out[0]
    # nothing qualifies → plain top-n
    assert [r["id"] for r in pick_narratives(rows[:4], 4)] == ["a", "b", "c", "d"]


@pytest.mark.asyncio
@patch("src.services.trending.hidden_tag_slugs", return_value={"hiddentag"})
@patch("src.services.trending.get_session", return_value=iter([object()]))
@patch("src.services.trending.cache_get", new_callable=AsyncMock, return_value=None)
@patch("src.services.trending.cache_set", new_callable=AsyncMock)
async def test_get_attention_windows_and_boards(_set, _get, _sess, _hidden):
    import src.services.trending as mod
    eps = []
    # NVDA: 14 in last 7d, 12 in the prior 7d, plenty in 30d
    eps += [_ep(f"n{i}", 0.5, ["NVDA"], ["aiindustry", "sp500"]) for i in range(14)]
    eps += [_ep(f"np{i}", 10, ["NVDA"], ["aiindustry"]) for i in range(12)]
    # 2615: 6 in last 7d vs 3 prior — higher %, lower momentum score than NVDA
    eps += [_ep(f"w{i}", 1, ["2615"], ["supplychain"]) for i in range(6)]
    eps += [_ep(f"wp{i}", 9, ["2615"], ["supplychain"]) for i in range(3)]
    # 2408: 4 vs 1 but only 5 in 30d total → passes floors (5 ≥ 5)
    eps += [_ep(f"s{i}", 2, ["2408"], ["fedrate"]) for i in range(4)]
    eps += [_ep(f"sp{i}", 12, ["2408"], ["fedrate"]) for i in range(1)]
    # 3037: 3 vs 2 but only 4 in 30d → below the 30d floor
    eps += [_ep(f"x{i}", 3, ["3037"], ["hiddentag", "notcanon"]) for i in range(3)]
    eps += [_ep(f"xp{i}", 11, ["3037"]) for i in range(1)]
    # prior-30d only mentions (day 45): count toward prev_30d, never 7d/30d
    eps += [_ep(f"o{i}", 45, ["NVDA"], ["aiindustry"]) for i in range(5)]
    # older than 60d: ignored entirely
    eps += [_ep("z", 70, ["NVDA"])]
    # a second podcast inside 7d
    eps += [_ep("q", 1, ["MSFT"], podcast="P2")]

    svc = TrendingService(podcast_service=SimpleNamespace(get_recent_episodes=AsyncMock(return_value=eps)))
    svc._get_translations_batch = AsyncMock(return_value={"NVDA": "輝達"})
    out = await svc.get_attention(limit=3, narratives=3, rising_limit=5)

    assert out["episode_count_7d"] == 14 + 6 + 4 + 3 + 1 and out["podcast_count_7d"] == 2
    nvda = out["tickers"][0]
    assert nvda == {"ticker": "NVDA", "name": "輝達", "count_30d": 26, "prev_30d": 5, "count_7d": 14, "prev_7d": 12}
    assert [t["ticker"] for t in out["tickers"]] == ["NVDA", "2615", "2408"]
    # rising: momentum order NVDA(2·ln15=5.4) < 2615(3·ln7=5.8) < 2408(3·ln5=4.8); 3037 and MSFT filtered
    assert [t["ticker"] for t in out["rising"]] == ["2615", "NVDA", "2408"]
    # narratives: sp500 (index) and hiddentag / notcanon excluded; top-2 + rising slot
    ids = [n["id"] for n in out["narratives"]]
    assert ids == ["aiindustry", "supplychain", "fedrate"]
    assert out["narratives"][-1]["rising"] is True
    assert out["narratives"][0]["name"] == "AI產業" and len(out["narratives"][0]["weekly"]) == 6
    assert out["narratives"][0]["weekly"][-1] == 14 and out["narratives"][0]["weekly"][-2] == 12
    assert mod.NON_NARRATIVE_TAGS  # guard: constant exists for the UI contract
