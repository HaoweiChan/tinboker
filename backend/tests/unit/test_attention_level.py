import random
from datetime import date, timedelta

from src.services.attention import MIN_HISTORY_DAYS, attention_level


def _days(n: int, start: date = date(2025, 1, 1)):
    return [start + timedelta(days=i) for i in range(n)]


def test_rising_share_ends_at_100_and_thin_history_gets_nothing():
    days = _days(200)
    market = {d: 100 for d in days}
    ticker = {d: i + 1 for i, d in enumerate(days)}  # share climbs every day
    out = attention_level(ticker, market, days[-1])
    assert len(out) == 200 - MIN_HISTORY_DAYS + 1
    assert out[0]["d"] == days[MIN_HISTORY_DAYS - 1].isoformat()
    assert out[-1] == {"d": days[-1].isoformat(), "p": 100}


def test_falling_share_ends_near_zero():
    days = _days(200)
    market = {d: 100 for d in days}
    ticker = {d: 200 - i for i, d in enumerate(days)}
    assert attention_level(ticker, market, days[-1])[-1]["p"] <= 1


def test_spike_outside_window_is_forgotten():
    # The decayed spike stays measurable for ~250 days at float precision, then has to
    # roll out of the 364-day window too, so "forgotten" is ~600 days out.
    days = _days(700)
    market = {d: 100 for d in days}
    # Irregular but identical mentions (no exact ties), so a float-epsilon residual of
    # the spike cannot flip a rank by breaking a tie.
    rng = random.Random(0)
    steady = {d: rng.randint(0, 9) for d in days}
    spiky = {**steady, days[0]: 5000}  # one loud day on top
    a = {r["d"]: r["p"] for r in attention_level(spiky, market, days[-1])}
    b = {r["d"]: r["p"] for r in attention_level(steady, market, days[-1])}
    # 100 days in, the spike still sits inside the window and pushes today's rank down.
    assert a[days[100].isoformat()] < b[days[100].isoformat()]
    # 699 days in, the spike has rolled out of the window: identical readings.
    assert a[days[-1].isoformat()] == b[days[-1].isoformat()]


def test_thin_market_days_are_skipped():
    days = _days(120)
    market = {d: (100 if i >= 100 else 1) for i, d in enumerate(days)}  # corpus too small at first
    ticker = {d: 1 for d in days}
    assert attention_level(ticker, market, days[-1]) == []
