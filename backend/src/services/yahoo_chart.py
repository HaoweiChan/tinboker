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

from curl_cffi.requests import AsyncSession
from curl_cffi.requests.exceptions import RequestException

from src.cache.redis_client import cache_get, cache_set

logger = logging.getLogger(__name__)

CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
SPARK_URL = "https://query1.finance.yahoo.com/v8/finance/spark"
SPARK_BATCH = 20
# 5 min: the giants prefilter only nominates names for a full chart fetch, so a quote
# a few minutes old is enough, and it re-asks Yahoo a fifth as often as a 60s tick.
SPARK_TTL = 300
# 2, not 6: six concurrent spark calls from the VPS drew HTTP 429 on most batches of a
# theme scan in the first prod window (v0.14.4, 2026-10-15, ~13 per scan).
SPARK_CONCURRENCY = 2
# The whole batched scan, not one request: every theme's members is ~30 batches, and a
# serial, retrying walk over them outlived Cloudflare's 100s edge timeout on dev. At
# concurrency 2 those batches need ~15 rounds, so 60s, still under that edge timeout.
SPARK_BUDGET = 60.0
NEWS_URL = "https://query1.finance.yahoo.com/v1/finance/search"
# Yahoo answers 429 to plain Python HTTP clients from datacenter IPs — verified on dev
# 2026-10-15, every chart call from the VPS was a 429 over httpx. It fingerprints the
# TLS handshake, not the User-Agent, so the request has to look like a browser's:
# curl_cffi impersonating Chrome, the same fix yfinance (already a dependency here)
# ships for the same 429s.
_IMPERSONATE = "chrome"
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


async def _get_json(url: str, params: dict, retries: int = _RETRIES) -> dict:
    last: Exception = YahooChartError("not attempted")
    for attempt in range(retries + 1):
        try:
            async with AsyncSession(impersonate=_IMPERSONATE, timeout=_TIMEOUT) as client:
                resp = await client.get(url, params=params)
            if resp.status_code == 200:
                return resp.json()
            last = YahooChartError(f"yahoo {url} {params} -> HTTP {resp.status_code}")
            if resp.status_code not in (429, 500, 502, 503, 504):
                break
        except (RequestException, ValueError) as e:
            last = YahooChartError(f"yahoo {url} {params} -> {type(e).__name__}: {e}")
        if attempt < retries:
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


@dataclass
class Quote:
    symbol: str
    prev_close: float
    last: float
    last_ts: int

    @property
    def pct(self) -> float:
        return (self.last - self.prev_close) / self.prev_close * 100


def _quote(symbol: str, prev, timestamps, closes) -> Optional[Quote]:
    pts = [(int(t), float(c)) for t, c in zip(timestamps or [], closes or []) if c is not None]
    if not prev or not pts:
        return None
    return Quote(symbol, float(prev), pts[-1][1], pts[-1][0])


def parse_spark(payload: dict) -> dict[str, Quote]:
    """Yahoo's spark answers in two shapes depending on the path/version it routes to:
    ``{SYM: {timestamp, close, chartPreviousClose}}`` or
    ``{spark: {result: [{symbol, response: [<chart result>]}]}}``. Accept both; a
    symbol missing from either is simply absent from the map."""
    out: dict[str, Quote] = {}
    if not isinstance(payload, dict):
        return out
    results = ((payload.get("spark") or {}).get("result")) if "spark" in payload else None
    if results is not None:
        for item in results or []:
            for r in (item or {}).get("response") or []:
                meta = r.get("meta") or {}
                closes = ((r.get("indicators") or {}).get("quote") or [{}])[0].get("close")
                q = _quote(item.get("symbol") or meta.get("symbol"),
                           meta.get("previousClose") or meta.get("chartPreviousClose"), r.get("timestamp"), closes)
                if q and q.symbol:
                    out[q.symbol] = q
        return out
    for sym, d in payload.items():
        if isinstance(d, dict):
            q = _quote(d.get("symbol") or sym, d.get("previousClose") or d.get("chartPreviousClose"),
                       d.get("timestamp"), d.get("close"))
            if q:
                out[q.symbol] = q
    return out


async def quotes(symbols: list[str], budget: float = SPARK_BUDGET) -> dict[str, Quote]:
    """Last price vs previous close for many symbols, 20 per request — what a basket or
    a watchlist scan needs, at a fraction of one chart call per name. Batches run
    ``SPARK_CONCURRENCY`` at a time with no retries, under one ``SPARK_BUDGET`` for the
    whole scan; a failed or late batch drops its symbols rather than the scan."""
    out: dict[str, Quote] = {}
    todo = []
    for sym in dict.fromkeys(symbols):
        cached = await cache_get(f"yahoo:quote:{sym}")
        if cached:
            out[sym] = Quote(**json.loads(cached))
        else:
            todo.append(sym)
    gate = asyncio.Semaphore(SPARK_CONCURRENCY)

    async def fetch(batch: list[str]) -> dict[str, Quote]:
        async with gate:
            try:
                return parse_spark(await _get_json(
                    SPARK_URL, {"symbols": ",".join(batch), "range": "1d", "interval": "5m"}, retries=0))
            except YahooChartError:
                return {}

    tasks = [asyncio.create_task(fetch(todo[i:i + SPARK_BATCH])) for i in range(0, len(todo), SPARK_BATCH)]
    if not tasks:
        return out
    done, late = await asyncio.wait(tasks, timeout=budget)
    for t in late:
        t.cancel()
    if late:
        logger.warning("yahoo quotes: %d of %d batches missed the %.0fs budget", len(late), len(tasks), budget)
    for t in done:
        for sym, q in t.result().items():
            out[sym] = q
            await cache_set(f"yahoo:quote:{sym}", json.dumps(asdict(q)), SPARK_TTL)
    return out


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
