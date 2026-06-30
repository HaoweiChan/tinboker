"""Unit check for FinMind 三大法人 net-flow aggregation (no network).

Validates the money path: net shares = Σ(buy − sell), value = net shares × close,
外資 vs 三大法人-total split, and 1/5/20d window cutoffs. The LIVE FinMind unit
calibration (shares vs lots vs value) must still be verified against TWSE T86 for one
real stock/day on dev before trusting absolute magnitudes — this only pins the math.
"""
from datetime import date, timedelta

from src.services.finmind_service import FinMindAPIService


def test_institutional_net_windows():
    svc = object.__new__(FinMindAPIService)  # bypass __init__ — no API key needed for the pure logic
    today = date.today()
    d0 = today.isoformat()
    d1 = (today - timedelta(days=1)).isoformat()
    rows = [
        {"date": d0, "stock_id": "2330", "name": "Foreign_Investor", "buy": 1000, "sell": 0},
        {"date": d0, "stock_id": "2330", "name": "Investment_Trust", "buy": 500, "sell": 0},
        {"date": d1, "stock_id": "2330", "name": "Foreign_Investor", "buy": 0, "sell": 200},
        {"date": d0, "stock_id": "9999", "name": "Foreign_Investor", "buy": 9999, "sell": 0},  # not requested
    ]
    svc._make_request = lambda params, timeout=10: {"data": rows}
    svc.get_tw_latest_closes = lambda: {"2330": 1000.0}  # close NT$1000

    out = svc.get_tw_institutional_net_windows(["2330"], windows=(1, 5))

    # 1d (today only): foreign = 1000sh × 1000 = 1e6; total = (1000+500)×1000 = 1.5e6
    assert round(out["foreign"]["1"]["2330"]) == 1_000_000
    assert round(out["total"]["1"]["2330"]) == 1_500_000
    # 5d (today + yesterday): foreign = (1000−200)×1000 = 8e5; total = (1500−200)×1000 = 1.3e6
    assert round(out["foreign"]["5"]["2330"]) == 800_000
    assert round(out["total"]["5"]["2330"]) == 1_300_000
    # ticker not in the requested set is excluded
    assert "9999" not in out["total"]["1"]
    assert "9999" not in out["foreign"]["1"]


if __name__ == "__main__":
    test_institutional_net_windows()
    print("✓ institutional net-windows aggregation OK")
