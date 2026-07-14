"""Point-in-time validation of discussion-heat as a forward-return predictor.

The /topics bubble chart plots *current* discussion heat (X) against *trailing*
return (Y) — both measured at request time, so the axes are contemporaneous and
tell you nothing about prediction (a topic looks "strong" only because it already
rose and is already being discussed). This module recomputes heat *as of* a past
date D from episodes released on or before D, then joins it to the *forward*
return over the following N days — the only framing in which heat can be judged a
profit signal. Heat is then quantized into buckets so the mean forward return per
bucket reads directly as a signal→profit curve.

Everything here is pure (no I/O) so ``compute_validation`` is unit-tested by the
``__main__`` self-check at the bottom. The service layer (``PodcastService``)
supplies the scanned episode events and dated closes.
"""
from __future__ import annotations

from bisect import bisect_right
from datetime import date, timedelta

_EPOCH = date(1970, 1, 1)


def day_index(date_str: str) -> int:
    """Whole days since the epoch for a ``YYYY-MM-DD`` string (heat decay unit)."""
    return (date.fromisoformat(date_str) - _EPOCH).days


def decayed_heat(event_days: list[float], asof_day: float, half_life: float = 7.0) -> float:
    """Σ 0.5^((asof-t)/H) over events at or before ``asof_day`` (future events dropped).

    Mirrors the production heat weight (``podcast.py`` board scan) but anchored to a
    historical ``asof_day`` instead of "now", so no future episode leaks in.
    """
    return sum(
        0.5 ** ((asof_day - t) / half_life)
        for t in event_days
        if t <= asof_day
    )


def close_asof(series: list[tuple[str, float]], target: str) -> float | None:
    """Last close with date <= ``target``. ``series`` is ascending ``(date, close)``.

    Binary search (dates are sorted) so the backtest stays fast as price history
    deepens — the whole point of a backfill is a longer series here.
    """
    i = bisect_right(series, target, key=lambda e: e[0])
    return series[i - 1][1] if i > 0 else None


def forward_return(series: list[tuple[str, float]], start: str, end: str) -> float | None:
    """Forward return from ``start`` to ``end`` — None unless the window is *complete*.

    Requires the series to actually reach ``end`` (its latest date >= ``end``);
    otherwise the window hasn't closed yet and returning a partial figure would be a
    look-ahead artifact. ``close_asof`` then picks the real trading-day closes in
    ``[start, end]``.
    """
    if not series or series[-1][0] < end:
        return None
    a = close_asof(series, start)
    b = close_asof(series, end)
    if a is None or b is None or a <= 0:
        return None
    return b / a - 1.0


def quantize(observations: list[tuple[float, float]], n_buckets: int) -> list[dict]:
    """Rank-split ``[(signal, fwd_return)]`` into ``n_buckets`` by signal (low→high).

    Returns one dict per non-empty bucket: signal range, mean forward return
    (percent), and the sample count (surfaced so shallow buckets are visible, never
    silently averaged over 2 points as if robust).
    """
    obs = sorted(observations, key=lambda o: o[0])
    total = len(obs)
    out: list[dict] = []
    for b in range(n_buckets):
        lo = b * total // n_buckets
        hi = (b + 1) * total // n_buckets
        chunk = obs[lo:hi]
        if not chunk:
            continue
        rets = [r for _, r in chunk]
        out.append({
            "bucket": b + 1,
            "signal_min": round(chunk[0][0], 3),
            "signal_max": round(chunk[-1][0], 3),
            "mean_return": round(sum(rets) / len(rets) * 100.0, 2),
            "n": len(chunk),
        })
    return out


def compute_validation(
    *,
    direct_events: dict[str, list[float]],
    implied_events: dict[str, list[float]],
    members_by_eid: dict[str, list[str]],
    closes: dict[str, list[tuple[str, float]]],
    horizons: tuple[int, ...] = (7, 30, 90),
    n_buckets: int = 5,
    w_direct: float = 1.0,
    w_ticker: float = 1.0,
    norm_alpha: float = 0.5,
    half_life: float = 7.0,
) -> dict:
    """Build the heat→forward-return buckets per horizon (pure; no I/O).

    For every (theme, as-of trading date) pair we recompute the blended heat as of
    that date and the member-average forward return over each horizon, then quantize.
    ``closes`` is ``{ticker: [(date, close)]}`` ascending; the union of its dates is
    the as-of grid.
    """
    all_dates = sorted({d for series in closes.values() for d, _ in series})
    if not all_dates:
        return _empty(horizons, n_buckets, half_life)

    attr_size = {eid: max(len(members_by_eid.get(eid) or []), 1) for eid in members_by_eid}
    obs: dict[int, list[tuple[float, float]]] = {n: [] for n in horizons}
    used_dates: set[str] = set()

    for eid, members in members_by_eid.items():
        direct = direct_events.get(eid) or []
        implied = implied_events.get(eid) or []
        if not direct and not implied:
            continue
        member_series = [closes[t] for t in members if t in closes]
        if not member_series:
            continue
        size = attr_size.get(eid, 1)
        for d in all_dates:
            asof = float(day_index(d))
            heat = (
                w_direct * decayed_heat(direct, asof, half_life)
                + w_ticker * (decayed_heat(implied, asof, half_life) / (size ** norm_alpha))
            )
            if heat <= 0:
                continue
            for n in horizons:
                end = (date.fromisoformat(d) + timedelta(days=n)).isoformat()
                rets = [fr for s in member_series if (fr := forward_return(s, d, end)) is not None]
                if rets:
                    obs[n].append((heat, sum(rets) / len(rets)))
                    used_dates.add(d)

    return {
        "half_life_days": half_life,
        "n_buckets": n_buckets,
        "horizons": {
            str(n): {"buckets": quantize(obs[n], n_buckets), "n": len(obs[n])}
            for n in horizons
        },
        "date_span": {"start": all_dates[0], "end": all_dates[-1]},
        "as_of_count": len(used_dates),
    }


def _empty(horizons: tuple[int, ...], n_buckets: int, half_life: float) -> dict:
    return {
        "half_life_days": half_life,
        "n_buckets": n_buckets,
        "horizons": {str(n): {"buckets": [], "n": 0} for n in horizons},
        "date_span": {"start": None, "end": None},
        "as_of_count": 0,
    }


if __name__ == "__main__":
    # decayed_heat drops future events (point-in-time correctness — the whole point).
    assert decayed_heat([0.0, 10.0], asof_day=5.0, half_life=7.0) == 0.5 ** (5.0 / 7.0)
    assert decayed_heat([], 5.0) == 0.0

    # close_asof picks the last close at/before the target.
    s = [("2024-01-01", 100.0), ("2024-01-08", 110.0), ("2024-01-15", 121.0)]
    assert close_asof(s, "2024-01-10") == 110.0
    assert close_asof(s, "2023-12-31") is None

    # forward_return uses start→end and refuses an incomplete (still-open) window.
    assert abs(forward_return(s, "2024-01-01", "2024-01-08") - 0.10) < 1e-9
    assert forward_return(s, "2024-01-08", "2024-02-01") is None  # end past last date

    # quantize splits by rank and reports counts; higher signal bucket ranks last.
    buckets = quantize([(1, -0.02), (2, 0.00), (3, 0.03), (4, 0.05)], n_buckets=2)
    assert [b["n"] for b in buckets] == [2, 2]
    assert buckets[0]["signal_max"] <= buckets[1]["signal_min"]
    assert buckets[1]["mean_return"] > buckets[0]["mean_return"]

    # End-to-end: a theme discussed on 01-01, one member that rose 10% over 7 days.
    out = compute_validation(
        direct_events={"t1": [float(day_index("2024-01-01"))]},
        implied_events={},
        members_by_eid={"t1": ["AAA"]},
        closes={"AAA": s},
        horizons=(7,),
        n_buckets=1,
    )
    b7 = out["horizons"]["7"]["buckets"]
    assert b7 and b7[0]["n"] >= 1 and b7[0]["mean_return"] > 0
    print("heat_validation self-check OK")
