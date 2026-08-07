"""Whole-market TW anomaly screener — compute service.

Scans the individual-stock universe (TWSE + TPEx) each trading day for a
**momentum breakout + 三大法人 confirmation** signal, scores the passers
cross-sectionally, and writes ranked ``screener_candidates`` rows behind an
internal API. No frontend — this is the compute substrate for issue #450.

Reads **only** the two warm tables maintained by ``tw_daily_ohlc_refresh`` —
``stock_daily_ohlc`` and ``stock_institutional_daily`` — so there is no
per-ticker FinMind fan-out. Mirrors the ``run_periodic_*`` pattern in
``stock_close_refresh`` and is scheduled from ``main.py`` to run after the daily
OHLC/institutional refresh.

The pure compute helpers (``passes_universe``, ``compute_stage1_metrics``,
``score_pool``) take plain sequences so they are unit-testable without a DB.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Dict, List, Optional, Sequence, Tuple

from sqlalchemy import case, func

from src.database.models import ScreenerCandidate, StockDailyOHLC, StockInstitutionalDaily
from src.database.postgres import get_session

logger = logging.getLogger(__name__)

# --- Tunables ------------------------------------------------------------------
MA_SHORT = 20
MA_LONG = 60
HIGH_SHORT = 20
HIGH_LONG = 60
VOL_BASELINE = 20          # sessions BEFORE today for the volume baseline
VOL_MULT_MIN = 1.5         # today_volume must exceed this × baseline mean
RET_LOOKBACK = 5           # sessions ago for the overheated hard-filter
RET_MAX = 0.20             # drop names up >= +20% over 5 sessions
INSTITUTION_LOOKBACK = 5   # sessions summed for the concentration numerator
CROWDED_THRESHOLD = 70.0   # price_pos_60d above this flags crowded
# Minimum sessions of history required to evaluate a ticker (MA60 / 60d-high need 60).
MIN_SESSIONS = MA_LONG
# A complete TW trading day has both listed (TWSE) and OTC (TPEx) rows. TWSE's
# STOCK_DAY_ALL feed lags ~1 day on some days, leaving MAX(date) a single-source
# partial day (e.g. TPEx-only, ~880 rows) that has zero real breakout candidates
# (they're almost all TWSE-listed). These mirror tw_daily_ohlc_refresh's per-source
# backfill thresholds.
MIN_TWSE_ROWS_COMPLETE = 500
MIN_TPEX_ROWS_COMPLETE = 100

_UNIVERSE_RE = re.compile(r"^\d{4}$")


# --- Universe ------------------------------------------------------------------
def passes_universe(ticker: str) -> bool:
    """Individual-stock universe filter.

    Ticker must be exactly 4 digits, NOT starting with ``00`` (excludes ETFs),
    and contain no letters (excludes warrants). TWSE + TPEx both qualify.
    """
    t = (ticker or "").strip().upper().split(".")[0]  # tolerate a "2330.TW" suffix
    if not _UNIVERSE_RE.match(t):
        return False
    if t.startswith("00"):
        return False
    return True


# --- Stage 1 + factor compute (pure) -------------------------------------------
def _mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def compute_stage1_metrics(
    dates: Sequence[str],
    closes: Sequence[float],
    volumes: Sequence[float],
    insti: Dict[str, Tuple[Optional[float], Optional[float]]],
) -> Optional[dict]:
    """Compute the raw per-ticker metrics for the last day of ``dates`` and apply
    the Stage-1 breakout filter.

    ``dates``/``closes``/``volumes`` are chronological (oldest→newest), ending on
    the target trading day. ``insti`` maps date → (foreign_net, trust_net); a
    missing date or ``None`` net-share value is treated as 0.

    Returns a metrics dict when the ticker passes ALL Stage-1 gates, else ``None``
    (also ``None`` when there is not enough history).
    """
    n = len(closes)
    if n < MIN_SESSIONS or n != len(dates) or n != len(volumes):
        return None
    # Need a full baseline window BEFORE today.
    if n < VOL_BASELINE + 1 or n < RET_LOOKBACK + 1:
        return None

    close = closes[-1]
    ma20 = _mean(closes[-MA_SHORT:])
    ma60 = _mean(closes[-MA_LONG:])
    high20 = max(closes[-HIGH_SHORT:])
    high60 = max(closes[-HIGH_LONG:])
    low60 = min(closes[-HIGH_LONG:])
    today_volume = volumes[-1]
    mean20_vol_before = _mean(volumes[-(VOL_BASELINE + 1):-1])  # 20 sessions before today
    close_5_ago = closes[-(RET_LOOKBACK + 1)]
    ret_5d = (close / close_5_ago - 1.0) if close_5_ago else 0.0

    # --- Stage 1: must pass ALL, else dropped ---
    if not (close > ma20 and close > ma60):
        return None
    if close < high20:  # 20-day closing high (today included -> close is the window max)
        return None
    if mean20_vol_before <= 0 or today_volume <= VOL_MULT_MIN * mean20_vol_before:
        return None
    if ret_5d >= RET_MAX:  # overheated hard-filter
        return None

    # --- Stage 2: institution concentration factor (scoring input, not a filter) ---
    mean20_vol = _mean(volumes[-VOL_BASELINE:])
    insti_sum = 0.0
    for d in dates[-INSTITUTION_LOOKBACK:]:
        foreign_net, trust_net = insti.get(d, (0.0, 0.0))
        insti_sum += (foreign_net or 0.0) + (trust_net or 0.0)
    institution_raw = insti_sum / mean20_vol if mean20_vol > 0 else 0.0

    # --- Flags ---
    span60 = high60 - low60
    price_pos_60d = ((close - low60) / span60 * 100.0) if span60 > 0 else 0.0

    return {
        "close": close,
        "ma20": ma20,
        "ma60": ma60,
        "high_20": high20,
        "high_60": high60,
        "low_60": low60,
        "today_volume": today_volume,
        "mean20_vol_before": mean20_vol_before,
        "mean20_vol": mean20_vol,
        # sub-metrics used both for scoring and stored in factors JSON
        "close_ma20": close / ma20 if ma20 else 0.0,
        "close_ma60": close / ma60 if ma60 else 0.0,
        "vol_mult": today_volume / mean20_vol_before if mean20_vol_before else 0.0,
        "institution_raw": institution_raw,
        "price_pos_60d": price_pos_60d,
        "ret_5d": ret_5d,
        "is_60d_high": close >= high60,
        "crowded": price_pos_60d > CROWDED_THRESHOLD,
    }


def _pctrank(values: Sequence[float]) -> List[float]:
    """Cross-sectional percentile rank in [0, 1] with average-rank tie handling.

    ``pctrank = rank / (n - 1)``. For n <= 1 (a lone passer) returns 0.0 — there is
    no cross-section to rank against.
    """
    n = len(values)
    if n <= 1:
        return [0.0] * n
    order = sorted(range(n), key=lambda i: values[i])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg / (n - 1)
        i = j + 1
    return ranks


def score_pool(pool: List[dict]) -> List[dict]:
    """Score & rank a day's Stage-1 pool cross-sectionally.

    ``pool`` is a list of metrics dicts (each must carry a ``ticker`` key). Returns
    a new list, ranked by ``final_score`` desc, each item augmented with
    ``momentum_score``, ``institution_score``, ``final_score`` and ``rank``.
    """
    if not pool:
        return []

    r_ma20 = _pctrank([p["close_ma20"] - 1.0 for p in pool])
    r_ma60 = _pctrank([p["close_ma60"] - 1.0 for p in pool])
    r_vol = _pctrank([p["vol_mult"] for p in pool])
    r_inst = _pctrank([p["institution_raw"] for p in pool])

    scored: List[dict] = []
    for idx, p in enumerate(pool):
        momentum = (r_ma20[idx] + r_ma60[idx] + r_vol[idx]) / 3.0
        institution = r_inst[idx]
        final = 0.5 * momentum + 0.5 * institution
        scored.append({**p, "momentum_score": momentum, "institution_score": institution, "final_score": final})

    # Rank 1 = highest final_score. Stable tie-break by ticker for determinism.
    scored.sort(key=lambda p: (-p["final_score"], p.get("ticker", "")))
    for rank, p in enumerate(scored, start=1):
        p["rank"] = rank
    return scored


def _factors_payload(m: dict) -> dict:
    """The raw sub-metrics stored in the candidate row's ``factors`` JSON."""
    keys = (
        "close", "ma20", "ma60", "close_ma20", "close_ma60", "vol_mult",
        "mean20_vol_before", "mean20_vol", "today_volume", "institution_raw",
        "price_pos_60d", "ret_5d", "high_20", "high_60", "low_60",
    )
    return {k: m[k] for k in keys if k in m}


# --- DB orchestration ----------------------------------------------------------
def _latest_complete_ohlc_date(session) -> Optional[str]:
    """Most recent date with a healthy TWSE row count AND a healthy TPEx row count.

    A single-source partial day (see ``MIN_TWSE_ROWS_COMPLETE``/``MIN_TPEX_ROWS_COMPLETE``
    above) must never be the screener's target — it silently yields zero candidates.
    Falls back to the plain latest date (logged) when no date satisfies the both-sources
    rule, e.g. a fresh DB or one with only pre-TPEx-era rows. Never raises.
    """
    rows = (
        session.query(
            StockDailyOHLC.date,
            func.sum(case((StockDailyOHLC.source == "twse", 1), else_=0)),
            func.sum(case((StockDailyOHLC.source == "tpex", 1), else_=0)),
        )
        .group_by(StockDailyOHLC.date)
        .order_by(StockDailyOHLC.date.desc())
        .all()
    )
    for date, twse_n, tpex_n in rows:
        if (twse_n or 0) >= MIN_TWSE_ROWS_COMPLETE and (tpex_n or 0) >= MIN_TPEX_ROWS_COMPLETE:
            return date
    if rows:
        logger.warning(
            "screener: no date has both TWSE(>=%d) and TPEx(>=%d) rows; falling back to "
            "latest date %s, which may be a single-source partial day.",
            MIN_TWSE_ROWS_COMPLETE, MIN_TPEX_ROWS_COMPLETE, rows[0][0],
        )
        return rows[0][0]
    return None


def _universe_tickers_for_date(session, target_date: str) -> List[str]:
    rows = (
        session.query(StockDailyOHLC.ticker)
        .filter(StockDailyOHLC.date == target_date)
        .distinct()
        .all()
    )
    return [t[0] for t in rows if passes_universe(t[0])]


def _load_ticker_window(session, ticker: str, target_date: str) -> Tuple[List[str], List[float], List[float]]:
    """Last ``MA_LONG`` sessions (<= target_date) for a ticker, chronological."""
    rows = (
        session.query(StockDailyOHLC.date, StockDailyOHLC.close, StockDailyOHLC.volume)
        .filter(StockDailyOHLC.ticker == ticker, StockDailyOHLC.date <= target_date)
        .order_by(StockDailyOHLC.date.desc())
        .limit(MA_LONG)
        .all()
    )
    rows = list(reversed(rows))  # chronological
    dates = [r[0] for r in rows]
    closes = [r[1] for r in rows if r[1] is not None]
    volumes = [(r[2] if r[2] is not None else 0.0) for r in rows]
    # Guard against any null close dropping the length out of sync.
    if len(closes) != len(dates):
        return [], [], []
    return dates, closes, volumes


def _load_institutional(session, ticker: str, target_date: str) -> Dict[str, Tuple[Optional[float], Optional[float]]]:
    rows = (
        session.query(
            StockInstitutionalDaily.date,
            StockInstitutionalDaily.foreign_net_shares,
            StockInstitutionalDaily.trust_net_shares,
        )
        .filter(StockInstitutionalDaily.ticker == ticker, StockInstitutionalDaily.date <= target_date)
        .order_by(StockInstitutionalDaily.date.desc())
        .limit(INSTITUTION_LOOKBACK)
        .all()
    )
    return {r[0]: (r[1], r[2]) for r in rows}


def refresh_screener_for_date_sync(target_date: Optional[str] = None) -> int:
    """Compute + persist the screener candidates for one trading day (sync).

    Defaults ``target_date`` to the latest date present in ``stock_daily_ohlc``.
    Re-running a date overwrites that date's rows (idempotent). Returns the number
    of candidate rows written. Never raises — logs and returns 0 on failure.
    """
    try:
        for session in get_session():
            date = target_date or _latest_complete_ohlc_date(session)
            if not date:
                return 0

            pool: List[dict] = []
            for ticker in _universe_tickers_for_date(session, date):
                dates, closes, volumes = _load_ticker_window(session, ticker, date)
                if len(closes) < MIN_SESSIONS:
                    continue
                insti = _load_institutional(session, ticker, date)
                metrics = compute_stage1_metrics(dates, closes, volumes, insti)
                if metrics is not None:
                    metrics["ticker"] = ticker
                    pool.append(metrics)

            scored = score_pool(pool)

            # Idempotent overwrite for this date.
            session.query(ScreenerCandidate).filter(ScreenerCandidate.date == date).delete()
            for m in scored:
                session.add(
                    ScreenerCandidate(
                        date=date,
                        ticker=m["ticker"],
                        rank=m["rank"],
                        final_score=m["final_score"],
                        momentum_score=m["momentum_score"],
                        institution_score=m["institution_score"],
                        factors=_factors_payload(m),
                        is_60d_high=bool(m["is_60d_high"]),
                        crowded=bool(m["crowded"]),
                    )
                )
            session.commit()
            logger.info(f"screener: wrote {len(scored)} candidate(s) for {date}.")
            return len(scored)
    except Exception as e:
        logger.warning(f"screener: refresh failed for {target_date or 'latest'}: {e}")
    return 0


async def refresh_screener_for_date(target_date: Optional[str] = None) -> int:
    """Async wrapper around :func:`refresh_screener_for_date_sync` (runs in a thread)."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, refresh_screener_for_date_sync, target_date)


async def run_periodic_screener_refresh(interval_hours: float = 24.0) -> None:
    """Background loop: compute the latest day's candidates on startup, then daily.

    Intended to run AFTER the daily OHLC/institutional refresh has populated the
    warm tables. Never raises.
    """
    while True:
        try:
            await refresh_screener_for_date()
        except Exception as e:
            logger.warning(f"screener refresh cycle failed: {e}")
        await asyncio.sleep(interval_hours * 3600)
