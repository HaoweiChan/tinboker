"""The paid weekly — the 方格子 salon-member issue built from data the site already has.

Three sections nobody else can write, in the order a subscriber reads them:

1. 本週節目焦點 — the public weekly rollup (``routers/weekly.build_week``): which
   tickers the tracked shows discussed most, bull/neutral/bear counts vs last week.
2. 誰講對了 — the mentions made FOUR weeks ago, now that their 20-trading-day forward
   return has resolved: per-show directional hit rate and mean r20d, plus the best
   and worst individual calls with the thesis that was stated at the time.
3. 篩選器前十 × 節目提及 — the whole-market anomaly screener's top ten for the latest
   trading day, each cross-referenced with how many episodes mentioned it this week.
   That join is the product; the screener alone is a list.

The section that carries the value is 2, and it is deliberately backward-looking:
a statistic about what third parties said and what happened after, not a call.
Section 3 is factor output with the same framing. The disclaimer says so explicitly
(投顧法 — this publication does not recommend, it measures).

Render is a pure function over three plain dicts so it can be tested without a
database; the two DB queries are separate and run in a thread (sync SQLAlchemy inside
an async endpoint stalls the loop).
"""

from __future__ import annotations

import asyncio
from collections import Counter, defaultdict
from datetime import timedelta
from typing import Optional

from sqlalchemy.orm import Session

from src.database.models import ContentMention, ScreenerCandidate, StockTranslation, TickerPerformanceSnapshot
from src.database.postgres import get_session
from src.routers.weekly import build_week, week_bounds

HORIZON = "r20d"
TRACK_RECORD_LAG_WEEKS = 4  # 20 trading days ≈ 4 weeks; the calls scored are that old
SCREENER_TOP = 10
TOP_TICKERS = 10
TOP_CALLS = 3
_BULL = ("BULLISH", "STRONG_BULLISH")
_BEAR = ("BEARISH", "STRONG_BEARISH")

DISCLAIMER = (
    "本文為聽播客 TinBoker 對追蹤節目公開內容的統計整理與市場資料彙整，"
    "所有「命中」「報酬」皆為事後計算的歷史數據，篩選器為量化因子排序結果。"
    "本文不構成任何投資建議，亦不推薦買賣任何有價證券；節目觀點屬各節目所有，"
    "過去績效不代表未來表現，投資前請自行評估風險。"
)


def lagged_week(week: str, weeks_back: int = TRACK_RECORD_LAG_WEEKS) -> str:
    monday, _ = week_bounds(week)
    y, w, _ = (monday - timedelta(weeks=weeks_back)).isocalendar()
    return f"{y}-W{w:02d}"


# ── DB queries (sync; call via asyncio.to_thread) ──────────────────────────────

def _hit(label: str, r: float) -> Optional[bool]:
    if label in _BULL:
        return r > 0
    if label in _BEAR:
        return r < 0
    return None


def query_track_record(db: Session, week: str) -> dict:
    """Every ticker mention released inside ``week`` whose r20d has resolved."""
    start, end = week_bounds(week)
    rows = (
        db.query(ContentMention, TickerPerformanceSnapshot)
        .join(TickerPerformanceSnapshot, TickerPerformanceSnapshot.mention_id == ContentMention.id)
        .filter(
            ContentMention.mention_type == "ticker",
            TickerPerformanceSnapshot.mention_date >= start.isoformat(),
            TickerPerformanceSnapshot.mention_date <= end.isoformat(),
            getattr(TickerPerformanceSnapshot, HORIZON).isnot(None),
        )
        .all()
    )
    calls = []
    for m, snap in rows:
        r = float(getattr(snap, HORIZON))
        label = str(m.sentiment_label or "").upper()
        calls.append({
            "podcaster": m.podcaster or "?", "ticker": m.ticker, "date": snap.mention_date,
            "sentiment_label": label, "thesis": m.thesis or "", "r": r, "hit": _hit(label, r),
        })
    return {"week": week, "start": start.isoformat(), "end": end.isoformat(), "calls": calls}


def query_screener(db: Session, top: int = SCREENER_TOP) -> dict:
    latest = db.query(ScreenerCandidate.date).order_by(ScreenerCandidate.date.desc()).first()
    if not latest:
        return {"date": None, "candidates": []}
    rows = (
        db.query(ScreenerCandidate)
        .filter(ScreenerCandidate.date == latest[0])
        .order_by(ScreenerCandidate.rank.asc())
        .limit(top)
        .all()
    )
    return {
        "date": latest[0],
        "candidates": [{
            "rank": r.rank, "ticker": r.ticker, "final_score": r.final_score,
            "factors": r.factors or {}, "is_60d_high": bool(r.is_60d_high), "crowded": bool(r.crowded),
        } for r in rows],
    }


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


def _episode_mentions(rollup: dict) -> Counter:
    c: Counter = Counter()
    for ep in rollup.get("episodes") or []:
        for tk in ep.get("related_tickers") or []:
            c[str(tk)] += 1
    return c


def cited_tickers(rollup: dict, record: dict, screener: dict) -> set[str]:
    return (
        {t["ticker"] for t in rollup.get("tickers") or []}
        | {c["ticker"] for c in record.get("calls") or [] if c.get("ticker")}
        | {c["ticker"] for c in screener.get("candidates") or []}
    )


def render_markdown(rollup: dict, record: dict, screener: dict, names: Optional[dict[str, str]] = None) -> dict:
    """``{title, markdown, excerpt, stats}`` for one week. Pure."""
    week = rollup["week"]
    names = {**(names or {}),
             **{t["ticker"]: t.get("name") for t in rollup.get("tickers") or [] if t.get("name")}}
    out: list[str] = []

    # 1. focus
    out.append(f"## 本週節目焦點（{rollup['start']} → {rollup['end']}）")
    out.append(f"追蹤節目本週共 {rollup['episode_count']} 集、{len(rollup.get('podcasts') or [])} 個節目。"
               f"下表是被最多集數討論的個股，以及各集對它的多空立場（括號為上週）。")
    out.append("")
    out.append("| 個股 | 集數 | 看多 | 中性 | 看空 |")
    out.append("|---|---:|---:|---:|---:|")
    for t in (rollup.get("tickers") or [])[:TOP_TICKERS]:
        out.append(f"| {_name(t['ticker'], names)} | {t['episodes']} | {t['bull']}（{t['prev_bull']}）"
                   f" | {t['neu']}（{t['prev_neu']}） | {t['bear']}（{t['prev_bear']}） |")
    out.append("")

    # 2. who was right
    calls = record["calls"]
    out.append(f"## 誰講對了 — {record['week']}（{record['start']} → {record['end']}）的說法，20 個交易日後")
    if not calls:
        out.append("那一週的提及尚無足夠的收盤資料可以計算，本節下期補上。")
    else:
        per: dict[str, dict] = defaultdict(lambda: {"n": 0, "scored": 0, "hits": 0, "sum": 0.0})
        for c in calls:
            row = per[c["podcaster"]]
            row["n"] += 1
            row["sum"] += c["r"]
            if c["hit"] is not None:
                row["scored"] += 1
                row["hits"] += int(c["hit"])
        out.append(f"共 {len(calls)} 筆有方向或中性立場的個股提及已可驗證。「命中」＝立場方向與其後 20 個交易日"
                   f"報酬同號，中性立場不計入命中、但計入平均。")
        out.append("")
        out.append("| 節目 | 提及 | 命中 | 平均 20 日報酬 |")
        out.append("|---|---:|---:|---:|")
        for show, row in sorted(per.items(), key=lambda kv: (-kv[1]["hits"] / kv[1]["scored"] if kv[1]["scored"] else 0, -kv[1]["n"])):
            hit = f"{row['hits']}/{row['scored']}" if row["scored"] else "—"
            out.append(f"| {show} | {row['n']} | {hit} | {_pct(row['sum'] / row['n'])} |")
        out.append("")
        directional = [c for c in calls if c["hit"] is not None]
        if directional:
            best = sorted(directional, key=lambda c: -(c["r"] if c["sentiment_label"] in _BULL else -c["r"]))
            out.append("**講得最準的三筆**")
            for c in best[:TOP_CALLS]:
                out.append(_call_line(c, names))
            out.append("")
            out.append("**偏差最大的三筆**")
            for c in reversed(best[-TOP_CALLS:]):
                out.append(_call_line(c, names))
            out.append("")

    # 3. screener × mentions
    ep_mentions = _episode_mentions(rollup)
    out.append(f"## 篩選器前十 × 節目提及（{screener.get('date') or '—'}）")
    if not screener.get("candidates"):
        out.append("本期無篩選器資料。")
    else:
        out.append("全市場動能／籌碼異常篩選的前十名，最後一欄是本週有幾集節目提到它。"
                   "有分數、沒人講的，和大家都在講、分數也高的，是兩種不同的東西。")
        out.append("")
        out.append("| # | 個股 | 分數 | 5 日 | 量能倍數 | 60 日新高 | 擁擠 | 本週提及集數 |")
        out.append("|--:|---|---:|---:|---:|:-:|:-:|---:|")
        for c in screener["candidates"]:
            f = c["factors"]
            ret5 = f.get("ret_5d")
            vol = f.get("vol_mult")
            out.append(f"| {c['rank']} | {_name(c['ticker'], names)} | {c['final_score']:.2f}"
                       f" | {_pct(None if ret5 is None else ret5 * 100)}"  # screener stores a fraction
                       f" | {'—' if vol is None else f'{vol:.1f}x'}"
                       f" | {'✓' if c['is_60d_high'] else ''} | {'✓' if c['crowded'] else ''}"
                       f" | {ep_mentions.get(c['ticker'], 0)} |")
        out.append("")

    out.append("---")
    out.append(f"*{DISCLAIMER}*")

    title = f"聽播客週報 Pro {week}｜誰講對了、篩選器前十"
    excerpt = (f"{rollup['start']}～{rollup['end']}：{rollup['episode_count']} 集節目的焦點個股、"
               f"四週前說法的 20 日驗證、以及篩選器前十與節目提及的交叉表。")
    stats = {"episodes": rollup["episode_count"], "calls_scored": len(calls),
             "screener_rows": len(screener.get("candidates") or [])}
    return {"title": title, "markdown": "\n".join(out), "excerpt": excerpt, "stats": stats}


def _call_line(c: dict, names: dict[str, str]) -> str:
    thesis = c["thesis"].strip()
    if len(thesis) > 60:
        thesis = thesis[:60] + "…"
    return (f"- {c['date']} {c['podcaster']} 對 {_name(c['ticker'], names)} {_label_zh(c['sentiment_label'])}"
            f"，之後 20 日 {_pct(c['r'])}。「{thesis}」")


# ── entry ──────────────────────────────────────────────────────────────────────

def _query_all(week: str, rollup: dict) -> tuple[dict, dict, dict]:
    for db in get_session():
        record, screener = query_track_record(db, lagged_week(week)), query_screener(db)
        return record, screener, query_names(db, cited_tickers(rollup, record, screener))
    return {"week": lagged_week(week), "start": "", "end": "", "calls": []}, {"date": None, "candidates": []}, {}


async def build_paid_weekly(week: str) -> Optional[dict]:
    """None when the week has no scoped episodes (same rule as the public page)."""
    rollup = await build_week(week)
    if rollup is None:
        return None
    record, screener, names = await asyncio.to_thread(_query_all, week, rollup)
    return {"week": week, **render_markdown(rollup, record, screener, names)}
