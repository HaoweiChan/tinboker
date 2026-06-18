"""Compose + publish episode summaries to a Facebook Page.

Reuses the platform-agnostic composer from ``threads_publisher`` (``compose_thread``
/ ``compose_post`` build the same ``social_thread``-aware draft), and maps it onto
Facebook's post+comments model:

  - the carousel images  → a multi-photo album post (the summary is the caption)
  - the reply chain      → comments on that post (one per theme card)

Idempotency is tracked in a separate ``facebook_posts`` ledger so an episode posts
once per platform (Threads and Facebook are recorded independently).
"""

import json
import logging
from datetime import datetime
from typing import Optional

from src.config import settings
from src.database.db import get_connection
from src.services.facebook_service import FacebookError, FacebookService
from src.services.threads_publisher import (
    _field,
    _release_ms,
    compose_post,
    compose_thread,
    podcast_service,
)

logger = logging.getLogger(__name__)


def _ensure_table() -> None:
    conn = get_connection()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS facebook_posts (
                episode_id  TEXT PRIMARY KEY,
                post_id     TEXT,
                url         TEXT,
                comment_ids TEXT,
                posted_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def already_posted(episode_id: str) -> bool:
    _ensure_table()
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT 1 FROM facebook_posts WHERE episode_id = ?", (episode_id,)
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def _record(episode_id: str, post_id: str, url: str, comment_ids: Optional[list[str]] = None) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO facebook_posts (episode_id, post_id, url, comment_ids, posted_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (episode_id, post_id, url, json.dumps(comment_ids or []), datetime.utcnow().isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


def list_posted(limit: int = 50) -> list[dict]:
    _ensure_table()
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT episode_id, post_id, url, comment_ids, posted_at FROM facebook_posts "
            "ORDER BY posted_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            try:
                d["comment_ids"] = json.loads(d.get("comment_ids") or "[]")
            except (TypeError, ValueError):
                d["comment_ids"] = []
            out.append(d)
        return out
    finally:
        conn.close()


async def publish_thread(service: FacebookService, draft: dict) -> dict:
    """Publish a composed thread to a Page: album/photo/text post + comment chain.

    Per-comment errors stop the chain but still return the root (the post is already
    live), so the caller records it and never re-posts.
    """
    image_urls = draft["image_urls"]
    if len(image_urls) >= 2:
        post_id = await service.publish_album(draft["main_text"], image_urls)
    elif len(image_urls) == 1:
        post_id = await service.publish_photo(draft["main_text"], image_urls[0])
    else:
        post_id = await service.publish_text(draft["main_text"])

    comment_ids: list[str] = []
    for reply in draft["replies"]:
        try:
            cid = await service.comment(post_id, reply["text"])
        except FacebookError as e:
            logger.warning("FB comment failed for %s (%d posted): %s",
                           draft["episode_id"], len(comment_ids), e)
            break
        comment_ids.append(cid)

    return {
        "root_post_id": post_id,
        "comment_ids": comment_ids,
        "image_count": len(image_urls),
        "comment_count": len(comment_ids),
    }


async def publish_recent(
    limit: int = 10,
    dry_run: bool = True,
    max_age_days: Optional[int] = None,
) -> dict:
    """Post any recent, not-yet-FB-posted episodes to the Facebook Page.

    Mirrors threads_publisher.publish_recent: same recency + content guards and the
    same composed draft, but a separate idempotency ledger. Idempotent per episode.
    """
    _ensure_table()
    service = FacebookService()
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

        if has_cards:
            thread = compose_thread(episode)
            if effective_dry_run:
                posted.append({
                    "episode_id": episode_id, "url": thread["url"],
                    "main_text": thread["main_text"], "image_count": len(thread["image_urls"]),
                    "comment_count": len(thread["replies"]), "dry_run": True,
                })
                continue
            try:
                res = await publish_thread(service, thread)
                _record(episode_id, res["root_post_id"], thread["url"], res["comment_ids"])
                posted.append({"episode_id": episode_id, "url": thread["url"], "dry_run": False, **res})
                logger.info("Posted FB album for %s (post=%s, %d comments)",
                            episode_id, res["root_post_id"], res["comment_count"])
            except FacebookError as e:
                skipped.append({"episode_id": episode_id, "reason": f"publish_failed: {e}"})
            continue

        draft = compose_post(episode)
        if effective_dry_run:
            posted.append({**draft, "dry_run": True})
            continue
        try:
            if draft.get("image_url"):
                post_id = await service.publish_photo(draft["text"], draft["image_url"])
            else:
                post_id = await service.publish_text(draft["text"])
            _record(episode_id, post_id, draft["url"])
            posted.append({**draft, "post_id": post_id, "dry_run": False})
            logger.info("Posted episode %s to Facebook (%s)", episode_id, post_id)
        except FacebookError as e:
            skipped.append({"episode_id": episode_id, "reason": f"publish_failed: {e}"})

    return {
        "platform": "facebook",
        "configured": configured,
        "dry_run": effective_dry_run,
        "candidates": len(episodes),
        "posted_count": len([p for p in posted if not p.get("dry_run")]),
        "posted": posted,
        "skipped": skipped,
    }
