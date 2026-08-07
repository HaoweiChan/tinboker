"""Regression tests for the /topics bubble-chart all-zero outage (2026-07-05).

The trading-value windows now come from Postgres (stock_daily_ohlc), but two guards from
the original outage still matter:
- F2: an all-empty result must NOT be cached for a day — before the daily fetcher/backfill
  has populated the table, an empty read would otherwise poison the cache for 24h.
- F1: yfinance must ship in the image (requirements.txt), so the Yahoo fallback used by the
  daily-close warmer isn't a silent ImportError.
"""

from unittest.mock import patch


# ── F2: an all-empty windows result is not written to the day-long cache ───────────

def test_all_empty_windows_result_is_not_cached():
    import asyncio

    from src.services.podcast import PodcastService

    svc = PodcastService.__new__(PodcastService)  # skip __init__ heavy deps
    empty = {"1": {}, "7": {}, "30": {}, "90": {}}  # always-truthy, no per-stock data

    sets: list = []

    async def fake_cache_get(*a, **k):
        return None

    async def fake_cache_set(*a, **k):
        sets.append(a)

    with patch("src.services.podcast.cache_get", fake_cache_get), \
         patch("src.services.podcast.cache_set", fake_cache_set), \
         patch.object(svc, "_read_tw_trading_value_windows", return_value=empty):
        out = asyncio.run(svc._tw_trading_value_windows_cached(["2330"]))

    assert out == empty        # still returned to the caller for this request
    assert sets == []          # but NOT cached — next request retries instead of T+24h


# ── F1: yfinance must be in the image manifest, not just pyproject ────────────────
# The Docker image installs from requirements.txt (not pyproject.toml). yfinance was in
# pyproject but missing from requirements.txt → `import yfinance` raised ImportError in
# the container → the Yahoo fallback silently returned [] and the bubbles went blank.

def test_yfinance_in_requirements_txt():
    from pathlib import Path

    req = Path(__file__).resolve().parents[2] / "requirements.txt"
    assert "yfinance" in req.read_text(), (
        "yfinance missing from requirements.txt — the backend image installs from it, "
        "so the Yahoo fallback dies with ImportError (see 2026-07-05 /topics outage)."
    )
