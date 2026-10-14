"""Index quotes from Yahoo Finance's chart endpoint — the only intraday source we have.

FinMind is polled REST and Massive is 15 minutes delayed on our plan, and neither carries
the Nikkei or KOSPI at all. Yahoo's ``/v8/finance/chart`` returns one-minute bars for every
index we care about with no key. It is an unofficial endpoint: the owner reviewed that
and chose it (2026-10-14) because the market-move posts are not monetised. Treat it as
best-effort — every caller must survive ``YahooChartError`` by posting nothing.

Cached for a minute in Redis so the card route and the detector share one fetch.
"""
from __future__ import annotations

import asyncio
import json
import logging
import statistics
from dataclasses import asdict, dataclass, field
from typing import Optional

import httpx

from src.cache.redis_client import cache_get, cache_set

logger = logging.getLogger(__name__)

CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
NEWS_URL = "https://query1.finance.yahoo.com/v1/finance/search"
# Without a browser UA the endpoint answers 429 to most datacentre IPs.
_HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"}
_TIMEOUT = 10.0
_RETRIES = 2
INTRADAY_TTL = 60
DAILY_TTL = 6 * 3600
NEWS_TTL = 300


class YahooChartError(Exception):
    """Yahoo answered nothing usable — network, status, or a payload without bars."""


@dataclass
class Intraday:
    symbol: str
    tz: str                     # IANA, e.g. Asia/Tokyo
    prev_close: float
    session_start: int          # epoch seconds, today's regular session
    session_end: int
    points: list[tuple[int, float]] = field(default_factory=list)  # (epoch s, close), ascending

    @property
    def last(self) -> float:
        return self.points[-1][1]

    @property
    def last_ts(self) -> int:
        return self.points[-1][0]

    @property
    def change(self) -> float:
        return self.last - self.prev_close

    @property
    def pct(self) -> float:
        return self.change / self.prev_close * 100

    @property
    def open(self) -> float:
        return self.points[0][1]

    @property
    def high(self) -> float:
        return max(v for _, v in self.points)

    @property
    def low(self) -> float:
        return min(v for _, v in self.points)

    def until(self, ts: Optional[int]) -> "Intraday":
        """The same day cut at ``ts`` — a card rendered after the post must show what
        the post saw, not the minutes Meta's crawler happened to fetch it at."""
        if ts is None:
            return self
        pts = [p for p in self.points if p[0] <= ts]
        if not pts:
            raise YahooChartError(f"{self.symbol}: no bars at or before {ts}")
        return Intraday(self.symbol, self.tz, self.prev_close, self.session_start, self.session_end, pts)


async def _get_json(url: str, params: dict) -> dict:
    last: Exception = YahooChartError("not attempted")
    for attempt in range(_RETRIES + 1):
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_HEADERS) as client:
                resp = await client.get(url, params=params)
            if resp.status_code == 200:
                return resp.json()
            last = YahooChartError(f"yahoo {url} {params} -> HTTP {resp.status_code}")
            if resp.status_code not in (429, 500, 502, 503, 504):
                break
        except (httpx.HTTPError, ValueError) as e:
            last = YahooChartError(f"yahoo {url} {params} -> {type(e).__name__}: {e}")
        if attempt < _RETRIES:
            await asyncio.sleep(1.5 * (attempt + 1))
    logger.warning("%s", last)
    raise last


def _result(payload: dict, symbol: str) -> dict:
    chart = (payload or {}).get("chart") or {}
    results = chart.get("result") or []
    if not results:
        raise YahooChartError(f"{symbol}: no result ({chart.get('error')})")
    return results[0]


def parse_intraday(payload: dict, symbol: str) -> Intraday:
    """Yahoo's ``range=1d&interval=1m`` payload → :class:`Intraday`. Null bars (Yahoo
    leaves a slot for every minute, traded or not) are dropped."""
    r = _result(payload, symbol)
    meta = r.get("meta") or {}
    prev = meta.get("previousClose") or meta.get("chartPreviousClose")
    regular = (meta.get("currentTradingPeriod") or {}).get("regular") or {}
    closes = ((r.get("indicators") or {}).get("quote") or [{}])[0].get("close") or []
    pts = [(int(t), float(c)) for t, c in zip(r.get("timestamp") or [], closes) if c is not None]
    if not prev or not pts or not regular.get("start") or not regular.get("end"):
        raise YahooChartError(f"{symbol}: payload missing previous close, bars or session")
    return Intraday(symbol=symbol, tz=meta.get("exchangeTimezoneName") or "UTC", prev_close=float(prev),
                    session_start=int(regular["start"]), session_end=int(regular["end"]), points=pts)


def parse_daily_closes(payload: dict, symbol: str) -> list[float]:
    r = _result(payload, symbol)
    closes = ((r.get("indicators") or {}).get("quote") or [{}])[0].get("close") or []
    return [float(c) for c in closes if c is not None]


def daily_sigma(closes: list[float]) -> Optional[float]:
    """Standard deviation of daily % returns — what "a big day" means for THIS index.
    A 2% day is routine for the SOX and rare for the Dow; one fixed threshold misfires."""
    rets = [(b - a) / a * 100 for a, b in zip(closes, closes[1:]) if a]
    return statistics.stdev(rets) if len(rets) >= 20 else None


async def intraday(symbol: str) -> Intraday:
    key = f"yahoo:intraday:{symbol}"
    cached = await cache_get(key)
    if cached:
        d = json.loads(cached)
        d["points"] = [tuple(p) for p in d["points"]]
        return Intraday(**d)
    data = parse_intraday(await _get_json(CHART_URL.format(symbol=symbol),
                                          {"range": "1d", "interval": "1m"}), symbol)
    await cache_set(key, json.dumps(asdict(data)), INTRADAY_TTL)
    return data


async def sigma(symbol: str) -> Optional[float]:
    key = f"yahoo:sigma:{symbol}"
    cached = await cache_get(key)
    if cached:
        return json.loads(cached)
    closes = parse_daily_closes(await _get_json(CHART_URL.format(symbol=symbol),
                                                {"range": "6mo", "interval": "1d"}), symbol)
    value = daily_sigma(closes)
    await cache_set(key, json.dumps(value), DAILY_TTL)
    return value


def parse_news(payload: dict) -> list[dict]:
    out = []
    for n in (payload or {}).get("news") or []:
        title, link = (n.get("title") or "").strip(), n.get("link") or ""
        if title and link:
            out.append({"title": title, "publisher": (n.get("publisher") or "").strip(),
                        "url": link, "published": int(n.get("providerPublishTime") or 0)})
    return out


async def news(query: str, count: int = 12) -> list[dict]:
    """Headlines Yahoo associates with ``query`` — title, publisher, link, epoch."""
    key = f"yahoo:news:{query}"
    cached = await cache_get(key)
    if cached:
        return json.loads(cached)
    items = parse_news(await _get_json(NEWS_URL, {"q": query, "newsCount": count, "quotesCount": 0}))
    await cache_set(key, json.dumps(items), NEWS_TTL)
    return items
