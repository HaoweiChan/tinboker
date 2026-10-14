"""Intraday market-move flash posts: when an index has a big morning, say so on Threads
within the first hour, with its intraday card and at most one line on why.

Speed over completeness, on purpose. The close-of-day write-up (full news, highlighted
sources) is a separate, later post; this one exists because by the close the reaction is
over. So the rules are about not being wrong fast:

  * "big" is relative to the index's own volatility (``yahoo_chart.daily_sigma``) with a
    floor in percent — a 2% SOX day is a Tuesday, a 2% Dow day is news;
  * the move must still be holding (at least half of its extreme so far), so an opening
    gap that has already filled is not posted as a crash;
  * the reason is one clause, and its wording is decided here, not by the model: two
    or more publishers attributing the move to the same driver → 外電普遍歸因於…;
    one → 市場推測與…有關; none → no reason at all. The model only extracts.

One post per market per local day (ledger key ``market_move:intraday:{market}:{date}``).
Off unless ``MARKET_MOVE_MARKETS`` is set — same one-environment rule as the posting slots.
"""
from __future__ import annotations

import json
import logging
import re
import urllib.parse
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

import httpx

from src.config import settings
from src.services import social_ledger, yahoo_chart
from src.services.intraday_card import signed
from src.services.threads_service import ThreadsError, ThreadsService
from src.services.yahoo_chart import Intraday, YahooChartError

logger = logging.getLogger(__name__)

PLATFORM = "threads"
FORMAT = "market_move_intraday"
HOLD_RATIO = 0.5             # keep at least half of the day's extreme so far
NEWS_MAX_AGE_HOURS = 20      # overnight + pre-market; older is yesterday's story
CAUSE_MAX_CHARS = 28
STALE_SECONDS = 30 * 60      # Yahoo delays some index feeds; older than this is not "now"
RETRY_AFTER = timedelta(minutes=10)
_retry_at: dict[str, datetime] = {}   # key -> earliest retry after a failed publish


@dataclass(frozen=True)
class Index:
    symbol: str              # Yahoo symbol, e.g. ^N225
    name: str

    @property
    def id(self) -> str:     # path-safe, for the card URL
        return self.symbol.lstrip("^")


@dataclass(frozen=True)
class Market:
    id: str
    name: str
    tz: str
    open_hm: tuple[int, int]
    indices: tuple[Index, ...]
    news_query: str


MARKETS: dict[str, Market] = {m.id: m for m in (
    Market("TW", "台股", "Asia/Taipei", (9, 0),
           (Index("^TWII", "加權指數"), Index("^TWOII", "櫃買指數")), "Taiwan stocks TAIEX"),
    Market("US", "美股", "America/New_York", (9, 30),
           (Index("^GSPC", "S&P 500"), Index("^IXIC", "那斯達克"), Index("^SOX", "費城半導體"),
            Index("^DJI", "道瓊")), "stock market today"),
    Market("JP", "日股", "Asia/Tokyo", (9, 0), (Index("^N225", "日經225"),), "Nikkei"),
    Market("KR", "韓股", "Asia/Seoul", (9, 0), (Index("^KS11", "KOSPI"), Index("^KQ11", "KOSDAQ")), "KOSPI"),
)}
INDEX_BY_ID: dict[str, tuple[Market, Index]] = {i.id: (m, i) for m in MARKETS.values() for i in m.indices}


@dataclass
class Move:
    index: Index
    day: Intraday
    sigma: Optional[float]

    @property
    def z(self) -> Optional[float]:
        return abs(self.day.pct) / self.sigma if self.sigma else None


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


def is_big(day: Intraday, sigma: Optional[float], *, k: float, floor_pct: float) -> bool:
    pct = day.pct
    if abs(pct) < floor_pct or (sigma and abs(pct) < k * sigma):
        return False
    direction = 1 if pct > 0 else -1
    extreme = max((v - day.prev_close) * direction for _, v in day.points)
    return day.change * direction >= HOLD_RATIO * extreme


def headline_move(moves: list[Move]) -> Move:
    """The index the post leads with: the most unusual one, not the biggest percent."""
    return max(moves, key=lambda m: (m.z or 0, abs(m.day.pct)))


def verb(pct: float) -> str:
    if pct >= 0:
        return "急漲" if pct >= 3 else "大漲"
    return "重挫" if pct <= -3 else "大跌"


def cause_text(cause: str, publishers: set[str]) -> tuple[str, str]:
    """``(tier, sentence)``. The hedge is chosen from how many publishers back the
    cause — never from the model's own confidence."""
    cause = cause.strip().rstrip("。.，,")
    if not cause or len(cause) > CAUSE_MAX_CHARS or "\n" in cause:
        return "none", ""
    if len(publishers) >= 2:
        return "consensus", f"外電普遍歸因於{cause}。"
    if len(publishers) == 1:
        return "reported", f"市場推測與{cause}有關。"
    return "none", ""


def compose_text(market: Market, lead: Move, peers: list[tuple[str, float]], cause_sentence: str) -> str:
    d = lead.day
    stamp = datetime.fromtimestamp(d.last_ts, ZoneInfo(d.tz))
    lines = [f"【盤中速報】{lead.index.name} {verb(d.pct)} {abs(d.pct):.2f}%",
             f"{d.last:,.2f}（{signed(d.change)}）· {market.name} {stamp:%H:%M}"]
    if peers:
        lines.append("同市場：" + "｜".join(f"{n} {signed(p, pct=True)}" for n, p in peers))
    if cause_sentence:
        lines.append(cause_sentence)
    return "\n".join(lines)


def card_url(index: Index, until: int) -> str:
    q = urllib.parse.urlencode({"until": until})
    return f"{settings.public_api_url.rstrip('/')}/api/og/market/{index.id}.png?{q}"


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

CAUSE_SYSTEM = """你負責從新聞標題中，找出某個股價指數今天盤中大幅波動的原因。

只能根據提供的標題判斷，不可使用標題以外的知識或推測。
回傳 JSON：{"cause": "...", "support": [標題編號...]}
- cause：繁體中文名詞短語，20 字以內，描述驅動因素本身，例如「美國公債殖利率走升」「輝達財報優於預期」。不要寫漲跌幅、不要加句號、不要寫「可能」「市場推測」等語氣詞。
- support：明確把「這個市場今天的漲跌」歸因於這個因素的標題編號。只是同時出現、或在講別的市場、別的日子的標題不算。
- 沒有任何標題明確解釋這次波動時，回傳 {"cause": "", "support": []}。寧可留白，不要猜。"""


async def _extract_cause(market: Market, lead: Move, headlines: list[dict]) -> dict:
    listing = "\n".join(f"[{i}] {h['publisher'] or '?'}：{h['title']}" for i, h in enumerate(headlines))
    user = (f"市場：{market.name}；指數：{lead.index.name}（{lead.index.symbol}）"
            f"盤中{'上漲' if lead.day.pct >= 0 else '下跌'} {abs(lead.day.pct):.2f}%。\n\n標題：\n{listing}")
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


async def find_cause(market: Market, lead: Move, now: datetime) -> dict:
    """``{tier, sentence, cause, sources}``. Never raises: a failed lookup is a post
    with no reason, which is the honest fallback anyway."""
    empty = {"tier": "none", "sentence": "", "cause": "", "sources": []}
    if not settings.openrouter_api_key:
        return {**empty, "error": "no_openrouter_key"}
    try:
        items = await yahoo_chart.news(market.news_query)
        items += await yahoo_chart.news(lead.index.symbol)
    except YahooChartError as e:
        return {**empty, "error": str(e)[:200]}
    headlines = fresh_headlines(items, now)
    if not headlines:
        return {**empty, "error": "no_fresh_headlines"}
    try:
        out = await _extract_cause(market, lead, headlines)
    except Exception as e:  # noqa: BLE001 — timeout, 5xx, malformed JSON: post without a reason
        logger.warning("market move cause extraction failed (%s): %s", market.id, e)
        return {**empty, "error": f"llm: {str(e)[:200]}"}
    ids = [i for i in out.get("support") or [] if isinstance(i, int) and 0 <= i < len(headlines)]
    sources = [headlines[i] for i in dict.fromkeys(ids)]
    publishers = {s["publisher"].lower() for s in sources if s["publisher"]}
    tier, sentence = cause_text(str(out.get("cause") or ""), publishers)
    return {"tier": tier, "sentence": sentence, "cause": str(out.get("cause") or "").strip(),
            "sources": sources if tier != "none" else []}


def sources_reply(sources: list[dict]) -> str:
    lines = ["消息來源："]
    for s in sources[:2]:
        lines.append(f"・{s['publisher'] or '新聞'}：{s['title']}\n{s['url']}")
    return "\n".join(lines)


# ── detection + publishing ─────────────────────────────────────────────────

async def scan(market: Market, today: date, now: datetime) -> dict:
    """Every index of ``market`` right now, and which of them count as a big move."""
    rows, moves = [], []
    for idx in market.indices:
        try:
            day = await yahoo_chart.intraday(idx.symbol)
        except YahooChartError as e:
            rows.append({"index": idx.id, "error": str(e)[:200]})
            continue
        if not is_today(day, today, now):
            rows.append({"index": idx.id, "skipped": "not_trading_today"})
            continue
        try:
            sigma = await yahoo_chart.sigma(idx.symbol)
        except YahooChartError:
            sigma = None  # the floor alone still guards
        big = is_big(day, sigma, k=settings.market_move_sigma, floor_pct=settings.market_move_min_pct)
        move = Move(idx, day, sigma)
        rows.append({"index": idx.id, "pct": round(day.pct, 2), "sigma": sigma and round(sigma, 2),
                     "z": move.z and round(move.z, 2), "big": big})
        if big:
            moves.append(move)
    return {"rows": rows, "moves": moves}


async def build_draft(market: Market, today: date, now: datetime, *, force: bool = False) -> dict:
    """What would be posted for ``market`` now. ``force`` drafts the headline index even
    below the threshold — for the admin preview only."""
    scanned = await scan(market, today, now)
    moves: list[Move] = scanned["moves"]
    if not moves and force:
        for idx in market.indices:
            try:
                day = await yahoo_chart.intraday(idx.symbol)
            except YahooChartError:
                continue
            moves = [Move(idx, day, None)]
            break
    base = {"market": market.id, "date": today.isoformat(), "indices": scanned["rows"]}
    if not moves:
        return {**base, "draft": None}
    lead = headline_move(moves)
    by_id = {r["index"]: r for r in scanned["rows"]}
    peers = [(i.name, by_id[i.id]["pct"]) for i in market.indices
             if i != lead.index and "pct" in by_id.get(i.id, {})]
    cause = await find_cause(market, lead, now)
    draft = {
        "key": f"market_move:intraday:{market.id}:{today.isoformat()}",
        "subject": lead.index.id,
        "text": compose_text(market, lead, peers, cause["sentence"]),
        "image_url": card_url(lead.index, lead.day.last_ts),
        "reply": sources_reply(cause["sources"]) if cause["sources"] else None,
        "cause": cause,
    }
    return {**base, "draft": draft}


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


async def publish_due(now: Optional[datetime] = None) -> int:
    """One worker tick: for each enabled market inside its window and not yet posted
    today, post if an index is having a big, holding move. Returns posts made."""
    now = now or datetime.now(timezone.utc)
    posted = 0
    for market in enabled_markets():
        today = window_date(market, now)
        if not today:
            continue
        key = f"market_move:intraday:{market.id}:{today.isoformat()}"
        if social_ledger.already_posted(PLATFORM, key) or _retry_at.get(key, now) > now:
            continue
        try:
            res = await build_draft(market, today, now)
        except Exception:  # one market's failure must not stop the others
            logger.exception("market move scan failed for %s", market.id)
            continue
        if not res["draft"]:
            continue
        out = await _publish(res["draft"])
        logger.info("market move %s: %s (%s)", key, out, res["draft"]["text"].splitlines()[0])
        if out.get("posted"):
            posted += 1
        elif str(out.get("reason", "")).startswith("publish_failed"):
            # Each retry re-asks the model; a broken image URL must not do that every minute.
            _retry_at[key] = now + RETRY_AFTER
    return posted


async def preview(market_id: str, *, force: bool = False, now: Optional[datetime] = None) -> dict:
    """Admin dry run: the scan and the draft for one market, ignoring the time window."""
    market = MARKETS.get(market_id.upper())
    if not market:
        raise KeyError(market_id)
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(ZoneInfo(market.tz)).date()
    res = await build_draft(market, today, now, force=force)
    return {**res, "in_window": window_date(market, now) is not None,
            "already_posted": social_ledger.already_posted(
                PLATFORM, f"market_move:intraday:{market.id}:{today.isoformat()}")}
