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
from datetime import date, timedelta
from typing import Dict, List, Optional

from src.database.models import ContentMention

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
