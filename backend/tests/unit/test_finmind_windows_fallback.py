"""Regression tests for the /topics bubble-chart all-zero outage (2026-07-05).

Two silent-failure bugs blanked the bubble chart:
- F1: a missing FinMind key raised inside the per-ticker fetch closure, skipping the
  Yahoo fallback → all-zero trading value. The fix makes `_make_request` return None
  (like every other failure) so `get_tw_trading_value_windows` falls through to Yahoo.
- F2: the all-empty result was cached for a day, turning a one-hour outage into 24h.
  `_tw_trading_value_windows_cached` must not cache a result with no per-stock data.
"""

from unittest.mock import patch

from src.services.finmind_service import FinMindAPIService


# ── F1: no key → Yahoo fallback populates the windows (no raise, no all-zero) ──────

def test_windows_fall_back_to_yahoo_when_no_api_key():
    svc = FinMindAPIService(api_key=None)
    svc.api_keys = []  # simulate an unconfigured container

    yahoo_rows = [
        {"date": "2026-07-04", "Trading_money": 1_000_000.0},
        {"date": "2026-07-03", "Trading_money": 2_000_000.0},
    ]
    with patch(
        "src.services.finmind_service.list_yahoo_tw_daily_range",
        return_value=yahoo_rows,
    ) as yahoo:
        totals = svc.get_tw_trading_value_windows(["2330"], windows=(7,))

    yahoo.assert_called_once()  # fallback was reached, not skipped by a raise
    assert totals["7"]["2330"] == 3_000_000.0  # both days summed from Yahoo


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
