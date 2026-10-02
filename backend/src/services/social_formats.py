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
from zoneinfo import ZoneInfo

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

TAIPEI = ZoneInfo("Asia/Taipei")


def _last_complete_week() -> date:
    today = datetime.now(TAIPEI).date()
    return today - timedelta(days=today.weekday() + 7)


def _weekly_episode_date(episode) -> Optional[date]:
    """Use publication time, never ingestion time, for weekly source attribution."""
    released = getattr(episode, "released_at_ms", None)
    if released:
        return datetime.fromtimestamp(released / 1000, tz=TAIPEI).date()
    try:
        return date.fromisoformat(getattr(episode, "spotify_release_date", None) or "")
    except ValueError:
        return None


async def _weekly_sources(start: date, end: date) -> list[dict]:
    from src.services.threads_publisher import podcast_service

    allowed = await podcast_service._allowed_podcast_names()
    episodes = await podcast_service.get_recent_episodes(limit=5000, enrich_content=False)
    selected = [ep for ep in episodes
                if (allowed is None or ep.podcast_name in allowed)
                and (released := _weekly_episode_date(ep)) is not None
                and start <= released <= end]
    # Bound hydration and model context; an unexpectedly large week needs review.
    if len(selected) > 80:
        logger.warning("weekly editorial has too many sources: %s", len(selected))
        return []
    semaphore = asyncio.Semaphore(4)

    async def hydrate(ep) -> Optional[dict]:
        async with semaphore:
            detail = await podcast_service.get_episode_by_id_only(
                ep.id, content_fields={"modified_summary_content", "summary_content"})
        if detail is None or detail.podcast_name != ep.podcast_name:
            return None
        released = _weekly_episode_date(detail)
        if released is None or not start <= released <= end:
            return None
        summary = (getattr(detail, "modified_summary_content", None)
                   or getattr(detail, "summary_content", None) or "").strip()
        if not 100 <= len(summary) <= 24000:
            return None
        return {"episode_id": detail.id, "podcast_name": detail.podcast_name,
                "title": detail.episode_title or detail.id, "date": released.isoformat(), "summary": summary}

    sources = [row for row in await asyncio.gather(*(hydrate(ep) for ep in selected)) if row]
    if sum(len(row["summary"]) for row in sources) > 240000:
        logger.warning("weekly editorial source context exceeds budget")
        return []
    return sources


async def _weekly_editorial(payload: dict) -> Optional[dict]:
    """The pipeline caches validated, rendered bundles; no template fallback."""
    import httpx

    base = (settings.netcup_api_url or "").rstrip("/")
    if not base:
        return None
    headers = {"X-API-Key": settings.podcast_api_key} if settings.podcast_api_key else {}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=5.0)) as client:
            response = await client.post(f"{base}/api/podcast/weekly-editorial", headers=headers, json=payload)
            response.raise_for_status()
            return response.json()
    except Exception:
        logger.exception("weekly editorial pipeline failed for %s", payload["week"])
        return None


async def select_weekly_movers() -> Optional[dict]:
    """Last complete week's sourced editorial carousel, retaining the existing ledger key."""
    start = _last_complete_week()
    end = start + timedelta(days=6)
    iso = start.isocalendar()
    week = f"{iso.year}-W{iso.week:02d}"
    episodes = await _weekly_sources(start, end)
    if len(episodes) < 3:
        return None
    result = await _weekly_editorial({"week": week, "start": start.isoformat(),
                                      "end": end.isoformat(), "episodes": episodes})
    if not isinstance(result, dict) or result.get("week") != week:
        return None
    images = result.get("image_urls")
    text = result.get("post")
    if (not isinstance(images, list) or len(images) != 3
            or any(not isinstance(url, str) or not url.startswith("https://") for url in images)
            or len(set(images)) != 3
            or not isinstance(text, str) or not text.strip() or len(text) > 500):
        logger.warning("weekly editorial returned an incomplete bundle for %s", week)
        return None
    return {"key": f"weekly_movers:{start.isoformat()}", "subject": start.isoformat(),
            "text": text.strip(), "image_urls": images,
            "url": f"{settings.site_url.rstrip('/')}/weekly/{week}"}


# ── post-hoc: what a show said, and what the price did since ──────────────────

POST_HOC_WINDOW_DAYS = 21   # mentions this recent; r5d must exist, so ≥ 5 sessions old
POST_HOC_MIN_MOVE = 8.0     # percent, baseline close → latest close
POST_HOC_MAX_ATTEMPTS = 3
STANCE_DIRECTION = {"BULLISH": 1, "STRONG_BULLISH": 1, "BEARISH": -1, "STRONG_BEARISH": -1}


def _stance_matches_move(label: Optional[str], pct: float) -> bool:
    direction = STANCE_DIRECTION.get((label or "").strip().upper())
    return direction is not None and pct * direction > 0


def _md(iso: str) -> str:
    """'2026-09-01' → '9/1'."""
    y, m, d = iso.split("-")
    return f"{int(m)}/{int(d)}"


def post_hoc_text(c: dict, story: str) -> str:
    """The story (the pipeline's post_hoc_copy_writer, clock stopped on air date) and
    then the one line only this side can write: air date → latest close. Selection
    requires the documented stance to agree with the observed direction."""
    word = "漲" if c["pct"] >= 0 else "跌"
    # Willy's spec for this line: the stock's name, one space, then the numbers run
    # together — 雙鴻 8/31到9/16漲8.8%.
    return (f'{story.strip()}\n\n{c["name"]} '
            f'{_md(c["mention_date"])}到{_md(c["last_date"])}{word}{abs(c["pct"]):.1f}%')


async def _story(c: dict, mode: str = "post_hoc") -> Optional[str]:
    """Ask the pipeline for the story of that episode's take on that stock. None on any
    failure — no story, no post; the number line alone is the caption Willy rejected.
    ``mode`` "today" is the same-day variant (present tense, no price line follows)."""
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
                      "speaker": speaker_for(c.get("podcaster")), "mode": mode})
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
            if abs(pct) < POST_HOC_MIN_MOVE or not _stance_matches_move(m.sentiment_label, pct):
                continue
            out.append({
                "ticker": m.ticker, "name": names.get(m.ticker) or m.display_name or m.ticker,
                "episode_id": m.episode_id, "podcaster": m.podcaster or "",
                "sentiment_label": m.sentiment_label, "thesis": m.thesis,
                "mention_date": snap.mention_date, "baseline_close": snap.baseline_close,
                "mention_start_s": m.mention_start_s,
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
             if (c["pct"] >= 0) == (direction > 0)
             and _stance_matches_move(c.get("sentiment_label"), c["pct"])]
    for c in cands[:POST_HOC_MAX_ATTEMPTS]:
        story = await _story(c)
        if story:
            break
    else:
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
        # Land on the part of the episode where the stock came up, and say so.
        "focus_ms": int(c["mention_start_s"] * 1000) if c.get("mention_start_s") else None,
        "link_hook": f'{speaker_for(c["podcaster"])} {_md(c["mention_date"])}那集講{c["name"]}的段落',
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
    would_post = None
    for fmt in FORMATS:
        try:
            draft = await fmt.select()
        except Exception as e:  # show the failure next to the format, not a 500
            draft, err = None, str(e)[:200]
        else:
            err = None
        if (would_post is None and draft and format_off_cooldown(fmt, recent, now)
                and subject_off_cooldown(fmt, draft.get("subject"), recent, now)):
            would_post = await _publish(fmt, draft, dry_run=True)
        formats.append({
            "format": fmt.id, "draft": draft,
            "format_off_cooldown": format_off_cooldown(fmt, recent, now),
            "subject_off_cooldown": subject_off_cooldown(fmt, (draft or {}).get("subject"), recent, now),
            **({"error": err} if err else {}),
        })
    return {"would_post": would_post, "formats": formats}


async def _publish(fmt: Format, draft: dict, dry_run: bool) -> dict:
    service = ThreadsService()
    base = {"format": fmt.id, "key": draft["key"], "subject": draft.get("subject"), "text": draft["text"]}
    if dry_run or not service.is_configured:
        return {**base, "posted": False, "dry_run": True}
    if not social_ledger.claim(PLATFORM, draft["key"]):
        return {**base, "posted": False, "reason": "already_posted"}
    try:
        if draft.get("image_urls"):
            media_id = await service.publish_carousel(draft["image_urls"], draft["text"])
        else:
            media_id = await service.publish(draft["text"], image_url=draft.get("image_url"))
        reply_ids: list[str] = []
        if draft.get("url"):
            # Link in the first reply, not the body — same reason as the episode posts.
            from src.services.threads_publisher import social_link
            url = draft["url"]
            if isinstance(draft.get("focus_ms"), int) and draft["focus_ms"] >= 1000:
                url = f'{url}?t={draft["focus_ms"]}'
            hook = (draft.get("link_hook") or "").strip()
            text = f"▶ {hook}\n{social_link(url, fmt.id)}" if hook else f"▶ {social_link(url, fmt.id)}"
            reply_ids.append(await service.publish_reply(text, reply_to_id=media_id))
    except ThreadsError as e:
        social_ledger.release(PLATFORM, draft["key"])
        return {**base, "posted": False, "reason": f"publish_failed: {e}"}
    social_ledger.record(PLATFORM, draft["key"], media_id, draft.get("url") or "", reply_ids,
                         fmt=fmt.id, subject=draft.get("subject"))
    return {**base, "posted": True, "media_id": media_id}
