"""Compose and publish episode summaries to Threads.

This is the bridge between the agents' podcast ingestion pipeline and the brand's
Threads account. It reads recent episodes (Firestore, via ``podcast_service``),
composes a zh-TW post from the contract fields the agents pipeline writes
(``key_insights``, ``related_tickers``, ``episode_title``) plus a permalink back to
``{site_url}/episode/{id}``, and publishes it.

Two guards keep it safe to run on a schedule:
  * an idempotency table (one row per posted episode) so a re-run never double-posts;
  * a recency window so even a wiped idempotency store can only ever touch episodes
    from the last few days.

With no Threads credentials configured the run is forced to ``dry_run`` — it composes
and returns the drafts without publishing — so the endpoint is always safe to call.
"""

import json
import logging
from datetime import datetime
from typing import Any, Optional

from src.config import settings
from src.database.db import get_connection
from src.services.podcast import PodcastService
from src.services.threads_service import THREADS_MAX_CHARS, ThreadsError, ThreadsService

logger = logging.getLogger(__name__)

podcast_service = PodcastService()

BRAND_HASHTAGS = ["台股", "投資理財", "財經"]
MAX_INSIGHTS = 3
MAX_TICKER_TAGS = 4
MAX_CARDS = 20  # Threads carousel hard limit (cover + up to 19 themes)


def _ensure_table() -> None:
    conn = get_connection()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS threads_posts (
                episode_id TEXT PRIMARY KEY,
                media_id   TEXT,
                url        TEXT,
                reply_ids  TEXT,
                posted_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        # Additive migration for DBs created before the thread (carousel+replies) work.
        # SQLite has no ADD COLUMN IF NOT EXISTS, so swallow the duplicate-column error.
        try:
            conn.execute("ALTER TABLE threads_posts ADD COLUMN reply_ids TEXT")
        except Exception:
            pass
        conn.commit()
    finally:
        conn.close()


def _field(episode: Any, name: str, default=None):
    """Read a field from an Episode model or a plain dict interchangeably."""
    if isinstance(episode, dict):
        return episode.get(name, default)
    return getattr(episode, name, default)


def episode_url(episode_id: str) -> str:
    return f"{settings.site_url.rstrip('/')}/episode/{episode_id}"


def _hashtags(related_tickers: list[str]) -> str:
    tags = list(BRAND_HASHTAGS)
    for sym in (related_tickers or [])[:MAX_TICKER_TAGS]:
        sym = (sym or "").strip().replace(" ", "")
        if sym:
            tags.append(sym)
    return " ".join(f"#{t}" for t in tags)


def compose_post(episode: Any, *, count_line: str = "") -> dict:
    """Build a Threads post draft from an episode. Always <= THREADS_MAX_CHARS chars.

    ``count_line`` (e.g. "⬇️ 7 個重點整理") is reserved in the budget and placed before
    the hashtags/link — used as the carousel caption to signal the thread below.
    Returns ``{episode_id, text, image_url, url}``.
    """
    episode_id = _field(episode, "id") or _field(episode, "episode_id") or ""
    title = (_field(episode, "episode_title") or "").strip()
    podcast_name = (_field(episode, "podcast_name") or "").strip()
    insights = [s.strip() for s in (_field(episode, "key_insights") or []) if s and s.strip()]
    tickers = _field(episode, "related_tickers") or []
    image_url = _field(episode, "summary_image_public_url") or None

    url = episode_url(episode_id)
    link_line = f"\n\n▶ 完整重點：{url}"
    tag_line = f"\n\n{_hashtags(tickers)}"
    count_seg = f"\n\n{count_line}" if count_line else ""

    header = "｜".join(p for p in (podcast_name, title) if p) or title or podcast_name

    # Fixed tail (count + link + hashtags) is reserved first; insights fill what remains.
    budget = THREADS_MAX_CHARS - len(link_line) - len(tag_line) - len(count_seg)
    body = header[:budget] if header else ""

    for insight in insights[:MAX_INSIGHTS]:
        candidate = f"{body}\n\n• {insight}" if body else f"• {insight}"
        if len(candidate) <= budget:
            body = candidate
        else:
            break

    if not body:
        # No header and no insight fit — fall back to a trimmed header/title.
        body = (header or title or podcast_name)[: max(0, budget - 1)].rstrip()

    text = f"{body}{count_seg}{tag_line}{link_line}"
    if len(text) > THREADS_MAX_CHARS:  # defensive; should not trigger given the budget
        text = text[: THREADS_MAX_CHARS - len(link_line)].rstrip() + link_line

    return {"episode_id": episode_id, "text": text, "image_url": image_url, "url": url}


def _compose_reply(title: str, bullets: list[str]) -> str:
    """One threaded reply: 【title】 + bullets, clamped to THREADS_MAX_CHARS."""
    lines = [f"【{title}】"] if title else []
    for bullet in bullets:
        candidate = "\n".join(lines + [f"• {bullet}"])
        if len(candidate) <= THREADS_MAX_CHARS:
            lines.append(f"• {bullet}")
        else:
            break  # never split a bullet (it carries the timestamp) — drop trailing ones
    return "\n".join(lines).strip()


def _finalize_post_text(episode: Any, body: str, count_line: str = "") -> str:
    """Append the fixed tail (count line + ticker hashtags + permalink) to a body,
    clamping to THREADS_MAX_CHARS. Used for the human-authored grand-summary post."""
    episode_id = _field(episode, "id") or _field(episode, "episode_id") or ""
    link_line = f"\n\n▶ 完整重點：{episode_url(episode_id)}"
    tag_line = f"\n\n{_hashtags(_field(episode, 'related_tickers') or [])}"
    count_seg = f"\n\n{count_line}" if count_line else ""
    budget = THREADS_MAX_CHARS - len(link_line) - len(tag_line) - len(count_seg)
    body = (body or "").strip()[:max(0, budget)].rstrip()
    text = f"{body}{count_seg}{tag_line}{link_line}"
    if len(text) > THREADS_MAX_CHARS:
        text = text[: THREADS_MAX_CHARS - len(link_line)].rstrip() + link_line
    return text


def compose_thread(episode: Any) -> dict:
    """Build an AlphaMemo-style thread from an episode's social_cards.

    Returns ``{episode_id, main_text, image_urls, replies, url}`` — the carousel
    caption + ordered card images, and one reply per theme card. image_urls[i] and
    replies line up with the cards (cover is image 0, themes follow).

    Prefers the human-authored ``social_thread`` (post + per-theme comments) when
    present; otherwise falls back to the mechanical ``【title】 + bullets`` compose.
    """
    episode_id = _field(episode, "id") or _field(episode, "episode_id") or ""
    cards = [c for c in (_field(episode, "social_cards") or []) if isinstance(c, dict)]
    image_urls = [c["image_url"] for c in cards if c.get("image_url")][:MAX_CARDS]
    theme_cards = [c for c in cards if c.get("kind") == "theme"]
    count_line = f"⬇️ {len(theme_cards)} 個重點整理" if theme_cards else ""

    thread = _field(episode, "social_thread")
    thread = thread if isinstance(thread, dict) else {}
    human_post = (thread.get("post") or "").strip()
    human_comments = [
        (c.get("text") if isinstance(c, dict) else str(c) or "").strip()
        for c in (thread.get("comments") or [])
    ]
    human_comments = [c for c in human_comments if c]

    if human_post:
        main_text = _finalize_post_text(episode, human_post, count_line)
    else:
        main_text = compose_post(episode, count_line=count_line)["text"]

    replies: list[dict] = []
    if human_comments:
        replies = [{"text": c[:THREADS_MAX_CHARS].rstrip()} for c in human_comments]
    else:
        for card in theme_cards:
            bullets = [b for b in (card.get("bullets") or []) if b and b.strip()]
            text = _compose_reply((card.get("title") or "").strip(), bullets)
            if text:
                replies.append({"text": text})

    return {
        "episode_id": episode_id,
        "main_text": main_text,
        "image_urls": image_urls,
        "replies": replies,
        "url": episode_url(episode_id),
    }


async def publish_thread(service: ThreadsService, draft: dict) -> dict:
    """Publish a composed thread: carousel (or single image) + reply chain.

    Returns ``{root_media_id, reply_ids, image_count, reply_count}``. Per-reply errors
    stop the chain but still return the root (the carousel is already live), so the
    caller records it and never re-posts.
    """
    image_urls = draft["image_urls"]
    if len(image_urls) >= 2:
        root = await service.publish_carousel(image_urls, draft["main_text"])
    elif len(image_urls) == 1:
        root = await service.publish(draft["main_text"], image_url=image_urls[0])
    else:
        root = await service.publish(draft["main_text"])

    reply_ids: list[str] = []
    prev = root
    for reply in draft["replies"]:
        try:
            rid = await service.publish_reply(reply["text"], reply_to_id=prev)
        except ThreadsError as e:
            logger.warning("Reply failed for %s (%d posted): %s", draft["episode_id"], len(reply_ids), e)
            break
        reply_ids.append(rid)
        prev = rid

    return {
        "root_media_id": root,
        "reply_ids": reply_ids,
        "image_count": len(image_urls),
        "reply_count": len(reply_ids),
    }


def _release_ms(episode: Any) -> Optional[int]:
    return _field(episode, "released_at_ms") or _field(episode, "created_time")


def already_posted(episode_id: str) -> bool:
    _ensure_table()
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT 1 FROM threads_posts WHERE episode_id = ?", (episode_id,)
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def _record(episode_id: str, media_id: str, url: str, reply_ids: Optional[list[str]] = None) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO threads_posts (episode_id, media_id, url, reply_ids, posted_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (episode_id, media_id, url, json.dumps(reply_ids or []), datetime.utcnow().isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


def list_posted(limit: int = 50) -> list[dict]:
    _ensure_table()
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT episode_id, media_id, url, reply_ids, posted_at FROM threads_posts "
            "ORDER BY posted_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            try:
                d["reply_ids"] = json.loads(d.get("reply_ids") or "[]")
            except (TypeError, ValueError):
                d["reply_ids"] = []
            out.append(d)
        return out
    finally:
        conn.close()


async def publish_recent(
    limit: int = 10,
    dry_run: bool = True,
    max_age_days: Optional[int] = None,
) -> dict:
    """Post any recent, not-yet-posted episodes to Threads.

    Returns a summary with the drafts that were (or would be) posted and the
    reasons others were skipped. Safe to call repeatedly; idempotent per episode.
    """
    _ensure_table()
    service = ThreadsService()
    configured = service.is_configured
    effective_dry_run = dry_run or not configured

    if max_age_days is None:
        max_age_days = settings.threads_max_age_days
    cutoff_ms: Optional[int] = None
    if max_age_days and max_age_days > 0:
        cutoff_ms = int((datetime.utcnow().timestamp() - max_age_days * 86400) * 1000)

    episodes = await podcast_service.get_recent_episodes(limit=limit, enrich_content=False)

    posted: list[dict] = []
    skipped: list[dict] = []

    for episode in episodes:
        episode_id = _field(episode, "id") or _field(episode, "episode_id") or ""
        if not episode_id:
            continue
        if already_posted(episode_id):
            skipped.append({"episode_id": episode_id, "reason": "already_posted"})
            continue
        rel_ms = _release_ms(episode)
        if cutoff_ms is not None and (rel_ms is None or rel_ms < cutoff_ms):
            skipped.append({"episode_id": episode_id, "reason": "outside_recency_window"})
            continue
        has_cards = bool(_field(episode, "social_cards"))
        if not (has_cards or _field(episode, "key_insights") or _field(episode, "episode_title")):
            skipped.append({"episode_id": episode_id, "reason": "no_postable_content"})
            continue

        # Prefer the full thread (carousel + reply chain) when the episode has rendered
        # cards; otherwise fall back to a single text/image post (legacy episodes).
        if has_cards:
            thread = compose_thread(episode)
            if effective_dry_run:
                posted.append({
                    "episode_id": episode_id, "url": thread["url"],
                    "main_text": thread["main_text"], "image_count": len(thread["image_urls"]),
                    "reply_count": len(thread["replies"]), "dry_run": True,
                })
                continue
            try:
                res = await publish_thread(service, thread)
                _record(episode_id, res["root_media_id"], thread["url"], res["reply_ids"])
                posted.append({"episode_id": episode_id, "url": thread["url"], "dry_run": False, **res})
                logger.info("Posted thread for %s (root=%s, %d replies)",
                            episode_id, res["root_media_id"], res["reply_count"])
            except ThreadsError as e:
                skipped.append({"episode_id": episode_id, "reason": f"publish_failed: {e}"})
            continue

        draft = compose_post(episode)
        if effective_dry_run:
            posted.append({**draft, "dry_run": True})
            continue
        try:
            media_id = await service.publish(draft["text"], image_url=draft["image_url"])
            _record(episode_id, media_id, draft["url"])
            posted.append({**draft, "media_id": media_id, "dry_run": False})
            logger.info("Posted episode %s to Threads (%s)", episode_id, media_id)
        except ThreadsError as e:
            skipped.append({"episode_id": episode_id, "reason": f"publish_failed: {e}"})

    return {
        "platform": "threads",
        "configured": configured,
        "dry_run": effective_dry_run,
        "candidates": len(episodes),
        "posted_count": len([p for p in posted if not p.get("dry_run")]),
        "posted": posted,
        "skipped": skipped,
    }


async def publish_episode(episode: Any, dry_run: bool = True) -> dict:
    """Publish one already-fetched episode to Threads (the admin "發佈" button).

    Unlike :func:`publish_recent` this targets a single, explicitly chosen episode
    and ignores the recency window (the operator picked it). Still idempotent
    (skips if already posted) and forced to dry-run when unconfigured. Returns a
    flat result: ``{platform, configured, dry_run, episode_id, posted, ...}`` with
    ``posted`` True only on a real publish, else a ``reason`` for the skip/preview.
    """
    _ensure_table()
    service = ThreadsService()
    configured = service.is_configured
    effective_dry_run = dry_run or not configured
    episode_id = _field(episode, "id") or _field(episode, "episode_id") or ""
    base = {"platform": "threads", "configured": configured, "dry_run": effective_dry_run, "episode_id": episode_id}

    if not episode_id:
        return {**base, "posted": False, "reason": "no_episode_id"}
    if already_posted(episode_id):
        return {**base, "posted": False, "reason": "already_posted", "url": episode_url(episode_id)}
    has_cards = bool(_field(episode, "social_cards"))
    if not (has_cards or _field(episode, "key_insights") or _field(episode, "episode_title")):
        return {**base, "posted": False, "reason": "no_postable_content"}

    if has_cards:
        thread = compose_thread(episode)
        if effective_dry_run:
            return {**base, "posted": False, "reason": "dry_run", "url": thread["url"],
                    "main_text": thread["main_text"], "image_count": len(thread["image_urls"]),
                    "reply_count": len(thread["replies"])}
        try:
            res = await publish_thread(service, thread)
        except ThreadsError as e:
            return {**base, "posted": False, "reason": f"publish_failed: {e}", "url": thread["url"]}
        _record(episode_id, res["root_media_id"], thread["url"], res["reply_ids"])
        logger.info("Posted thread for %s (root=%s, %d replies)", episode_id, res["root_media_id"], res["reply_count"])
        return {**base, "posted": True, "url": thread["url"], **res}

    draft = compose_post(episode)
    if effective_dry_run:
        return {**base, "posted": False, "reason": "dry_run", **draft}
    try:
        media_id = await service.publish(draft["text"], image_url=draft["image_url"])
    except ThreadsError as e:
        return {**base, "posted": False, "reason": f"publish_failed: {e}", "url": draft["url"]}
    _record(episode_id, media_id, draft["url"])
    logger.info("Posted episode %s to Threads (%s)", episode_id, media_id)
    return {**base, "posted": True, "media_id": media_id, **draft}
