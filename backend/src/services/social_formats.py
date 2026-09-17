"""Post shapes other than "one episode → one carousel", and the rule for which one a
posting slot gets.

By mid-September 2026, 105 of the account's 128 Threads posts were the same skeleton
(a judgment line + theme-card carousel + reply chain), readers had learned to skip it,
and weekly views had fallen from 179K to ~12K with the per-post median unchanged. The
fix is variety in STRUCTURE, which needs three things this module supplies:

  * a registry — one ``Format`` per shape, in priority order;
  * a selector — per slot, the first registered format that has something to say
    today AND is off cooldown, both for the format itself and for its subject (the
    same ticker five times in three days is what killed the AI-slowdown posts);
  * a ledger entry with ``format`` + ``subject`` so the per-format engagement report
    (``/insights/by-format``) can say which shapes to keep.

Episode posts stay in ``threads_publisher.publish_recent`` — they are many-per-slot
and episode-keyed. This lane posts at most ONE extra shape per slot, keyed by
``draft["key"]`` in the shared ledger (the ``episode_id`` column doubles as the key;
``weekly_movers:2026-09-07`` cannot collide with an episode id).

Adding a shape: write a ``select()`` that returns a draft or ``None``, append a
``Format`` to ``FORMATS``. Nothing else. ponytail: priority is list order; add
weights or randomness only once two formats measurably compete for the same slot.
"""
from __future__ import annotations

import asyncio
import logging
import urllib.parse
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Awaitable, Callable, Optional

from src.config import settings
from src.database.models import ContentMention, TickerPerformanceSnapshot
from src.database.postgres import get_session
from src.services import social_ledger
from src.services.attention import scope_mentions
from src.services.content_source_service import speaker_for
from src.services.threads_service import ThreadsError, ThreadsService

logger = logging.getLogger(__name__)

PLATFORM = "threads"


@dataclass(frozen=True)
class Format:
    id: str
    select: Callable[[], Awaitable[Optional[dict]]]
    """Today's draft — ``{key, subject, text, image_url, url}`` — or None for "no material"."""
    cooldown_days: int
    """The same shape again no sooner than this."""
    subject_cooldown_days: int
    """The same subject (ticker / week / topic), in ANY shape, no sooner than this."""


# ── selection (pure) ────────────────────────────────────────────────────────

def _posted_at(row: dict) -> Optional[datetime]:
    raw = row.get("posted_at")
    return datetime.fromisoformat(raw) if raw else None


def _within(row: dict, now: datetime, days: int) -> bool:
    ts = _posted_at(row)
    return ts is not None and ts >= now - timedelta(days=days)


def format_off_cooldown(fmt: Format, recent: list[dict], now: datetime) -> bool:
    return not any(r.get("format") == fmt.id and _within(r, now, fmt.cooldown_days) for r in recent)


def subject_off_cooldown(fmt: Format, subject: Optional[str], recent: list[dict], now: datetime) -> bool:
    if not subject:
        return True
    return not any(r.get("subject") == subject and _within(r, now, fmt.subject_cooldown_days)
                   for r in recent)


# ── formats ─────────────────────────────────────────────────────────────────

# A recap with nothing in it is worse than no recap. Both floors are guesses against
# one week of data (W37: total 327, top rise +6 — thin); tune from the by-format report.
WEEKLY_MIN_TOTAL = 500      # market-wide mentions in the week
WEEKLY_MIN_RISE = 5         # the leader's week-over-week gain in mentions
WEEKLY_BUSY_N = 8           # runners-up only get a line when they are this loud


def _tk(r: dict) -> str:
    return f'{r["ticker"]} {r.get("name") or ""}'.strip()


def weekly_movers_text(data: dict) -> str:
    """Caption for the 本週聲量竄升 card. It is about the leader — which shows, which
    way they leaned — and mentions the runners-up only when they are loud too. The
    card carries the full list; the caption's other job is to say what the numbers ARE
    (mentions, not price) so nobody reads a recap as a buy list."""
    top, *rest = data["rows"]
    bull, bear = top.get("bull", 0), top.get("bear", 0)
    lean = "看多的多" if bull > bear else "看空的多" if bear > bull else "多空各半"
    lines = [f'{_tk(top)} 這週{top.get("casts", 0)}個節目提了{top["n"]}次 上週{top.get("prev", 0)} {lean}']
    busy = [r for r in rest if r["n"] >= WEEKLY_BUSY_N][:2]
    if busy:
        lines.append("")
        lines.append("也很吵的還有")
        lines += [f'{_tk(r)} {r["n"]}次 上週{r.get("prev", 0)}' for r in busy]
    return "\n".join(lines) + "\n\n提及次數 不是漲幅 全部名單在圖裡"


def _last_complete_week() -> date:
    today = date.today()
    return today - timedelta(days=today.weekday() + 7)


async def select_weekly_movers() -> Optional[dict]:
    """Last complete week's biggest risers in mention count — the same card and ranking
    the ``/api/og/weekly.png`` route draws, so the caption and the image agree."""
    # ponytail: the movers query lives in the og router; lazy import avoids the
    # router→service→router cycle. Move it to weekly_card when a third caller appears.
    from src.routers.og import _weekly_movers
    from src.services.threads_publisher import podcast_service

    week_start = _last_complete_week()
    allowed = await podcast_service._allowed_podcast_names()
    data = await asyncio.to_thread(_weekly_movers, week_start, allowed)
    rows = data["rows"]
    if (not rows or data["total"] < WEEKLY_MIN_TOTAL
            or rows[0]["n"] - rows[0].get("prev", 0) < WEEKLY_MIN_RISE):
        return None
    iso = week_start.isocalendar()
    return {
        "key": f"weekly_movers:{data['week_start']}",
        "subject": data["week_start"],
        "text": weekly_movers_text(data),
        "image_url": f"{settings.public_api_url.rstrip('/')}/api/og/weekly.png",
        "url": f"{settings.site_url.rstrip('/')}/weekly/{iso[0]}-W{iso[1]:02d}",
    }


# ── post-hoc: what a show said, and what the price did since ──────────────────

POST_HOC_WINDOW_DAYS = 21   # mentions this recent; r5d must exist, so ≥ 5 sessions old
POST_HOC_MIN_MOVE = 8.0     # percent, baseline close → latest close
STANCE_ZH = {"BULLISH": "看多", "BEARISH": "看空"}


def _md(iso: str) -> str:
    """'2026-09-01' → '9/1'."""
    y, m, d = iso.split("-")
    return f"{int(m)}/{int(d)}"


def post_hoc_text(c: dict, story: str) -> str:
    """The story (the pipeline's post_hoc_copy_writer, clock stopped on air date) and
    then the one line only this side can write: air date → latest close. No verdict:
    a 看空 followed by 漲 19% needs no help, and the misses post on purpose — that is
    what makes the hits worth anything."""
    word = "漲" if c["pct"] >= 0 else "跌"
    # Willy's spec for this line: the stock's name, one space, then the numbers run
    # together — 雙鴻 8/31到9/16漲8.8%.
    return (f'{story.strip()}\n\n{c["name"]} '
            f'{_md(c["mention_date"])}到{_md(c["last_date"])}{word}{abs(c["pct"]):.1f}%')


async def _story(c: dict) -> Optional[str]:
    """Ask the pipeline for the story of that episode's take on that stock. None on any
    failure — no story, no post; the number line alone is the caption Willy rejected."""
    import httpx
    base = (settings.netcup_api_url or "").rstrip("/")
    if not base:
        return None
    headers = {"X-API-Key": settings.podcast_api_key} if settings.podcast_api_key else {}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=5.0)) as client:
            resp = await client.post(
                f"{base}/api/podcast/episodes/{c['episode_id']}/post-hoc-copy", headers=headers,
                json={"ticker": c["ticker"], "name": c["name"], "mention_date": c["mention_date"],
                      "sentiment_label": c.get("sentiment_label"), "thesis": c.get("thesis"),
                      "speaker": speaker_for(c.get("podcaster"))})
        if resp.status_code >= 400:
            logger.warning("post-hoc story %s/%s -> %s: %s", c["episode_id"], c["ticker"],
                           resp.status_code, resp.text[:200])
            return None
        return (resp.json().get("post") or "").strip() or None
    except Exception as e:  # noqa: BLE001 — a dead pipeline skips this slot, nothing more
        logger.warning("post-hoc story call failed for %s/%s: %r", c["episode_id"], c["ticker"], e)
        return None


def _post_hoc_candidates(allowed: Optional[frozenset], since: datetime) -> list[dict]:
    """Recent ticker mentions with a thesis and a 5-session return, best-moved first.
    Sync — runs under ``asyncio.to_thread`` like every other mention reader."""
    from src.services.mention_sync import _closes_from
    from src.services.paid_weekly import query_names

    for db in get_session():
        rows = (
            scope_mentions(db.query(ContentMention, TickerPerformanceSnapshot), allowed)
            .join(TickerPerformanceSnapshot, TickerPerformanceSnapshot.mention_id == ContentMention.id)
            .filter(ContentMention.mention_type == "ticker",
                    ContentMention.mentioned_at >= since,
                    ContentMention.thesis.isnot(None),
                    TickerPerformanceSnapshot.r5d.isnot(None),
                    TickerPerformanceSnapshot.price_break_date.is_(None))
            .order_by(TickerPerformanceSnapshot.mention_date.desc())
            .all()
        )
        shows_by_ticker: dict[str, set] = {}
        for m, _ in rows:
            shows_by_ticker.setdefault(m.ticker, set()).add(m.podcaster)
        # r5d ranks the shortlist; the caption quotes baseline → LATEST close instead,
        # because "五個交易日後" is a window nobody reads a chart in.
        top = sorted(rows, key=lambda r: -abs(r[1].r5d))[:15]
        names = query_names(db, {m.ticker for m, _ in top})
        out = []
        for m, snap in top:
            closes = _closes_from(db, m.ticker, snap.mention_date)
            if not closes or not snap.baseline_close:
                continue
            last_date, last_close = closes[-1]
            pct = (last_close - snap.baseline_close) / snap.baseline_close * 100
            if abs(pct) < POST_HOC_MIN_MOVE:
                continue
            out.append({
                "ticker": m.ticker, "name": names.get(m.ticker) or m.display_name or m.ticker,
                "episode_id": m.episode_id, "podcaster": m.podcaster or "",
                "sentiment_label": m.sentiment_label, "thesis": m.thesis,
                "mention_date": snap.mention_date, "baseline_close": snap.baseline_close,
                "last_date": last_date, "last_close": last_close, "pct": pct,
                "others": len(shows_by_ticker.get(m.ticker, set()) - {m.podcaster}),
            })
        return sorted(out, key=lambda c: -abs(c["pct"]))
    return []


async def _select_post_hoc(direction: int) -> Optional[dict]:
    """The recent mention whose ticker moved most in ``direction`` (+1 up, -1 down) —
    each direction is its own format so a big riser and a big faller both get told."""
    from src.services.threads_publisher import episode_url, podcast_service

    allowed = await podcast_service._allowed_podcast_names()
    since = datetime.utcnow() - timedelta(days=POST_HOC_WINDOW_DAYS)
    cands = [c for c in await asyncio.to_thread(_post_hoc_candidates, allowed, since)
             if (c["pct"] >= 0) == (direction > 0)]
    if not cands:
        return None
    c = cands[0]
    story = await _story(c)
    if not story:
        return None
    label = f'{c["podcaster"]} {_md(c["mention_date"])}'
    api = settings.public_api_url.rstrip("/")
    return {
        "key": f'post_hoc:{c["ticker"]}:{c["episode_id"]}',
        "subject": c["ticker"],
        "text": post_hoc_text(c, story),
        "image_url": f'{api}/api/og/stock/{c["ticker"]}.png?days=60&event={c["mention_date"]}'
                     f'&label={urllib.parse.quote(label)}',
        "url": episode_url(c["episode_id"]),
    }


async def select_post_hoc_up() -> Optional[dict]:
    return await _select_post_hoc(+1)


async def select_post_hoc_down() -> Optional[dict]:
    return await _select_post_hoc(-1)


FORMATS: list[Format] = [
    # Monday recap first — it is rarer; post-hoc takes the next slot the same day.
    Format("weekly_movers", select_weekly_movers, cooldown_days=6, subject_cooldown_days=6),
    Format("post_hoc_up", select_post_hoc_up, cooldown_days=3, subject_cooldown_days=14),
    Format("post_hoc_down", select_post_hoc_down, cooldown_days=3, subject_cooldown_days=14),
]


# ── the slot ────────────────────────────────────────────────────────────────

async def publish_due_format(dry_run: bool = False, now: Optional[datetime] = None) -> Optional[dict]:
    """Post at most one non-episode shape for this slot. Returns what was (or would be)
    posted, or None when every format is quiet or cooling down."""
    if not FORMATS:
        return None
    now = now or datetime.utcnow()
    horizon = max(max(f.cooldown_days, f.subject_cooldown_days) for f in FORMATS)
    recent = social_ledger.list_posted(PLATFORM, limit=500, days=horizon)

    for fmt in FORMATS:
        if not format_off_cooldown(fmt, recent, now):
            continue
        try:
            draft = await fmt.select()
        except Exception:  # one broken query must not silence the other formats
            logger.exception("format %s select failed", fmt.id)
            continue
        if not draft or not subject_off_cooldown(fmt, draft.get("subject"), recent, now):
            continue
        return await _publish(fmt, draft, dry_run)
    return None


async def preview(now: Optional[datetime] = None) -> dict:
    """Every format's draft for today plus what the next slot would actually post —
    so the caption can be read before Monday, not after."""
    now = now or datetime.utcnow()
    horizon = max((max(f.cooldown_days, f.subject_cooldown_days) for f in FORMATS), default=1)
    recent = social_ledger.list_posted(PLATFORM, limit=500, days=horizon)
    formats = []
    for fmt in FORMATS:
        try:
            draft = await fmt.select()
        except Exception as e:  # show the failure next to the format, not a 500
            draft, err = None, str(e)[:200]
        else:
            err = None
        formats.append({
            "format": fmt.id, "draft": draft,
            "format_off_cooldown": format_off_cooldown(fmt, recent, now),
            "subject_off_cooldown": subject_off_cooldown(fmt, (draft or {}).get("subject"), recent, now),
            **({"error": err} if err else {}),
        })
    return {"would_post": await publish_due_format(dry_run=True, now=now), "formats": formats}


async def _publish(fmt: Format, draft: dict, dry_run: bool) -> dict:
    service = ThreadsService()
    base = {"format": fmt.id, "key": draft["key"], "subject": draft.get("subject"), "text": draft["text"]}
    if dry_run or not service.is_configured:
        return {**base, "posted": False, "dry_run": True}
    if not social_ledger.claim(PLATFORM, draft["key"]):
        return {**base, "posted": False, "reason": "already_posted"}
    try:
        media_id = await service.publish(draft["text"], image_url=draft.get("image_url"))
        reply_ids: list[str] = []
        if draft.get("url"):
            # Link in the first reply, not the body — same reason as the episode posts.
            reply_ids.append(await service.publish_reply(f"▶ {draft['url']}", reply_to_id=media_id))
    except ThreadsError as e:
        social_ledger.release(PLATFORM, draft["key"])
        return {**base, "posted": False, "reason": f"publish_failed: {e}"}
    social_ledger.record(PLATFORM, draft["key"], media_id, draft.get("url") or "", reply_ids,
                         fmt=fmt.id, subject=draft.get("subject"))
    return {**base, "posted": True, "media_id": media_id}
