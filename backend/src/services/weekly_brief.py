"""週報素材 — the structured fact base a paid weekly issue is written from.

The paid issue's core is a cross-show piece: which topic the most shows talked about this
week, where they agree, where they differ and whether the difference comes from time
horizon or from an assumption, what nobody mentioned, which episode to hear in full.
The prose is written from this brief (by a model, then fact-checked, then published by
hand — never auto-published); the brief itself is data only and must contain nothing a
show did not say. Every row carries the show, the episode and the release date so each
sentence in the article can be traced back.

Reads the same things the public weekly and 每日一集 read: release-scoped episodes and the
ticker insights the pipeline writes. Selection and rendering are pure so they can be
tested without a database.
"""

from __future__ import annotations

import asyncio
from collections import Counter, defaultdict
from datetime import datetime, time, timedelta
from typing import Optional

from src.config import settings
from src.database.postgres import get_session
from src.routers.weekly import _insights_for, _released_ms, _sentiment, podcast_service, week_bounds
from src.services.attention import attention_movers
from src.services.daily_pick import TAIPEI  # noqa: F401 — same day boundary as the nightly pick
from src.services.paid_weekly import query_names
from src.services.syndication_markdown import released_date

MIN_SHOWS = 3          # a topic is worth a cross-show piece only when ≥ this many shows raised it
MAX_TOPICS = 4
STANCE_ZH = {"bull": "看多", "neu": "中性", "bear": "看空"}


def _stance(label: str) -> str:
    return _sentiment(label)


def select_topics(insights: list[dict], episodes: dict[str, dict], names: dict[str, str],
                  min_shows: int = MIN_SHOWS, max_topics: int = MAX_TOPICS) -> list[dict]:
    """Tickers raised by ≥ min_shows distinct shows, best first, each with every
    observation and a divergence read-out. Pure."""
    by_ticker: dict[str, list[dict]] = defaultdict(list)
    for i in insights:
        if i.get("ticker") and i.get("episode_id") in episodes:
            by_ticker[i["ticker"]].append(i)
    topics = []
    for ticker, rows in by_ticker.items():
        shows = {r.get("podcaster") for r in rows if r.get("podcaster")}
        if len(shows) < min_shows:
            continue
        obs = []
        for r in sorted(rows, key=lambda r: r.get("podcast_launch_time") or ""):
            ep = episodes[r["episode_id"]]
            obs.append({
                "show": r.get("podcaster"), "date": (r.get("podcast_launch_time") or "")[:10],
                "episode_id": r["episode_id"], "episode_title": ep.get("episode_title") or "",
                "stance": STANCE_ZH[_stance(r.get("sentiment_label"))], "horizon": r.get("time_horizon") or "",
                "thesis": r.get("bluf_thesis") or "",
                "reasons": [{"category": x.get("category"), "title": x.get("title"), "description": x.get("description")}
                            for x in (r.get("reasons") or [])],
                "risks": [{"title": x.get("title"), "description": x.get("description")} for x in (r.get("risks") or [])],
            })
        stances = Counter(o["stance"] for o in obs)
        horizons = Counter(o["horizon"] for o in obs if o["horizon"])
        categories = Counter(x["category"] for o in obs for x in o["reasons"] if x.get("category"))
        topics.append({
            "ticker": ticker, "name": names.get(ticker), "shows": len(shows), "observations": len(obs),
            "stances": dict(stances), "horizons": dict(horizons), "reason_mix": dict(categories),
            # A read-out, not a verdict: the article explains WHERE a difference comes from.
            "divergence": {"stance": len(stances) > 1, "horizon": len(horizons) > 1,
                           "risks_raised_by": sorted({o["show"] for o in obs if o["risks"]})},
            "rows": obs,
        })
    topics.sort(key=lambda t: (t["shows"], t["observations"], t["ticker"]), reverse=True)
    return topics[:max_topics]


def render_brief_markdown(brief: dict) -> str:
    """The brief as the markdown a writer (or model) works from. Pure. Facts only;
    the rules block is what keeps the prose on the right side of 投顧法."""
    site = settings.site_url.rstrip("/")
    out = [f"# 週報素材 {brief['week']}（{brief['start']} → {brief['end']}）", "",
           "## 規則",
           "- 只能使用下面列出的事實；每一個主張都要能對到某個節目某一集。",
           "- 分歧只解釋「來自時間尺度還是假設」，不判哪一邊比較對，不寫「值得布局」「建議關注」。",
           "- 沒有節目講到的東西，明確寫「這週沒有節目談到」；不要為了對照製造分歧。",
           "- 看多／看空／中性是 TinBoker 判讀的標籤；主持人沒明講就是中性。",
           "- 不報收錄規模（幾個節目、幾則觀點）；節目名和日期只在指出誰、何時說的時候出現。",
           ""]
    for t in brief["topics"]:
        head = f"{t['name']}（{t['ticker']}）" if t.get("name") else t["ticker"]
        out.append(f"## 題目：{head}")
        out.append(f"節目數 {t['shows']}・觀點 {t['observations']}・立場 {t['stances']}・時間尺度 {t['horizons']}・理由類別 {t['reason_mix']}")
        d = t["divergence"]
        out.append(f"分歧：立場{'有' if d['stance'] else '無'}分歧，時間尺度{'有' if d['horizon'] else '無'}分歧；有講風險的節目：{'、'.join(d['risks_raised_by']) or '無'}")
        out.append(f"個股頁：{site}/stock/{t['ticker']}")
        out.append("")
        for o in t["rows"]:
            out.append(f"### {o['show']}・{o['date']}・{o['stance']}・{o['horizon'] or '尺度未明'}")
            out.append(f"集數：{o['episode_title']}（{site}/episode/{o['episode_id']}）")
            out.append(f"說法：{o['thesis']}")
            for r in o["reasons"]:
                out.append(f"- 理由［{r.get('category') or '?'}］{r.get('title') or ''} — {r.get('description') or ''}")
            for r in o["risks"]:
                out.append(f"- 風險 {r.get('title') or ''} — {r.get('description') or ''}")
            out.append("")
    m = brief.get("movers") or {}
    if m:
        out.append(f"## 聲量水位（as of {m.get('as_of')}；只寫狀態，不寫報酬）")
        for k, label in (("high", "在自己一年高點"), ("low", "在自己一年低點")):
            rows = m.get(k) or []
            out.append(f"{label}：" + ("、".join(f"{r.get('name') or r['ticker']}（{r['ticker']}，{r['level']}）" for r in rows) or "無"))
        out.append("")
    out.append("## 這週的集數")
    for e in brief["episodes"]:
        out.append(f"- {e['podcast_name']}・{e['date']}・{e['episode_title']}（{site}/episode/{e['id']}）")
    return "\n".join(out)


async def build_weekly_brief(week: str) -> Optional[dict]:
    """The brief for one ISO week, or None when no scoped episode falls in it."""
    start, end = week_bounds(week)
    lo = int(datetime.combine(start, time.min, tzinfo=TAIPEI).timestamp() * 1000)
    hi = int(datetime.combine(end + timedelta(days=1), time.min, tzinfo=TAIPEI).timestamp() * 1000)
    episodes = {}
    for ep in await podcast_service.get_recent_episodes(limit=3000, enrich_content=False):
        ms = _released_ms(ep)
        if ms is not None and lo <= ms < hi:
            episodes[ep.id] = {"id": ep.id, "podcast_name": ep.podcast_name, "episode_title": ep.episode_title or "",
                               "date": released_date(ms).isoformat()}
    if not episodes:
        return None
    podcasters = sorted({e["podcast_name"] for e in episodes.values() if e["podcast_name"]})
    insights = await _insights_for(podcasters, start - timedelta(days=1), end + timedelta(days=1))
    tickers = {i["ticker"] for i in insights if i.get("ticker")}

    def _names() -> dict[str, str]:
        for db in get_session():
            return query_names(db, tickers)
        return {}

    names = await asyncio.to_thread(_names) if tickers else {}
    allowed = await podcast_service._allowed_podcast_names()
    movers = await attention_movers(week, allowed=allowed)
    topics = select_topics(insights, episodes, names)
    brief = {"week": week, "start": start.isoformat(), "end": end.isoformat(),
             "episode_count": len(episodes), "topics": topics, "movers": movers,
             "episodes": sorted(episodes.values(), key=lambda e: (e["date"], e["podcast_name"]))}
    brief["markdown"] = render_brief_markdown(brief)
    return brief
