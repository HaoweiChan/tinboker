"""每日精選 — one 方格子 article a day: which stocks today's episodes talked about.

Replaces per-episode summary syndication. Four weeks of pushing every summary to vocus
produced 870 articles at a median of 7 pageviews each, no comments, and a feed that
buried anything else the account published. What the 2026-09-10 sentiment study found
to carry value is not the summary but the per-ticker observation with its reason and
its source — so that is what goes out, once a day, ranked by how many shows raised the
name.

Reads only what the public weekly already reads (release-scoped episodes and the ticker
insights the pipeline writes); ``render_digest`` is pure so the markdown is testable
without a database. Publishing goes through ``routers.social._syndicate_once`` under the
key ``digest:{YYYY-MM-DD}``, so three environments cannot mint three copies.
"""

from __future__ import annotations

import asyncio
import logging
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from src.config import settings
from src.database.postgres import get_session
from src.routers.weekly import _insights_for, _released_ms, _sentiment, podcast_service, week_of_ms
from src.services.paid_weekly import query_names

logger = logging.getLogger(__name__)

TAIPEI = ZoneInfo("Asia/Taipei")
TOP_TICKERS = 12
THESIS_MAX_CHARS = 80
# Publish after the evening ingest (systemd timer 20:10 Asia/Taipei) has landed.
PUBLISH_AT = time(20, 40)
VOCUS_TAGS = ["台股", "Podcast", "每日精選", "聽播客"]

DISCLAIMER = (
    "節目觀點由聽播客 TinBoker 自動整理，為第三方公開言論的統計，"
    "不構成投資建議，亦不推薦買賣任何有價證券；投資前請自行評估風險。"
)


def day_bounds_ms(day: date) -> tuple[int, int]:
    """[start, end) of one Asia/Taipei calendar day in Unix milliseconds."""
    start = datetime.combine(day, time.min, tzinfo=TAIPEI)
    return int(start.timestamp() * 1000), int((start + timedelta(days=1)).timestamp() * 1000)


def _best_thesis(insights: list[dict]) -> Optional[dict]:
    """The observation worth quoting: the one backed by the most reasons, shortest wins ties."""
    with_thesis = [i for i in insights if (i.get("bluf_thesis") or "").strip()]
    if not with_thesis:
        return None
    return max(with_thesis, key=lambda i: (len(i.get("reasons") or []), -len(i["bluf_thesis"])))


def _clip(text: str, n: int = THESIS_MAX_CHARS) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[:n] + "…"


def select_rows(episodes: list[dict], insights: list[dict], names: dict[str, str], top: int = TOP_TICKERS) -> list[dict]:
    """Rank today's tickers by (shows, mentions) and attach one sourced quote each. Pure."""
    ep_by_id = {e["id"]: e for e in episodes}
    by_ticker: dict[str, list[dict]] = defaultdict(list)
    for i in insights:
        if i.get("ticker") and i.get("episode_id") in ep_by_id:
            by_ticker[i["ticker"]].append(i)
    rows = []
    for tk, ins in by_ticker.items():
        shows = {i.get("podcaster") for i in ins if i.get("podcaster")}
        stance = Counter(_sentiment(i.get("sentiment_label")) for i in ins)
        best = _best_thesis(ins)
        ep = ep_by_id.get(best["episode_id"]) if best else None
        rows.append({
            "ticker": tk, "name": names.get(tk), "mentions": len(ins), "shows": len(shows),
            "bull": stance["bull"], "neu": stance["neu"], "bear": stance["bear"],
            "thesis": _clip(best["bluf_thesis"]) if best else None,
            "podcaster": best.get("podcaster") if best else None,
            "episode_id": ep["id"] if ep else None,
            "episode_title": (ep.get("episode_title") or "") if ep else "",
        })
    rows.sort(key=lambda r: (r["shows"], r["mentions"], r["ticker"]), reverse=True)
    return rows[:top]


def render_digest(day: date, episodes: list[dict], rows: list[dict]) -> dict:
    """``{title, markdown, excerpt}`` for one day. Pure."""
    site = settings.site_url.rstrip("/")
    shows = Counter(e.get("podcast_name") or "" for e in episodes)
    show_line = "、".join(f"{n} {c} 集" for n, c in shows.most_common())
    title = f"聽播客每日精選 {day.isoformat()}｜今天節目講了哪些股票"
    out = [
        f"追蹤的節目今天共 {len(episodes)} 集（{show_line}），提到 {len(rows)} 檔以上的股票。"
        f"以下是被最多節目講到的 {len(rows)} 檔，每檔附一句節目裡講的理由和出處。",
        "",
    ]
    for r in rows:
        head = f"{r['name']}（{r['ticker']}）" if r.get("name") else r["ticker"]
        parts = [f"{r['shows']} 個節目 · {r['mentions']} 則觀點"]
        stance = " / ".join(f"{k} {v}" for k, v in (("看多", r["bull"]), ("中性", r["neu"]), ("看空", r["bear"])) if v)
        if stance:
            parts.append(stance)
        out.append(f"## {head}")
        out.append(" · ".join(parts))
        if r.get("thesis"):
            src = r.get("podcaster") or ""
            if r.get("episode_id"):
                src += f"《{r['episode_title'] or r['episode_id']}》（{site}/episode/{r['episode_id']}）"
            out.append(f"「{r['thesis']}」——{src}")
        out.append("")
    week = week_of_ms(day_bounds_ms(day)[0])
    out += [
        "## 資料說明",
        DISCLAIMER,
        f"每檔股票的聲量水位與完整觀點在 {site}/stock/代號 ；本週統計：{site}/weekly/{week}",
    ]
    excerpt = "、".join((r.get("name") or r["ticker"]) for r in rows[:5])
    return {"title": title, "markdown": "\n".join(out), "excerpt": f"今天節目講到：{excerpt}"}


async def build_daily_digest(day: date) -> Optional[dict]:
    """The digest for one Asia/Taipei day, or None when no scoped episode was released."""
    lo, hi = day_bounds_ms(day)
    episodes = [
        ep.model_dump(mode="json")
        for ep in await podcast_service.get_recent_episodes(limit=2000, enrich_content=False)
        if (ms := _released_ms(ep)) is not None and lo <= ms < hi
    ]
    if not episodes:
        return None
    podcasters = sorted({e["podcast_name"] for e in episodes if e.get("podcast_name")})
    # One day either side: podcast_launch_time is a UTC string, the day is Taipei.
    insights = await _insights_for(podcasters, day - timedelta(days=1), day + timedelta(days=1))
    tickers = {i["ticker"] for i in insights if i.get("ticker")}

    def _names() -> dict[str, str]:
        for db in get_session():
            return query_names(db, tickers)
        return {}

    names = await asyncio.to_thread(_names) if tickers else {}
    rows = select_rows(episodes, insights, names)
    if not rows:
        return None
    return {"day": day.isoformat(), "episode_count": len(episodes), "rows": rows, **render_digest(day, episodes, rows)}


async def publish_daily_digest(day: date, *, dry_run: bool, as_draft: bool) -> dict:
    """Publish one day to vocus through the shared claim-then-publish ledger."""
    from src.routers.social import _syndicate_once  # routers import services; keep this lazy
    from src.services import vocus_publisher

    digest = await build_daily_digest(day)
    if digest is None:
        return {"day": day.isoformat(), "posted": False, "reason": "no_episodes"}
    key = f"digest:{day.isoformat()}"
    result = await _syndicate_once("vocus", key, lambda: vocus_publisher.publish_markdown(
        key, digest["title"], digest["markdown"],
        canonical_url="",  # vocus-native: there is no tinboker copy to point at
        abstract=digest["excerpt"], tags=VOCUS_TAGS, as_draft=as_draft, dry_run=dry_run,
    ), dry_run)
    return {**result, "day": day.isoformat(), "episode_count": digest["episode_count"], "tickers": len(digest["rows"])}


async def run_periodic_daily_digest(interval_seconds: float = 600.0) -> None:
    """Background loop: once a day, after PUBLISH_AT Asia/Taipei, publish today's digest.

    Gated by ``settings.digest_autopublish`` so only the environment that owns
    syndication runs it; the ledger makes a second environment a no-op anyway.
    """
    if not settings.digest_autopublish:
        return
    from src.services import social_ledger
    while True:
        try:
            now = datetime.now(TAIPEI)
            if now.time() >= PUBLISH_AT:
                key = f"digest:{now.date().isoformat()}"
                if not await asyncio.to_thread(social_ledger.posted_record, "vocus", key):
                    result = await publish_daily_digest(now.date(), dry_run=False, as_draft=False)
                    logger.info("daily digest %s: posted=%s reason=%s", key, result.get("posted"), result.get("reason"))
        except Exception as e:  # noqa: BLE001 — a bad day must not kill the loop
            logger.exception("daily digest tick failed: %s", e)
        await asyncio.sleep(interval_seconds)
