"""Offline unit tests for the FinMind industry-member refresh logic.

No network: the pure merge/sync functions are fed fixture dicts. The key
invariant under test is *non-regression* — FinMind's ``電子工業`` catch-all must
never displace a curated fine label or pollute a clean sector.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "refresh_industry_members.py"
_spec = importlib.util.spec_from_file_location("refresh_industry_members", _SCRIPT)
rim = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rim)

# 2454 聯發科 is a semiconductor company but FinMind buckets it under the legacy
# broad ``電子工業`` — it must be EXCLUDED from auto-fill, not mis-mapped.
INFO = {
    "2330": {"name": "台積電", "category": "半導體業"},
    "2303": {"name": "聯電", "category": "半導體業"},
    "2337": {"name": "旺宏", "category": "半導體業"},
    "2454": {"name": "聯發科", "category": "電子工業"},   # catch-all → unmapped
    "2603": {"name": "長榮", "category": "航運業"},
    "9999": {"name": "Other", "category": "其他"},        # unknown category
}
MARKET_VALUES = {"2330": 6e13, "2303": 5e11, "2337": 1e11, "2454": 2e12, "2603": 3e11}
CATEGORY_MAP = {"半導體業": "sector_semiconductor", "航運業": "sector_shipping"}
SECTOR_DISPLAY = {"sector_semiconductor": "半導體", "sector_shipping": "航運"}


def test_build_finmind_members_ranks_by_market_cap_and_excludes_catchall():
    members = rim.build_finmind_members(INFO, MARKET_VALUES, CATEGORY_MAP, cap=3)
    semi = [m["ticker"] for m in members["sector_semiconductor"]]
    assert semi == ["2330", "2303", "2337"]            # market-cap desc
    assert "2454" not in semi                          # 電子工業 excluded
    assert members["sector_shipping"][0]["ticker"] == "2603"
    assert all(m["source"] == "finmind" for m in members["sector_semiconductor"])
    assert [m["market_cap_rank"] for m in members["sector_semiconductor"]] == [1, 2, 3]


def test_build_finmind_members_respects_cap():
    members = rim.build_finmind_members(INFO, MARKET_VALUES, CATEGORY_MAP, cap=2)
    assert len(members["sector_semiconductor"]) == 2


def test_merge_preserves_curated_first_and_adds_breadth():
    existing = [
        {"ticker": "2330", "source": "curated", "rank": 1, "reason": "晶圓代工龍頭"},
        {"ticker": "NVDA", "source": "issuer_etf", "market_cap_rank": 1},
        {"ticker": "3035", "source": "websearch"},
    ]
    finmind = rim.build_finmind_members(INFO, MARKET_VALUES, CATEGORY_MAP, cap=3)["sector_semiconductor"]
    merged, new_tickers = rim.merge_sector_members(existing, finmind, cap=4)
    tickers = [m["ticker"] for m in merged]

    assert merged[0]["ticker"] == "2330"               # curated ranks first
    assert merged[0]["reason"] == "晶圓代工龍頭"          # curated reason preserved
    assert merged[0]["source"] == "curated"            # not overwritten by FinMind
    assert set(new_tickers) == {"2303", "2337"}        # FinMind-only additions that survived the cap
    assert "3035" not in tickers                       # lowest-priority trimmed at cap=4
    assert len(merged) == 4


def test_ticker_sync_is_non_regressing():
    tickers = {
        "2330": {"sector": "半導體"},   # already correct → no update
        "2303": {"sector": "記憶體"},   # wrong → corrected to 半導體
        "2454": {"sector": "半導體"},   # FinMind says 電子工業 (unmapped) → MUST be left alone
        "2603": {"sector": "航運"},     # already correct → no update
        "0050": {"sector": "ETF"},     # not in FinMind info → skipped
    }
    updates = rim.resolve_ticker_sector_updates(tickers, INFO, CATEGORY_MAP, SECTOR_DISPLAY)
    assert updates == {"2303": "半導體"}
    assert "2454" not in updates       # the non-regression guarantee


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok {name}")
    print("all passed")
