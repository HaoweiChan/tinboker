"""Intraday market-move flash posts: when an index, one of the market's giants, or one of
TinBoker's own themes has a big morning, say so on Threads within the first hour, with a
card and one line on why.

Speed over completeness, on purpose. The close-of-day write-up (full news, highlighted
sources) is a separate, later post; this one exists because by the close the reaction is
over. So the rules are about not being wrong fast:

  * "big" is relative: an index or a stock against its own volatility
    (``yahoo_chart.daily_sigma``) with a floor in percent — a 2% SOX day is a Tuesday, a
    2% Dow day is news; a theme by the median of its members, with most of them moving
    the same way, so one limit-up name does not make a theme;
  * an index or stock must still be holding (at least half of its extreme so far), so an
    opening gap that has already filled is not posted as a crash;
  * the post is one plain sentence — what moved, how much, and why — not a data
    block: the numbers are on the card. Its hedge is decided here, not by the model:
    two or more publishers attributing the move to the same driver → 主因…; one →
    市場推測與…有關. The model only extracts;
  * no reason, no post. A number without a story is what the card already says —
    the tick tries again later in the window, when the wires may have caught up.

Three lanes per market, same rules, separate budgets, tried in this order:

  * index  — once per market per day (``market_move:intraday:{market}:{date}``);
  * stock  — the market's giants (``MARKETS[*].stocks``: the TWSE market-cap leaders and
    the largest US names, researched 2026-10), at most ``MARKET_MOVE_MAX_STOCK_POSTS``
    per market per day, each once (``market_move:stock:{market}:{date}:{id}``). A stock
    also needs ``MARKET_MOVE_STOCK_MIN_PCT`` — a 1% TSMC morning is not news;
  * theme  — TinBoker's theme registry (tag_registry sector rows, exposure_type theme):
    each theme's members in this market form a basket; at most
    ``MARKET_MOVE_MAX_THEME_POSTS`` per market per day
    (``market_move:theme:{market}:{date}:{exposure_id}``). Scanned every
    ``THEME_SCAN_EVERY`` rather than every tick: it is one batched quote call per 20
    members across every theme.

At most one post per market per tick, so lanes never fire together.
Off unless ``MARKET_MOVE_MARKETS`` is set — same one-environment rule as the posting slots.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
import statistics
import urllib.parse
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

import httpx

from src.config import settings
from src.services import social_ledger, yahoo_chart
from src.services.threads_service import ThreadsError, ThreadsService
from src.services.yahoo_chart import Intraday, Quote, YahooChartError

logger = logging.getLogger(__name__)

PLATFORM = "threads"
FORMAT = "market_move_intraday"
HOLD_RATIO = 0.5             # keep at least half of the day's extreme so far
NEWS_MAX_AGE_HOURS = 20      # overnight + pre-market; older is yesterday's story
CAUSE_MAX_CHARS = 32
STALE_SECONDS = 30 * 60      # Yahoo delays some index feeds; older than this is not "now"
RETRY_AFTER = timedelta(minutes=10)
# 15 min: a theme move has to hold inside a 90-minute window anyway, and every scan is
# ~30 spark batches; at 5 min they were the 429 bursts in the first prod window.
THEME_SCAN_EVERY = timedelta(minutes=15)
THEME_MIN_MEMBERS = 3        # fewer quoted members than this is a pair, not a theme
THEME_BREADTH = 0.7          # share of members that must move with the median
THEME_CARD_ROWS = 10
_retry_at: dict[str, datetime] = {}   # key -> earliest retry after a failed publish / no reason
_theme_scanned_at: dict[str, datetime] = {}   # market id -> last theme scan
ALERT_AFTER = 5              # consecutive failing ticks (minutes) before admins are told
_problems: list[str] = []    # what went wrong in the current tick
_health: dict = {"fails": 0, "alerted": False, "last": ""}


@dataclass(frozen=True)
class Instrument:
    symbol: str              # Yahoo symbol: ^N225, 2330.TW, NVDA
    name: str                # short, for the card
    spoken: str = ""         # as a sentence names it; defaults to ``name``
    news_query: str = ""     # what Yahoo's news search knows it as (stocks only)

    @property
    def said(self) -> str:
        return self.spoken or self.name

    @property
    def id(self) -> str:     # path-safe, for the card URL: ^TWII → TWII, 2330.TW → 2330_TW
        return self.symbol.lstrip("^").replace(".", "_")

    @property
    def code(self) -> str:   # what the card prints next to the name
        return self.symbol.lstrip("^").split(".")[0]

    @property
    def is_index(self) -> bool:
        return self.symbol.startswith("^")


@dataclass(frozen=True)
class Market:
    id: str
    name: str
    tz: str
    open_hm: tuple[int, int]
    indices: tuple[Instrument, ...]
    news_query: str
    stocks: tuple[Instrument, ...] = ()


# Giants, by what actually moves the index (researched 2026-10):
#   TW — the TWSE market-cap top 20 (兆元俱樂部), minus 中華電: a utility that does not
#        have mornings. Financials stay; the 3% floor keeps them quiet unless it matters.
#   US — the largest US-listed names by market cap, plus TSM (the ADR is how Taiwan
#        reads the night), MU and AMD (memory and the other AI GPU — top 15 by cap).
I = Instrument  # noqa: E741 — the registry below reads better short
MARKETS: dict[str, Market] = {m.id: m for m in (
    Market("TW", "台股", "Asia/Taipei", (9, 0),
           (I("^TWII", "加權指數", "台股加權指數"), I("^TWOII", "櫃買指數")), "Taiwan stocks TAIEX",
           (I("2330.TW", "台積電", news_query="TSMC"), I("2454.TW", "聯發科", news_query="MediaTek"),
            I("2308.TW", "台達電", news_query="Delta Electronics"), I("2317.TW", "鴻海", news_query="Foxconn Hon Hai"),
            I("3711.TW", "日月光投控", news_query="ASE Technology"), I("2383.TW", "台光電", news_query="Elite Material"),
            I("2881.TW", "富邦金", news_query="Fubon Financial"), I("3037.TW", "欣興", news_query="Unimicron"),
            I("2303.TW", "聯電", news_query="United Microelectronics UMC"), I("1303.TW", "南亞", news_query="Nan Ya Plastics"),
            I("2408.TW", "南亞科", news_query="Nanya Technology"), I("2882.TW", "國泰金", news_query="Cathay Financial"),
            I("2382.TW", "廣達", news_query="Quanta Computer"), I("2891.TW", "中信金", news_query="CTBC Financial"),
            I("2327.TW", "國巨", news_query="Yageo"), I("2345.TW", "智邦", news_query="Accton Technology"),
            I("2059.TW", "川湖", news_query="King Slide"), I("3017.TW", "奇鋐", news_query="Asia Vital Components"))),
    Market("US", "美股", "America/New_York", (9, 30),
           (I("^GSPC", "S&P 500", "標普500指數"), I("^IXIC", "那斯達克", "那斯達克指數"),
            I("^SOX", "費城半導體", "費城半導體指數"), I("^DJI", "道瓊", "道瓊指數")),
           "stock market today",
           (I("NVDA", "輝達", news_query="Nvidia"), I("AAPL", "蘋果", news_query="Apple"),
            I("GOOGL", "Alphabet", "Google母公司Alphabet", "Alphabet Google"), I("MSFT", "微軟", news_query="Microsoft"),
            I("AMZN", "亞馬遜", news_query="Amazon"), I("SPCX", "SpaceX", news_query="SpaceX"),
            I("META", "Meta", news_query="Meta Platforms"), I("AVGO", "博通", news_query="Broadcom"),
            I("TSLA", "特斯拉", news_query="Tesla"), I("MU", "美光", news_query="Micron"),
            I("AMD", "超微", news_query="AMD"), I("TSM", "台積電ADR", news_query="TSMC ADR"))),
    Market("JP", "日股", "Asia/Tokyo", (9, 0), (I("^N225", "日經225", "日經225指數"),), "Nikkei"),
    Market("KR", "韓股", "Asia/Seoul", (9, 0),
           (I("^KS11", "KOSPI", "韓國KOSPI指數"), I("^KQ11", "KOSDAQ", "韓國KOSDAQ指數")), "KOSPI"),
)}
del I
BY_ID: dict[str, tuple[Market, Instrument]] = {
    i.id: (m, i) for m in MARKETS.values() for i in (*m.indices, *m.stocks)}
LANES = ("index", "stock", "theme")
THEME_MARKETS = ("TW", "US")  # the registry only carries TW and US tickers


@dataclass
class Move:
    index: Instrument
    day: Intraday
    sigma: Optional[float]

    @property
    def z(self) -> Optional[float]:
        return abs(self.day.pct) / self.sigma if self.sigma else None


@dataclass
class Basket:
    """One theme's members in one market."""
    exposure_id: str
    name: str
    members: list[Instrument] = field(default_factory=list)


@dataclass
class ThemeMove:
    basket: Basket
    rows: list[tuple[Instrument, Quote]]   # quoted members, biggest move in the median's direction first

    @property
    def median(self) -> float:
        return statistics.median(q.pct for _, q in self.rows)

    @property
    def last_ts(self) -> int:
        return max(q.last_ts for _, q in self.rows)

    @property
    def leaders(self) -> list[Instrument]:
        return [i for i, _ in self.rows[:2]]


# ── pure rules ──────────────────────────────────────────────────────────────

def window_date(market: Market, now: datetime) -> Optional[date]:
    """The market's local date when ``now`` falls in today's detection window
    (open + delay, for ``window`` minutes), else None. Weekends never; holidays are
    caught later by the data (the session Yahoo returns is not today's)."""
    local = now.astimezone(ZoneInfo(market.tz))
    if local.weekday() >= 5:
        return None
    opened = local.replace(hour=market.open_hm[0], minute=market.open_hm[1], second=0, microsecond=0)
    start = opened + timedelta(minutes=settings.market_move_delay_minutes)
    if start <= local < start + timedelta(minutes=settings.market_move_window_minutes):
        return local.date()
    return None


def is_today(day: Intraday, today: date, now: datetime) -> bool:
    """Yahoo serves the last session on a holiday — only today's, still ticking, counts."""
    tz = ZoneInfo(day.tz)
    return (datetime.fromtimestamp(day.session_start, tz).date() == today
            and now.timestamp() - day.last_ts < STALE_SECONDS)


def quote_is_live(q: Quote, market: Market, today: date, now: datetime) -> bool:
    return (datetime.fromtimestamp(q.last_ts, ZoneInfo(market.tz)).date() == today
            and now.timestamp() - q.last_ts < STALE_SECONDS)


def is_big(day: Intraday, sigma: Optional[float], *, k: float, floor_pct: float) -> bool:
    pct = day.pct
    if abs(pct) < floor_pct or (sigma and abs(pct) < k * sigma):
        return False
    direction = 1 if pct > 0 else -1
    extreme = max((v - day.prev_close) * direction for _, v in day.points)
    return day.change * direction >= HOLD_RATIO * extreme


def theme_move(basket: Basket, quotes: dict[str, Quote], *, floor_pct: float) -> Optional[ThemeMove]:
    """The basket as a move, or None: too few quoted members, a median under the floor,
    or a move carried by a few names while the rest sit still or go the other way."""
    rows = [(m, quotes[m.symbol]) for m in basket.members if m.symbol in quotes]
    if len(rows) < THEME_MIN_MEMBERS:
        return None
    med = statistics.median(q.pct for _, q in rows)
    if abs(med) < floor_pct:
        return None
    direction = 1 if med > 0 else -1
    if sum(1 for _, q in rows if q.pct * direction > 0) / len(rows) < THEME_BREADTH:
        return None
    rows.sort(key=lambda r: r[1].pct * direction, reverse=True)
    return ThemeMove(basket, rows)


def headline_move(moves: list[Move]) -> Move:
    """The instrument the post leads with: the most unusual one, not the biggest percent."""
    return max(moves, key=lambda m: (m.z or 0, abs(m.day.pct)))


def verb(pct: float) -> str:
    if pct >= 0:
        return "急漲" if pct >= 3 else "大漲"
    return "重挫" if pct <= -3 else "大跌"


def amount(pct: float) -> str:
    """How a person says the size: 4.19 → 逾4%, 3.02 → 3%. The exact figure is on the card."""
    a = abs(pct)
    n = int(a)
    if n < 1:
        return f"{a:.1f}%"
    return f"逾{n}%" if a - n >= 0.1 else f"{n}%"


def cause_text(cause: str, publishers: set[str]) -> tuple[str, str]:
    """``(tier, clause)``. The hedge is chosen from how many publishers back the
    cause — never from the model's own confidence."""
    cause = cause.strip().rstrip("。.，,")
    if not cause or len(cause) > CAUSE_MAX_CHARS or "\n" in cause:
        return "none", ""
    if len(publishers) >= 2:
        return "consensus", f"主因{cause}"
    if len(publishers) == 1:
        return "reported", f"市場推測與{cause}有關"
    return "none", ""


def _sentence(head: str, clause: str) -> str:
    return f"{head}，{clause}。" if clause else f"{head}。"


def compose_text(lead: Move, clause: str) -> str:
    """One sentence, the way a person would tell it: 費城半導體指數盤中重挫逾3%，市場推測與…有關。
    No headline tag, no price block — the card carries the numbers."""
    return _sentence(f"{lead.index.said}盤中{verb(lead.day.pct)}{amount(lead.day.pct)}", clause)


def compose_theme_text(move: ThemeMove, clause: str) -> str:
    """散熱族群盤中急漲，奇鋐、雙鴻領漲，主因…。 — the theme, who led it, and why."""
    med = move.median
    leaders = "、".join(i.said for i in move.leaders)
    return _sentence(f"{move.basket.name}族群盤中{verb(med)}，{leaders}{'領漲' if med >= 0 else '領跌'}", clause)


def card_url(index: Instrument, until: int, clause: str = "") -> str:
    """The reason rides in the URL too, so the image Meta fetches says what the post says."""
    q = urllib.parse.urlencode({"until": until, **({"reason": clause[:60]} if clause else {})})
    return f"{settings.public_api_url.rstrip('/')}/api/og/market/{index.id}.png?{q}"


def encode_theme_card(market: Market, move: ThemeMove, clause: str = "") -> str:
    """The theme card's whole content, in the path: a basket has no single series to
    re-fetch, and the card must show exactly what the post saw — including its reason."""
    rows = [[i.name, i.code, round(q.pct, 2)] for i, q in move.rows[:THEME_CARD_ROWS]]
    raw = json.dumps({"n": move.basket.name, "z": market.tz, "t": move.last_ts,
                      "m": round(move.median, 2), "c": clause[:60], "r": rows},
                     ensure_ascii=False, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_theme_card(payload: str) -> dict:
    try:
        d = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        rows = [(str(n), str(c), float(p)) for n, c, p in d["r"]]
        out = {"name": str(d["n"]), "tz": str(d["z"]), "ts": int(d["t"]), "median": float(d["m"]),
               "reason": str(d.get("c") or ""), "rows": rows}
        ZoneInfo(out["tz"])
    except Exception as e:  # noqa: BLE001 — one error for every malformed shape
        raise ValueError("payload is not a theme card") from e
    if not rows:
        raise ValueError("theme card has no rows")
    return out


def theme_card_url(market: Market, move: ThemeMove, clause: str = "") -> str:
    return (f"{settings.public_api_url.rstrip('/')}/api/og/market-theme/"
            f"{encode_theme_card(market, move, clause)}.png")


def lane_key(market: Market, today: date, lane: str, subject_id: str = "") -> str:
    if lane == "index":
        return f"market_move:intraday:{market.id}:{today.isoformat()}"
    return f"market_move:{lane}:{market.id}:{today.isoformat()}:{subject_id}"


def fresh_headlines(items: list[dict], now: datetime) -> list[dict]:
    cutoff = now.timestamp() - NEWS_MAX_AGE_HOURS * 3600
    seen, out = set(), []
    for h in items:
        if h["url"] in seen or not (cutoff <= h.get("published", 0) <= now.timestamp() + 300):
            continue
        seen.add(h["url"])
        out.append(h)
    return out[:15]


# ── the reason: the model extracts, the code decides how sure to sound ─────

@dataclass
class Subject:
    """What moved, as the model and the news search need it."""
    kind: str                # 指數 / 個股 / 題材
    label: str               # 台積電（2330.TW） / 「散熱」族群（奇鋐、雙鴻、健策）
    pct: float
    queries: list[str]


def subject_of(market: Market, move: Move | ThemeMove) -> Subject:
    if isinstance(move, ThemeMove):
        names = "、".join(i.name for i, _ in move.rows[:6])
        # Yahoo's search knows the leaders, not a zh theme name.
        queries = [market.news_query, *[i.news_query or i.symbol for i in move.leaders]]
        return Subject("題材", f"「{move.basket.name}」族群（{names}）", move.median, queries)
    inst = move.index
    queries = [market.news_query if inst.is_index else (inst.news_query or inst.code), inst.symbol]
    return Subject("指數" if inst.is_index else "個股", f"{inst.name}（{inst.symbol}）", move.day.pct, queries)


CAUSE_SYSTEM = """你負責從新聞標題中，找出某個股價指數、個股或題材族群今天盤中大幅波動的原因。

只能根據提供的標題判斷，不可使用標題以外的知識或推測。
回傳 JSON：{"cause": "...", "support": [標題編號...]}
- cause：繁體中文名詞短語，30 字以內，具體描述驅動因素本身（事件或市場擔憂的事），例如「美國公債殖利率走升」「輝達財報優於預期」「市場擔憂SpaceX籌資400億美元購買輝達晶片」。要能直接接在「主因」或「市場推測與…有關」中間讀通。不要寫漲跌幅、不要加句號、不要寫「可能」「市場推測」等語氣詞。
- support：明確把「這個標的今天的漲跌」歸因於這個因素的標題編號（標的是指數時，講整個市場今天漲跌的標題也算；標的是題材族群時，講族群內個股或整個產業今天漲跌的標題也算）。
- 沒有任何標題明確解釋這次波動時，回傳 {"cause": "", "support": []}。寧可留白，不要猜。"""


async def _extract_cause(market: Market, subject: Subject, headlines: list[dict]) -> dict:
    listing = "\n".join(f"[{i}] {h['publisher'] or '?'}：{h['title']}" for i, h in enumerate(headlines))
    user = (f"市場：{market.name}；{subject.kind}：{subject.label}"
            f"盤中{'上漲' if subject.pct >= 0 else '下跌'} {abs(subject.pct):.2f}%。\n\n標題：\n{listing}")
    async with httpx.AsyncClient(timeout=45.0) as client:
        resp = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {settings.openrouter_api_key}",
                     "HTTP-Referer": "https://tinboker.com", "X-Title": "TinBoker market move"},
            json={"model": settings.market_move_model, "temperature": 0,
                  "response_format": {"type": "json_object"},
                  "messages": [{"role": "system", "content": CAUSE_SYSTEM},
                               {"role": "user", "content": user}]},
        )
        resp.raise_for_status()
    raw = resp.json()["choices"][0]["message"]["content"].strip()
    match = re.search(r"\{.*\}", raw, re.S)
    return json.loads(match.group(0) if match else raw, strict=False)


async def find_cause(market: Market, subject: Subject, now: datetime) -> dict:
    """``{tier, clause, cause, sources}``. Never raises: a failed lookup is tier none,
    which means no post."""
    empty = {"tier": "none", "clause": "", "cause": "", "sources": []}
    if not settings.openrouter_api_key:
        _problems.append("OPENROUTER_API_KEY 未設定，找不到原因就不會發文")
        return {**empty, "error": "no_openrouter_key"}
    try:
        items = []
        for q in dict.fromkeys(subject.queries):
            items += await yahoo_chart.news(q)
    except YahooChartError as e:
        return {**empty, "error": str(e)[:200]}
    headlines = fresh_headlines(items, now)
    if not headlines:
        return {**empty, "error": "no_fresh_headlines"}
    try:
        out = await _extract_cause(market, subject, headlines)
    except Exception as e:  # noqa: BLE001 — timeout, 5xx, malformed JSON: no reason, no post
        logger.warning("market move cause extraction failed (%s): %s", market.id, e)
        _problems.append(f"OpenRouter 原因萃取失敗：{str(e)[:120]}")
        return {**empty, "error": f"llm: {str(e)[:200]}"}
    ids = [i for i in out.get("support") or [] if isinstance(i, int) and 0 <= i < len(headlines)]
    sources = [headlines[i] for i in dict.fromkeys(ids)]
    publishers = {s["publisher"].lower() for s in sources if s["publisher"]}
    tier, clause = cause_text(str(out.get("cause") or ""), publishers)
    return {"tier": tier, "clause": clause, "cause": str(out.get("cause") or "").strip(),
            "sources": sources if tier != "none" else []}


def sources_reply(sources: list[dict]) -> str:
    lines = ["消息來源："]
    for s in sources[:2]:
        lines.append(f"・{s['publisher'] or '新聞'}：{s['title']}\n{s['url']}")
    return "\n".join(lines)


# ── themes from the registry ────────────────────────────────────────────────

def _tw_suffixes(tickers: list[str]) -> dict[str, str]:
    """``{2330: '.TW', 6488: '.TWO'}`` from the warmed TWSE/TPEx bars — Yahoo needs the
    venue in the symbol. A ticker never warmed defaults to the main board."""
    from sqlalchemy import func

    from src.database.models import StockDailyOHLC
    from src.database.postgres import get_session
    out = {t: ".TW" for t in tickers}
    if not tickers:
        return out
    for db in get_session():
        latest = (db.query(StockDailyOHLC.ticker, func.max(StockDailyOHLC.date).label("d"))
                  .filter(StockDailyOHLC.ticker.in_(tickers)).group_by(StockDailyOHLC.ticker).subquery())
        rows = (db.query(StockDailyOHLC.ticker, StockDailyOHLC.source)
                .join(latest, (StockDailyOHLC.ticker == latest.c.ticker) & (StockDailyOHLC.date == latest.c.d))
                .all())
        for ticker, source in rows:
            if source == "tpex":
                out[ticker] = ".TWO"
    return out


def _load_baskets() -> dict[str, list[Basket]]:
    """``{TW: [...], US: [...]}`` — every visible theme's members, split by market."""
    from src.services.podcast import PodcastService
    from src.utils.market import infer_market
    idx = PodcastService._sector_membership_index()
    meta, members = idx.get("meta", {}), idx.get("members", {})
    themes = {eid: m for eid, m in members.items() if (meta.get(eid) or {}).get("exposure_type") == "theme"}
    tw_codes = sorted({m["ticker"] for ms in themes.values() for m in ms if infer_market(m["ticker"]) == "TW"})
    suffix = _tw_suffixes(tw_codes)
    out: dict[str, list[Basket]] = {"TW": [], "US": []}
    for eid, ms in themes.items():
        name = meta[eid].get("display_name") or eid
        by_market: dict[str, list[Instrument]] = {"TW": [], "US": []}
        for m in ms:
            t, mk = m["ticker"], infer_market(m["ticker"])
            if mk == "TW":
                by_market["TW"].append(Instrument(f"{t}{suffix.get(t, '.TW')}", m.get("name") or t))
            elif mk == "US":
                by_market["US"].append(Instrument(t, m.get("name") or t))
        for mk, insts in by_market.items():
            if len(insts) >= THEME_MIN_MEMBERS:
                out[mk].append(Basket(eid, name, insts))
    return out


_baskets_cache: dict[str, object] = {}


async def baskets(market: Market, now: datetime) -> list[Basket]:
    """The registry is edited by hand a few times a week; an hour is fresh enough."""
    if market.id not in THEME_MARKETS:
        return []
    at = _baskets_cache.get("at")
    if not at or now - at > timedelta(hours=1):  # type: ignore[operator]
        _baskets_cache["data"] = await asyncio.to_thread(_load_baskets)
        _baskets_cache["at"] = now
    return (_baskets_cache.get("data") or {}).get(market.id, [])  # type: ignore[union-attr]


# ── detection + publishing ─────────────────────────────────────────────────

def _floor(lane: str) -> float:
    return {"index": settings.market_move_min_pct, "stock": settings.market_move_stock_min_pct,
            "theme": settings.market_move_theme_min_pct}[lane]


async def scan(instruments, today: date, now: datetime, floor_pct: float) -> dict:
    """Each instrument right now (full intraday + sigma), and which count as a big move.
    Instruments are fetched concurrently: four US indices one after another, each
    allowed its retries, was enough to outlive a 100s request."""
    async def one(inst: Instrument) -> tuple[dict, Optional[Move]]:
        try:
            day = await yahoo_chart.intraday(inst.symbol)
        except YahooChartError as e:
            return {"id": inst.id, "error": str(e)[:200]}, None
        if not is_today(day, today, now):
            return {"id": inst.id, "skipped": "not_trading_today"}, None
        try:
            sigma = await yahoo_chart.sigma(inst.symbol)
        except YahooChartError:
            sigma = None  # the floor alone still guards
        big = is_big(day, sigma, k=settings.market_move_sigma, floor_pct=floor_pct)
        move = Move(inst, day, sigma)
        row = {"id": inst.id, "pct": round(day.pct, 2), "sigma": sigma and round(sigma, 2),
               "z": move.z and round(move.z, 2), "big": big}
        return row, move if big else None

    results = await asyncio.gather(*(one(i) for i in instruments))
    return {"rows": [r for r, _ in results], "moves": [m for _, m in results if m]}


async def _prefilter(market: Market, pool: list[Instrument], today: date, now: datetime,
                     floor_pct: float) -> list[Instrument]:
    """Giants: one batched quote call decides who is worth a full chart fetch."""
    quoted = await yahoo_chart.quotes([i.symbol for i in pool])
    return [i for i in pool if i.symbol in quoted and quote_is_live(quoted[i.symbol], market, today, now)
            and abs(quoted[i.symbol].pct) >= floor_pct]


async def _draft(market: Market, lane: str, key: str, subject_id: str, move, text_fn, image_fn,
                 now: datetime, force: bool, base: dict) -> dict:
    cause = await find_cause(market, subject_of(market, move), now)
    if cause["tier"] == "none" and not force:
        return {**base, "draft": None, "skipped": "no_cause", "key": key, "cause": cause}
    draft = {"key": key, "lane": lane, "subject": subject_id, "text": text_fn(cause["clause"]),
             "image_url": image_fn(cause["clause"]), "reply": sources_reply(cause["sources"]) if cause["sources"] else None,
             "cause": cause}
    return {**base, "draft": draft}


async def build_theme_draft(market: Market, today: date, now: datetime, *,
                            exclude: frozenset[str] = frozenset(), force: bool = False) -> dict:
    pool = [b for b in await baskets(market, now) if b.exposure_id not in exclude]
    quoted = await yahoo_chart.quotes([m.symbol for b in pool for m in b.members])
    live = {s: q for s, q in quoted.items() if quote_is_live(q, market, today, now) or force}
    floor = 0.0 if force else _floor("theme")
    moves = [m for b in pool if (m := theme_move(b, live, floor_pct=floor))]
    if force and moves:
        moves = [max(moves, key=lambda m: abs(m.median))]
    base = {"market": market.id, "lane": "theme", "date": today.isoformat(),
            "rows": [{"id": m.basket.exposure_id, "name": m.basket.name, "median": round(m.median, 2),
                      "members": len(m.rows)} for m in moves]}
    if not moves:
        return {**base, "draft": None}
    lead = max(moves, key=lambda m: abs(m.median))
    eid = lead.basket.exposure_id
    return await _draft(market, "theme", lane_key(market, today, "theme", eid), eid, lead,
                        lambda clause: compose_theme_text(lead, clause),
                        lambda clause: theme_card_url(market, lead, clause),
                        now, force, base)


async def build_draft(market: Market, today: date, now: datetime, *, lane: str = "index",
                      exclude: frozenset[str] = frozenset(), force: bool = False) -> dict:
    """What ``lane`` would post for ``market`` now. ``exclude`` drops subject ids already
    posted or backing off today. ``force`` drafts the top candidate even below the
    threshold or without a reason — for the admin preview only."""
    if lane == "theme":
        return await build_theme_draft(market, today, now, exclude=exclude, force=force)
    pool = [i for i in (market.indices if lane == "index" else market.stocks) if i.id not in exclude]
    if lane == "stock" and not force:
        pool = await _prefilter(market, pool, today, now, _floor(lane))
    scanned = await scan(pool, today, now, _floor(lane))
    moves: list[Move] = scanned["moves"]
    if not moves and force:
        for inst in pool:
            try:
                moves = [Move(inst, await yahoo_chart.intraday(inst.symbol), None)]
                break
            except YahooChartError:
                continue
    base = {"market": market.id, "lane": lane, "date": today.isoformat(), "rows": scanned["rows"]}
    errors = [r["error"] for r in scanned["rows"] if "error" in r]
    if lane == "index" and errors and len(errors) == len(scanned["rows"]):
        # Every index failing at once is Yahoo (blocked, down, or a new payload shape),
        # not one quiet symbol.
        _problems.append(f"Yahoo 指數報價全部失敗（{market.id}）：{errors[0][:120]}")
    if not moves:
        return {**base, "draft": None}
    lead = headline_move(moves)
    return await _draft(market, lane, lane_key(market, today, lane, lead.index.id), lead.index.id, lead,
                        lambda clause: compose_text(lead, clause),
                        lambda clause: card_url(lead.index, lead.day.last_ts, clause),
                        now, force, base)


async def _publish(draft: dict) -> dict:
    service = ThreadsService()
    if not service.is_configured:
        return {"posted": False, "reason": "threads_not_configured"}
    if not social_ledger.claim(PLATFORM, draft["key"]):
        return {"posted": False, "reason": "already_posted"}
    try:
        media_id = await service.publish(draft["text"], image_url=draft["image_url"])
        reply_ids = []
        if draft.get("reply"):
            try:
                reply_ids.append(await service.publish_reply(draft["reply"], reply_to_id=media_id))
            except ThreadsError:
                logger.exception("market move: sources reply failed for %s", draft["key"])
    except ThreadsError as e:
        social_ledger.release(PLATFORM, draft["key"])
        return {"posted": False, "reason": f"publish_failed: {e}"}
    social_ledger.record(PLATFORM, draft["key"], media_id, "", reply_ids, fmt=FORMAT, subject=draft["subject"])
    return {"posted": True, "media_id": media_id}


def enabled_markets() -> list[Market]:
    ids = [p.strip().upper() for p in (settings.market_move_markets or "").split(",") if p.strip()]
    return [MARKETS[i] for i in ids if i in MARKETS]


def _blocked(key: str, now: datetime) -> bool:
    return social_ledger.already_posted(PLATFORM, key) or _retry_at.get(key, now) > now


def _posted_today(market: Market, today: date, lane: str) -> list[str]:
    prefix = lane_key(market, today, lane)
    return [r["episode_id"] for r in social_ledger.list_posted(PLATFORM, limit=200, days=2)
            if str(r.get("episode_id", "")).startswith(prefix)]


def _blocked_ids(market: Market, today: date, lane: str, ids: list[str], now: datetime) -> frozenset[str]:
    return frozenset(i for i in ids if _retry_at.get(lane_key(market, today, lane, i), now) > now)


def _lane_exclusions(market: Market, today: date, lane: str, now: datetime) -> Optional[frozenset[str]]:
    """Subject ids this lane must skip right now, or None when the lane has nothing to
    do (index posted / backing off, a daily budget spent, or the theme scan not due)."""
    if lane == "index":
        return None if _blocked(lane_key(market, today, "index"), now) else frozenset()
    cap = settings.market_move_max_stock_posts if lane == "stock" else settings.market_move_max_theme_posts
    posted = _posted_today(market, today, lane)
    if len(posted) >= cap:
        return None
    done = frozenset(k.rsplit(":", 1)[-1] for k in posted)
    if lane == "stock":
        if not market.stocks:
            return None
        return done | _blocked_ids(market, today, "stock", [s.id for s in market.stocks], now)
    if market.id not in THEME_MARKETS:
        return None
    last = _theme_scanned_at.get(market.id)
    if last and now - last < THEME_SCAN_EVERY:
        return None
    _theme_scanned_at[market.id] = now
    prefix = lane_key(market, today, "theme")
    return done | frozenset(k[len(prefix):] for k, t in _retry_at.items() if k.startswith(prefix) and t > now)


async def publish_due(now: Optional[datetime] = None) -> int:
    """One worker tick: for each enabled market inside its window, post the first lane
    (index, giants, theme) with a big move and a reason. Returns posts made."""
    now = now or datetime.now(timezone.utc)
    posted = 0
    _problems.clear()
    for market in enabled_markets():
        today = window_date(market, now)
        if not today:
            continue
        for lane in LANES:
            exclude = _lane_exclusions(market, today, lane, now)
            if exclude is None:
                continue
            try:
                res = await build_draft(market, today, now, lane=lane, exclude=exclude)
            except Exception as e:  # one market's failure must not stop the others
                logger.exception("market move scan failed for %s/%s", market.id, lane)
                _problems.append(f"{market.id}/{lane} 掃描例外：{type(e).__name__}: {str(e)[:120]}")
                continue
            if res.get("skipped") == "no_cause":
                # Big move, no story yet. Ask again later — not every minute, each ask is a model call.
                logger.info("market move %s: big move but no reason yet (%s)", res["key"], res["cause"].get("error"))
                _retry_at[res["key"]] = now + RETRY_AFTER
                continue
            if not res["draft"]:
                continue
            out = await _publish(res["draft"])
            logger.info("market move %s: %s (%s)", res["draft"]["key"], out, res["draft"]["text"])
            if out.get("posted"):
                posted += 1
                break  # one post per market per tick
            if str(out.get("reason", "")).startswith("publish_failed"):
                _problems.append(f"Threads 發文失敗：{out['reason'][:160]}")
                # Each retry re-asks the model; a broken image URL must not do that every minute.
                _retry_at[res["draft"]["key"]] = now + RETRY_AFTER
    return posted


def _notify_admins(title: str, body: str) -> int:
    """A bell notification for every registered admin — the channel the news drafts
    already use, so no new secret or service. Never raises."""
    from sqlalchemy import func

    from src.database.models import User
    from src.models.notification import NotificationType
    from src.services.notification_service import create_user_notification
    try:
        from src.database.postgres import session_scope
        with session_scope() as db:
            ids = [u.id for u in db.query(User.id).filter(func.lower(User.email).in_(
                [e.lower() for e in settings.admin_emails])).all()]
        for uid in ids:
            create_user_notification(uid, NotificationType.SYSTEM_ALERT, title, body, {"source": "market_moves"})
        if not ids:
            logger.error("market moves alert had no admin recipient: %s — %s", title, body)
        return len(ids)
    except Exception:  # noqa: BLE001 — an alert that cannot be sent is logged, not fatal
        logger.exception("market moves alert could not be sent: %s — %s", title, body)
        return 0


def track_health(problems: list[str], active: bool) -> Optional[str]:
    """Count consecutive failing ticks inside a detection window and tell admins once
    per outage (after ``ALERT_AFTER``), and once more when it recovers. Ticks outside
    every window prove nothing either way and leave the count alone. Returns the alert
    kind sent, if any."""
    if not active:
        return None
    if problems:
        _health["fails"] += 1
        _health["last"] = problems[0]
        if _health["fails"] >= ALERT_AFTER and not _health["alerted"]:
            _health["alerted"] = True
            _notify_admins("盤中速報連續失敗",
                           f"已連續 {_health['fails']} 分鐘失敗，期間不會發文。最近一次：{problems[0]}")
            return "failing"
        return None
    if _health["alerted"]:
        _notify_admins("盤中速報已恢復", f"連續 {_health['fails']} 分鐘的失敗已排除。最後的錯誤：{_health['last']}")
        _health.update(fails=0, alerted=False, last="")
        return "recovered"
    _health.update(fails=0, last="")
    return None


async def run_periodic(interval_seconds: float = 60.0) -> None:
    """Its own loop, not a step of the scheduled-posts worker: one tick can spend a
    minute on Yahoo retries and a model call, and the 11:30 slot must not wait on it."""
    logger.info("market moves worker started (markets=%s)", settings.market_move_markets or "off")
    while True:
        if settings.market_move_markets:
            now = datetime.now(timezone.utc)
            try:
                await publish_due(now)
            except Exception as e:
                logger.exception("market move cycle encountered an error")
                _problems.append(f"整輪例外：{type(e).__name__}: {str(e)[:120]}")
            active = any(window_date(m, now) for m in enabled_markets())
            try:
                await asyncio.to_thread(track_health, list(_problems), active)
            except Exception:
                logger.exception("market move health tracking failed")
        await asyncio.sleep(interval_seconds)


async def preview(market_id: str, *, lane: str = "index", force: bool = False,
                  now: Optional[datetime] = None) -> dict:
    """Admin dry run: one lane's scan and draft for one market, ignoring the time window."""
    market = MARKETS.get(market_id.upper())
    if not market or lane not in LANES:
        raise KeyError(market_id)
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(ZoneInfo(market.tz)).date()
    res = await build_draft(market, today, now, lane=lane, force=force)
    key = (res.get("draft") or {}).get("key") or res.get("key")
    if not key and lane == "index":
        key = lane_key(market, today, "index")
    return {**res, "in_window": window_date(market, now) is not None,
            "already_posted": bool(key) and social_ledger.already_posted(PLATFORM, key)}
