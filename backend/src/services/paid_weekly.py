"""The paid weekly — the 方格子 salon-member issue.

Shape agreed 2026-09-13 (Willy + the weekly session): the reader sees a SHORT summary for
free, the paywall sits right after it (placed by hand in the vocus wizard, at the ``---``
this module emits), and everything else is paid:

1. 摘要 — three lines: the week's topic and what the appendix verifies. Free.
2. 本週主題 — the cross-show piece written from ``weekly_brief`` (by a model, then
   fact-checked, never auto-published). Passed in as markdown; this module does not
   write prose.
3. 資料附錄 — charts, not bullet numbers: the topic tickers' OG cards, the 聲量水位
   movers (state only), and the calls made FOUR weeks ago now that their 20-trading-day
   return has resolved — pooled, against the index over the same window, because the
   raw hit rate of a bull call in an up-market is beta, not skill (2026-09-10 study).
   No per-show ranking: it read as a league table and invited "who to follow".

Everything numeric is a statistic about what third parties said and what happened after,
never a call (投顧法 — this publication measures, it does not recommend). Render is pure
over plain dicts so it can be tested without a database.
"""

from __future__ import annotations

import asyncio
import re
from bisect import bisect_left
from datetime import timedelta
from typing import Optional

from sqlalchemy.orm import Session

from src.config import settings
from src.database.models import ContentMention, StockDailyOHLC, StockTranslation, TickerPerformanceSnapshot
from src.database.postgres import get_session
from src.routers.weekly import build_week, week_bounds
from src.services.attention import attention_movers, scope_mentions
from src.services.podcast import PodcastService

# ponytail: only its cached release scope is read here, same as the routers.
_podcast_service = PodcastService()

HORIZON = "r20d"
HORIZON_SESSIONS = 20
TRACK_RECORD_LAG_WEEKS = 4  # 20 trading days ≈ 4 weeks; the calls scored are that old
TOP_CALLS = 3
CHART_TICKERS = 3
INDEX = {"TW": "0050", "US": "SPY"}
_BULL = ("BULLISH", "STRONG_BULLISH")
_BEAR = ("BEARISH", "STRONG_BEARISH")
PAYWALL = "---"  # the wizard's paywall goes here; nothing above it is paid

DISCLAIMER = (
    "本文為聽播客 TinBoker 對追蹤節目公開內容的統計整理與市場資料彙整，"
    "所有報酬皆為事後計算的歷史數據，聲量水位為節目提及量相對其自身過去一年的分位數。"
    "本文不構成任何投資建議，亦不推薦買賣任何有價證券；節目觀點屬各節目所有，"
    "過去績效不代表未來表現，投資前請自行評估風險。"
)


def lagged_week(week: str, weeks_back: int = TRACK_RECORD_LAG_WEEKS) -> str:
    monday, _ = week_bounds(week)
    y, w, _ = (monday - timedelta(weeks=weeks_back)).isocalendar()
    return f"{y}-W{w:02d}"


def _stance(label: str) -> str:
    return "bull" if label in _BULL else "bear" if label in _BEAR else "neu"


def _market(ticker: str) -> str:
    return "TW" if ticker[:1].isdigit() else "US"


# ── DB queries (sync; call via asyncio.to_thread) ──────────────────────────────

def _index_r20(db: Session, start: str) -> dict[str, tuple[list[str], list[float]]]:
    """Sorted (dates, closes) per index, from a few sessions before ``start``."""
    out = {}
    for mkt, tk in INDEX.items():
        rows = (db.query(StockDailyOHLC.date, StockDailyOHLC.close)
                .filter(StockDailyOHLC.ticker == tk, StockDailyOHLC.date >= start)
                .order_by(StockDailyOHLC.date).all())
        out[mkt] = ([d for d, _ in rows], [float(c) for _, c in rows])
    return out


def index_return(series: tuple[list[str], list[float]], day: str, sessions: int = HORIZON_SESSIONS) -> Optional[float]:
    """The index's % change from the first session on/after ``day`` over ``sessions``
    sessions — the same window the snapshot's r20d covers. Pure."""
    dates, closes = series
    i = bisect_left(dates, day)
    if i + sessions >= len(dates):
        return None
    return (closes[i + sessions] / closes[i] - 1) * 100


def query_track_record(db: Session, week: str, allowed: Optional[frozenset]) -> dict:
    """Every ticker mention released inside ``week`` whose r20d has resolved, each with
    the index's return over the same window.

    ``allowed`` is the release roster (PodcastService._allowed_podcast_names(), resolved
    by the async caller): the scored calls must be the same shows the rollup counts, or
    an English batch in the store gets scored in a zh-TW issue.
    """
    start, end = week_bounds(week)
    rows = (
        scope_mentions(db.query(ContentMention, TickerPerformanceSnapshot), allowed)
        .join(TickerPerformanceSnapshot, TickerPerformanceSnapshot.mention_id == ContentMention.id)
        .filter(
            ContentMention.mention_type == "ticker",
            TickerPerformanceSnapshot.mention_date >= start.isoformat(),
            TickerPerformanceSnapshot.mention_date <= end.isoformat(),
            getattr(TickerPerformanceSnapshot, HORIZON).isnot(None),
        )
        .all()
    )
    index = _index_r20(db, (start - timedelta(days=7)).isoformat()) if rows else {}
    calls = []
    for m, snap in rows:
        r = float(getattr(snap, HORIZON))
        label = str(m.sentiment_label or "").upper()
        idx = index_return(index[_market(m.ticker)], snap.mention_date) if index else None
        calls.append({
            "podcaster": m.podcaster or "?", "ticker": m.ticker, "date": snap.mention_date,
            "sentiment_label": label, "stance": _stance(label), "thesis": m.thesis or "",
            "r": r, "idx": idx, "excess": None if idx is None else r - idx,
        })
    return {"week": week, "start": start.isoformat(), "end": end.isoformat(), "calls": calls}


def query_names(db: Session, tickers: set[str]) -> dict[str, str]:
    """zh-TW display names from stock_translations for the tickers an issue cites.
    The rollup only names tickers that appear in a sector exposure; a paid issue
    that prints bare codes like 6173 reads unfinished."""
    if not tickers:
        return {}
    rows = (
        db.query(StockTranslation.ticker, StockTranslation.name_zh_tw)
        .filter(StockTranslation.ticker.in_(sorted(tickers)), StockTranslation.name_zh_tw.isnot(None))
        .all()
    )
    return {t: n for t, n in rows if n}


# ── render (pure) ──────────────────────────────────────────────────────────────

def _pct(x: Optional[float]) -> str:
    return "—" if x is None else f"{x:+.1f}%"


def _label_zh(label: str) -> str:
    return {"STRONG_BULLISH": "強烈看多", "BULLISH": "看多", "NEUTRAL": "中性",
            "BEARISH": "看空", "STRONG_BEARISH": "強烈看空"}.get(label, label or "—")


def _name(ticker: str, names: dict[str, str]) -> str:
    n = names.get(ticker)
    return f"{n}（{ticker}）" if n else ticker


def cited_tickers(rollup: dict, record: dict, movers: dict) -> set[str]:
    return (
        {t["ticker"] for t in rollup.get("tickers") or []}
        | {c["ticker"] for c in record.get("calls") or [] if c.get("ticker")}
        | {r["ticker"] for k in ("high", "low") for r in movers.get(k) or []}
    )


def article_title(article: Optional[str]) -> Optional[str]:
    for line in (article or "").splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return None


def article_tickers(article: Optional[str], limit: int = CHART_TICKERS) -> list[str]:
    """The stocks the piece links to (``/stock/{ticker}``), in order of first mention:
    the appendix charts what the article is about, not what the week talked about most."""
    seen: list[str] = []
    for t in re.findall(r"/stock/([A-Za-z0-9.\-]{1,20})", article or ""):
        if t.upper() not in seen:
            seen.append(t.upper())
    return seen[:limit]


def _strip_title(article: str) -> str:
    lines = article.strip().splitlines()
    return "\n".join(lines[1:]).strip() if lines and lines[0].startswith("# ") else article.strip()


def pooled(calls: list[dict]) -> Optional[dict]:
    """The bull calls as one population against the index over the same windows."""
    bulls = [c for c in calls if c["stance"] == "bull" and c.get("idx") is not None]
    if not bulls:
        return None
    n = len(bulls)
    return {
        "n": n, "up": sum(c["r"] > 0 for c in bulls) / n * 100,
        "mean_r": sum(c["r"] for c in bulls) / n, "mean_idx": sum(c["idx"] for c in bulls) / n,
        "beat": sum(c["excess"] > 0 for c in bulls) / n * 100,
    }


def render_markdown(rollup: dict, record: dict, movers: dict, names: Optional[dict[str, str]] = None,
                    article: Optional[str] = None) -> dict:
    """``{title, markdown, excerpt, stats}`` for one week. Pure."""
    week = rollup["week"]
    site = settings.site_url.rstrip("/")
    api = settings.public_api_url.rstrip("/")
    names = {**(names or {}),
             **{r["ticker"]: r["name"] for k in ("high", "low") for r in movers.get(k) or [] if r.get("name")},
             **{t["ticker"]: t.get("name") for t in rollup.get("tickers") or [] if t.get("name")}}
    topic = article_title(article)
    top = article_tickers(article) or [t["ticker"] for t in (rollup.get("tickers") or [])[:CHART_TICKERS]]
    calls = record["calls"]
    stat = pooled(calls)
    out: list[str] = []

    # 1. 摘要 — free
    out.append(f"## 本期摘要（{rollup['start']} → {rollup['end']}）")
    if topic:
        out.append(f"本週主題：{topic}" + ("" if topic[-1] in "？。！?" else "。"))
    most = [t["ticker"] for t in (rollup.get("tickers") or [])[:CHART_TICKERS]]
    if most:
        out.append("追蹤節目本週談最多的是 " + "、".join(_name(t, names) for t in most) + "。")
    out.append(f"資料附錄回頭驗證 {record['week']} 那週節目說過的話，20 個交易日後對照同期大盤。"
               if calls else f"資料附錄的驗證段（{record['week']} 的說法）本期資料未齊，下期補上。")
    out.append("")
    out.append(PAYWALL)
    out.append("")

    # 2. 本週主題 — the article, verbatim
    if article:
        out.append(f"## {topic or '本週主題'}")
        out.append("")
        out.append(_strip_title(article))
        out.append("")

    # 3. 資料附錄
    out.append("## 資料附錄")
    out.append("")
    if top:
        out.append("**主題個股的走勢與節目多空**（K 線、成交量、節目看多／看空分佈）")
        out.append("")
        for t in top:
            out.append(f"![{_name(t, names)}]({api}/api/og/stock/{t}.png)")
            out.append(f"[{_name(t, names)} 個股頁]({site}/stock/{t})")
            out.append("")
    if movers.get("high") or movers.get("low"):
        out.append(f"**聲量水位**（{movers.get('as_of')}；每檔相對自己過去一年的討論量分位數，只描述狀態）")
        out.append("")
        for k, label in (("high", "在自己一年高點（≥90）"), ("low", "在自己一年低點（≤10）")):
            rows = movers.get(k) or []
            if rows:
                out.append(f"- {label}：" + "、".join(f"{_name(r['ticker'], names)} {r['level']}" for r in rows))
        out.append("")
    out.append(f"**{record['week']}（{record['start']} → {record['end']}）的說法，20 個交易日後**")
    out.append("")
    if not stat:
        out.append("那一週的提及尚無足夠的收盤資料可以計算，本節下期補上。")
    else:
        out.append(f"那週有 {stat['n']} 筆看多的個股說法可驗證。單看漲跌，{stat['up']:.0f}% 之後是漲的；"
                   f"但同一段時間大盤（台股 0050／美股 SPY）平均走了 {_pct(stat['mean_idx'])}，"
                   f"這些個股平均 {_pct(stat['mean_r'])}，只有 {stat['beat']:.0f}% 跑贏同期大盤。"
                   f"看多說法的命中率有多少是選股、多少是市場本身，要看第二個數字。")
        out.append("")
        scored = [c for c in calls if c["stance"] == "bull" and c.get("excess") is not None]
        by = sorted(scored, key=lambda c: -c["excess"])
        out.append("**相對大盤最強的三筆**")
        out.extend(_call_line(c, names) for c in by[:TOP_CALLS])
        out.append("")
        out.append("**相對大盤最弱的三筆**")
        out.extend(_call_line(c, names) for c in reversed(by[-TOP_CALLS:]))
    out.append("")
    out.append("---")
    out.append(f"*{DISCLAIMER}*")

    title = f"聽播客週報 Pro {week}｜{topic}" if topic else f"聽播客週報 Pro {week}"
    excerpt = (f"{rollup['start']}～{rollup['end']}：" + (f"{topic}；" if topic else "")
               + f"附 {record['week']} 節目說法的 20 日驗證與聲量水位。")
    stats = {"episodes": rollup["episode_count"], "calls_scored": len(calls),
             "movers": len(movers.get("high") or []) + len(movers.get("low") or []), "article": bool(article)}
    return {"title": title, "markdown": "\n".join(out), "excerpt": excerpt, "stats": stats}


def _call_line(c: dict, names: dict[str, str]) -> str:
    thesis = c["thesis"].strip()
    if len(thesis) > 60:
        thesis = thesis[:60] + "…"
    return (f"- {c['date']} {c['podcaster']} 對 {_name(c['ticker'], names)} {_label_zh(c['sentiment_label'])}"
            f"，之後 20 日 {_pct(c['r'])}（同期大盤 {_pct(c['idx'])}）。「{thesis}」")


# ── entry ──────────────────────────────────────────────────────────────────────

def _query_all(week: str, rollup: dict, movers: dict, allowed: Optional[frozenset]) -> tuple[dict, dict]:
    for db in get_session():
        record = query_track_record(db, lagged_week(week), allowed)
        return record, query_names(db, cited_tickers(rollup, record, movers))
    return {"week": lagged_week(week), "start": "", "end": "", "calls": []}, {}


async def build_paid_weekly(week: str, article: Optional[str] = None) -> Optional[dict]:
    """None when the week has no scoped episodes (same rule as the public page)."""
    rollup = await build_week(week)
    if rollup is None:
        return None
    allowed = await _podcast_service._allowed_podcast_names()
    movers = await attention_movers(week, allowed=allowed)
    record, names = await asyncio.to_thread(_query_all, week, rollup, movers, allowed)
    return {"week": week, **render_markdown(rollup, record, movers, names, article)}
