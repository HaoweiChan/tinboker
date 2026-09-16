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
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Awaitable, Callable, Optional

from src.config import settings
from src.services import social_ledger
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

def weekly_movers_text(data: dict) -> str:
    """Caption for the 本週聲量竄升 card: the top three, numbers only. The card carries
    the full list; the caption's one job is to say what the numbers ARE (mentions, not
    price) so nobody reads a recap as a buy list."""
    lines = [f'{r["ticker"]} {r.get("name") or ""} {r["n"]} 次 上週 {r.get("prev", 0)}'.replace("  ", " ")
             for r in data["rows"][:3]]
    return ("這週 podcast 提及數比上週多最多的\n\n" + "\n".join(lines)
            + "\n\n提及次數 不是漲幅 全部名單在圖裡")


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
    if not data["rows"]:
        return None
    iso = week_start.isocalendar()
    return {
        "key": f"weekly_movers:{data['week_start']}",
        "subject": data["week_start"],
        "text": weekly_movers_text(data),
        "image_url": f"{settings.public_api_url.rstrip('/')}/api/og/weekly.png",
        "url": f"{settings.site_url.rstrip('/')}/weekly/{iso[0]}-W{iso[1]:02d}",
    }


FORMATS: list[Format] = [
    Format("weekly_movers", select_weekly_movers, cooldown_days=6, subject_cooldown_days=6),
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
