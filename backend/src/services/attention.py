"""聲量水位 — where a ticker's podcast attention sits inside its own trailing year.

One definition, one owner. The stock page's chart pane and (if it ever carries the
number) the weekly rollup both read this function, so they cannot drift into two
percentiles in two languages.

Why a percentile and not the share of site-wide mentions: the share's scale moves with
how much we ingest. When the roster grew in 2025-08 the median mentioned ticker's share
fell to 15–27% of its previous level with nothing about the stocks changing, and a share
is never comparable between a name that is always discussed (TSMC ~10% of everything)
and one that rarely is. Ranking each day against the ticker's own year cancels both.
Of 15 normalisations tested on 2020–2026 data this was the only family that read the
same before and after the roster change (2026-09-10 sentiment quantamental report).
"""
import asyncio
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

from sqlalchemy import func

from src.database.models import ContentMention
from src.database.postgres import get_session

HALF_LIFE_DAYS = 7.0


def scope_mentions(query, allowed: Optional[frozenset]):
    """Restrict a ContentMention query to the release roster.

    `allowed` is PodcastService._allowed_podcast_names(): resolve it in the async
    endpoint and pass it into the sync query — never call the async method from inside
    a thread. None means no language scope is configured (filter off); an empty set
    fails closed, matching the episode surfaces.

    ContentMention reads never pass through PodcastService's read chokepoint, so every
    reader (mention lists, heat, 聲量水位, the weekly's track record) must go through this
    one function or an English batch landing in the store moves every TW ticker's
    numbers — and, because the level ranks each day against a trailing year, keeps
    moving them for a year after.
    """
    return query if allowed is None else query.filter(ContentMention.podcaster.in_(allowed))
WINDOW_DAYS = 364
# ~60 trading sessions. A freshly ingested ticker shows nothing rather than a percentile
# computed against three weeks.
MIN_HISTORY_DAYS = 84
# Below this much market-wide heat a share is one loud day divided by another, not a
# measurement; those days get no share and therefore no level.
MIN_MARKET_HEAT = 30.0


def attention_level(
    ticker_daily: Dict[date, int],
    market_daily: Dict[date, int],
    until: date,
) -> List[dict]:
    """Daily 0–100 level for every calendar day up to `until` that has enough history.

    Both inputs are raw daily mention counts (ticker's own, and every ticker's) drawn
    from the same scoped population. Heat decays by 0.5 ** (age / HALF_LIFE_DAYS) per
    calendar day; share = ticker heat / market heat; level = share's percentile rank
    (inclusive) among the shares of the trailing WINDOW_DAYS, once at least
    MIN_HISTORY_DAYS of shares exist in that window.
    """
    if not market_daily:
        return []
    start = min(market_daily)
    decay = 0.5 ** (1.0 / HALF_LIFE_DAYS)
    heat = 0.0
    market = 0.0
    shares: List[tuple] = []  # (day, share), in day order
    out: List[dict] = []
    day = start
    window = timedelta(days=WINDOW_DAYS)
    head = 0
    while day <= until:
        heat = heat * decay + ticker_daily.get(day, 0)
        market = market * decay + market_daily.get(day, 0)
        if market >= MIN_MARKET_HEAT:
            share = heat / market
            shares.append((day, share))
            while shares[head][0] < day - window:
                head += 1
            n = len(shares) - head
            if n >= MIN_HISTORY_DAYS:
                # ponytail: O(window) scan per day, ~730 × ~364; a sorted window if it ever matters.
                le = sum(1 for _, s in shares[head:] if s <= share)
                out.append({"d": day.isoformat(), "p": round(le / n * 100)})
        day += timedelta(days=1)
    return out


# ── 聲量水位 movers: the week's tickers at their own-year high / low ─────────────
# One owner for the number and the list: the paid weekly's 資料附錄, the weekly video's
# scene 3 and the Threads weekly copy all read this. State only — the level and which
# end of its own year a ticker sits at — never a forward return (投顧法 line, agreed
# 2026-09-13 with the weekly session).

MOVER_HIGH = 90
MOVER_LOW = 10
MOVER_LIMIT = 8


def _week_bounds(week: str) -> tuple[date, date]:
    y, w = week.split("-W")
    monday = date.fromisocalendar(int(y), int(w), 1)
    return monday, monday + timedelta(days=6)


def _movers_query(start: date, end: date, allowed: Optional[frozenset]) -> dict:
    """Daily ticker counts (all history, for the levels) and the week's mention stats."""
    day = func.date(ContentMention.mentioned_at)
    for db in get_session():
        rows = scope_mentions(db.query(ContentMention.ticker, day, func.count(1)), allowed).filter(
            ContentMention.mention_type == "ticker", ContentMention.ticker.isnot(None),
        ).group_by(ContentMention.ticker, day).all()
        week = scope_mentions(db.query(ContentMention.ticker, func.count(1), func.count(func.distinct(ContentMention.podcaster))), allowed).filter(
            ContentMention.mention_type == "ticker", ContentMention.ticker.isnot(None),
            ContentMention.mentioned_at >= datetime.combine(start, datetime.min.time()),
            ContentMention.mentioned_at < datetime.combine(end + timedelta(days=1), datetime.min.time()),
        ).group_by(ContentMention.ticker).all()
        from src.services.paid_weekly import query_names  # lazy: paid_weekly imports this module
        names = query_names(db, {t for t, _, _ in week})
        return {"daily": rows, "week": week, "names": names}
    return {"daily": [], "week": [], "names": {}}


async def attention_movers(week: str, *, allowed: Optional[frozenset]) -> dict:
    """Tickers the roster mentioned inside ``week`` whose 聲量水位 on the week's last day
    is ≥ MOVER_HIGH (``high``, level desc) or ≤ MOVER_LOW (``low``, level asc), top
    MOVER_LIMIT each. Levels come from attention_level() with the same roster scope as
    the stock page, so the two never disagree."""
    start, end = _week_bounds(week)
    q = await asyncio.to_thread(_movers_query, start, end, allowed)
    per_ticker: Dict[str, Dict[date, int]] = defaultdict(dict)
    market: Dict[date, int] = defaultdict(int)
    for ticker, d, n in q["daily"]:
        d = d if isinstance(d, date) else date.fromisoformat(str(d))
        per_ticker[ticker][d] = int(n)
        market[d] += int(n)
    high, low = [], []
    for ticker, mentions, shows in q["week"]:
        levels = attention_level(per_ticker.get(ticker, {}), market, end)
        if not levels or levels[-1]["d"] != end.isoformat():
            continue  # no share on the last day (market too thin) → no state to report
        level = levels[-1]["p"]
        row = {"ticker": ticker, "name": q["names"].get(ticker), "level": level,
               "share": None, "mentions": int(mentions), "shows": int(shows)}
        if level >= MOVER_HIGH:
            high.append(row)
        elif level <= MOVER_LOW:
            low.append(row)
    high.sort(key=lambda r: (-r["level"], -r["mentions"], r["ticker"]))
    low.sort(key=lambda r: (r["level"], -r["mentions"], r["ticker"]))
    return {"week": week, "start": start.isoformat(), "end": end.isoformat(),
            "high": high[:MOVER_LIMIT], "low": low[:MOVER_LIMIT]}
