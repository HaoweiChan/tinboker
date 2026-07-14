"""Point-in-time validation of discussion-heat as a forward-return predictor.

The /topics bubble chart plots *current* discussion heat (X) against *trailing*
return (Y) — both measured at request time, so the axes are contemporaneous and
tell you nothing about prediction (a topic looks "strong" only because it already
rose and is already being discussed). This module recomputes heat *as of* a past
date D from episodes released on or before D, then joins it to the *forward*
return over the following N days — the only framing in which heat can be judged a
profit signal. Heat is then quantized into buckets so the mean forward return per
bucket reads directly as a signal→profit curve.

Returns are cross-sectionally demeaned per as-of date before quantizing (see
``demean_by_date``): raw pooled returns would let a single market regime — or a
calendar stretch of heavy podcast volume — manufacture a heat→return gradient out
of nothing. Every bucket therefore reports EXCESS return vs the other themes on the
same day, not an absolute one.

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


def demean_by_date(observations: list[tuple[float, float, str]]) -> list[tuple[float, float]]:
    """Subtract each as-of date's cross-sectional mean return → ``[(signal, excess)]``.

    Without this, two confounds stack: returns are raw (not market-adjusted) and
    observations are pooled across dates before the rank-split. A calendar stretch of
    heavy podcast volume then lands wholesale in the top heat buckets, and with a
    shallow price history one market regime dominates — so in a rising tape the top
    bucket beats the bottom one even when heat carries ZERO cross-sectional signal,
    and the panel would "validate" heat spuriously.

    Demeaning per date makes every bucket answer the question the panel actually
    claims: did the hottest themes *that day* beat the other themes *that same day*.
    A date with a single theme demeans to 0 and self-neutralises — correct, since one
    theme carries no cross-sectional information.
    """
    sums: dict[str, float] = {}
    counts: dict[str, int] = {}
    for _, r, d in observations:
        sums[d] = sums.get(d, 0.0) + r
        counts[d] = counts.get(d, 0) + 1
    return [(h, r - sums[d] / counts[d]) for h, r, d in observations]


def quantize(observations: list[tuple[float, float]], n_buckets: int) -> list[dict]:
    """Rank-split ``[(signal, excess_return)]`` into ``n_buckets`` by signal (low→high).

    Returns one dict per non-empty bucket: signal range, mean excess forward return
    (percent, cross-sectionally demeaned by ``demean_by_date``), and the sample count
    (surfaced so shallow buckets are visible, never silently averaged over 2 points as
    if robust).
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
    # (heat, forward_return, as_of_date) — the date is carried so returns can be
    # cross-sectionally demeaned per date before quantizing (see demean_by_date).
    obs: dict[int, list[tuple[float, float, str]]] = {n: [] for n in horizons}
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
                    obs[n].append((heat, sum(rets) / len(rets), d))
                    used_dates.add(d)

    return {
        "half_life_days": half_life,
        "n_buckets": n_buckets,
        "horizons": {
            str(n): {
                "buckets": quantize(demean_by_date(obs[n]), n_buckets),
                "n": len(obs[n]),
            }
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

    # demean_by_date subtracts each date's cross-sectional mean; a lone theme on a
    # date carries no cross-sectional info and self-neutralises to 0.
    dm = demean_by_date([(1.0, 0.02, "d1"), (2.0, 0.00, "d1"), (3.0, 0.05, "d2")])
    assert abs(dm[0][1] - 0.01) < 1e-12 and abs(dm[1][1] + 0.01) < 1e-12
    assert abs(dm[2][1]) < 1e-12

    # THE regression guard: a pure market move (every theme up the same amount) has
    # zero cross-sectional signal — demeaning must flatten it, so a rising tape can
    # never manufacture a heat→return gradient.
    flat = demean_by_date([(1.0, 0.05, "d1"), (9.0, 0.05, "d1")])
    assert all(abs(r) < 1e-12 for _, r in flat)

    # End-to-end, cross-sectional: same day, hot theme's member +10%, cold theme's
    # -10%. The hot bucket must earn positive EXCESS return over the cold one.
    d0 = float(day_index("2024-01-01"))
    down = [("2024-01-01", 100.0), ("2024-01-08", 90.0)]
    out = compute_validation(
        direct_events={"hot": [d0, d0, d0], "cold": [d0]},  # hot is discussed 3x
        implied_events={},
        members_by_eid={"hot": ["AAA"], "cold": ["BBB"]},
        closes={"AAA": s, "BBB": down},
        horizons=(7,),
        n_buckets=2,
    )
    b7 = out["horizons"]["7"]["buckets"]
    assert len(b7) == 2, b7
    assert b7[0]["signal_max"] <= b7[1]["signal_min"]        # bucket 2 = hotter
    assert b7[1]["mean_return"] > 0 > b7[0]["mean_return"]   # hotter → higher excess
    print("heat_validation self-check OK")
