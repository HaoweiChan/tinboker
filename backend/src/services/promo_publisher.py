"""Publish a free-form promo post (operator-authored text + media) to Threads and/or
Facebook in one shot.

Unlike the episode publishers this carries NO composition or idempotency: the operator
writes everything and each publish is an intentional one-off. The only smarts are the
per-platform media rules, which differ:

  * Threads — a single post can be text, one image/video, or a 2–20 item carousel that
    MAY mix images and videos.
  * Facebook — a feed post can hold multiple photos OR a single video, but NOT both, and
    not multiple videos. Per the product decision, a mixed promo is blocked on Facebook
    (Threads still posts) rather than silently dropping media.

``plan_threads`` / ``plan_facebook`` are pure so the rules are unit-tested without the API.
"""

import logging
from typing import Optional

from src.services.facebook_service import FACEBOOK_MAX_ALBUM, FacebookError, FacebookService
from src.services.threads_service import THREADS_MAX_CHARS, ThreadsError, ThreadsService

logger = logging.getLogger(__name__)

THREADS_MAX_MEDIA = 20  # carousel hard limit


class PromoError(ValueError):
    """A promo cannot be represented on a platform (caller turns this into a skip reason)."""


def _split(media: list[dict]) -> tuple[list[dict], list[dict]]:
    images = [m for m in media if m.get("type") == "image"]
    videos = [m for m in media if m.get("type") == "video"]
    return images, videos


def plan_threads(text: str, media: list[dict]) -> dict:
    """Decide the Threads post shape, or raise PromoError if it can't be represented."""
    if not media and not (text or "").strip():
        raise PromoError("empty")
    if len((text or "")) > THREADS_MAX_CHARS:
        raise PromoError("text_too_long")
    if len(media) > THREADS_MAX_MEDIA:
        raise PromoError("too_many_media")
    if not media:
        return {"kind": "text"}
    if len(media) == 1:
        return {"kind": "single", "item": media[0]}
    return {"kind": "carousel", "items": media}


def plan_facebook(text: str, media: list[dict]) -> dict:
    """Decide the single Facebook post shape, or raise PromoError when FB can't hold it.

    FB cannot mix photos + video, nor carry multiple videos, in one post.
    """
    images, videos = _split(media)
    if not media and not (text or "").strip():
        raise PromoError("empty")
    if images and videos:
        raise PromoError("fb_mixed_media")
    if len(videos) > 1:
        raise PromoError("fb_multiple_videos")
    if videos:
        return {"kind": "video", "url": videos[0]["url"]}
    if len(images) > FACEBOOK_MAX_ALBUM:
        raise PromoError("fb_too_many_photos")
    if len(images) >= 2:
        return {"kind": "album", "urls": [m["url"] for m in images]}
    if len(images) == 1:
        return {"kind": "photo", "url": images[0]["url"]}
    return {"kind": "text"}


def _meta_error_reason(exc: Exception) -> str:
    """Map a raw Meta OAuth/Graph error to a short, actionable reason code.

    - token_expired:           code 190 / "Session has expired" → re-mint the token.
    - insufficient_permission: (#200) → token is missing a scope (e.g. Facebook
                               comments need pages_manage_engagement).
    """
    s = str(exc).lower()
    if "code': 190" in s or "session has expired" in s or "validating access token" in s:
        return "token_expired"
    if "(#200)" in s or "code': 200" in s or "sufficient permission" in s:
        return "insufficient_permission"
    return "publish_failed"


async def _publish_threads(text: str, media: list[dict], comments: list[str], dry_run: bool) -> dict:
    service = ThreadsService()
    configured = service.is_configured
    effective_dry_run = dry_run or not configured
    base = {"platform": "threads", "configured": configured, "dry_run": effective_dry_run,
            "media_count": len(media), "comment_count": len(comments)}
    try:
        plan = plan_threads(text, media)
    except PromoError as e:
        return {**base, "posted": False, "reason": str(e)}
    if any(len(c) > THREADS_MAX_CHARS for c in comments):
        return {**base, "posted": False, "reason": "comment_too_long"}
    if effective_dry_run:
        return {**base, "posted": False, "reason": "dry_run", "plan": plan["kind"]}
    try:
        if plan["kind"] == "text":
            media_id = await service.publish(text)
        elif plan["kind"] == "single":
            media_id = await service.publish_single_media(text, plan["item"])
        else:
            media_id = await service.publish_media_carousel(plan["items"], text)
    except ThreadsError as e:
        kind = _meta_error_reason(e)
        reason = "threads_token_expired" if kind == "token_expired" else f"publish_failed: {e}"
        return {**base, "posted": False, "reason": reason}
    # Chain each comment as a reply to the previous one (a Threads thread). A failure
    # stops the chain but keeps the already-live root.
    reply_ids: list[str] = []
    comment_error: Optional[str] = None
    prev = media_id
    for c in comments:
        try:
            prev = await service.publish_reply(c, reply_to_id=prev)
        except ThreadsError as e:
            comment_error = _meta_error_reason(e)
            logger.warning("promo Threads reply failed (%d posted): %s", len(reply_ids), e)
            break
        reply_ids.append(prev)
    logger.info("Promo posted to Threads (%s, %s, %d replies)", media_id, plan["kind"], len(reply_ids))
    out = {**base, "posted": True, "media_id": media_id, "plan": plan["kind"], "posted_comments": len(reply_ids)}
    if comment_error:
        out["comment_error"] = comment_error
    return out


async def _publish_facebook(text: str, media: list[dict], comments: list[str], dry_run: bool) -> dict:
    service = FacebookService()
    configured = service.is_configured
    effective_dry_run = dry_run or not configured
    base = {"platform": "facebook", "configured": configured, "dry_run": effective_dry_run,
            "media_count": len(media), "comment_count": len(comments)}
    try:
        plan = plan_facebook(text, media)
    except PromoError as e:
        return {**base, "posted": False, "reason": str(e)}
    if effective_dry_run:
        return {**base, "posted": False, "reason": "dry_run", "plan": plan["kind"]}
    try:
        if plan["kind"] == "text":
            post_id = await service.publish_text(text)
        elif plan["kind"] == "photo":
            post_id = await service.publish_photo(text, plan["url"])
        elif plan["kind"] == "album":
            post_id = await service.publish_album(text, plan["urls"])
        else:  # video
            post_id = await service.publish_video(text, plan["url"])
    except FacebookError as e:
        kind = _meta_error_reason(e)
        reason = "fb_token_expired" if kind == "token_expired" else f"publish_failed: {e}"
        return {**base, "posted": False, "reason": reason}
    # Post each comment on the root post. A failure stops the rest but keeps the post.
    posted_comments = 0
    comment_error: Optional[str] = None
    for c in comments:
        try:
            await service.comment(post_id, c)
        except FacebookError as e:
            comment_error = _meta_error_reason(e)
            logger.warning("promo FB comment failed (%d posted): %s", posted_comments, e)
            break
        posted_comments += 1
    logger.info("Promo posted to Facebook (%s, %s, %d comments)", post_id, plan["kind"], posted_comments)
    out = {**base, "posted": True, "post_id": post_id, "plan": plan["kind"], "posted_comments": posted_comments}
    if comment_error:
        out["comment_error"] = comment_error
    return out


_PUBLISHERS = {"threads": _publish_threads, "facebook": _publish_facebook}


async def publish_promo(
    text: str,
    media: list[dict],
    platforms: list[str],
    comments: Optional[list[str]] = None,
    dry_run: bool = True,
) -> dict:
    """Publish one promo to each selected platform; one independent result per platform.

    ``comments`` are posted as a reply chain (Threads) / comments on the post (Facebook),
    text-only, after the root. A failure or platform-specific block (e.g. FB mixed media)
    never affects the others.
    """
    text = (text or "").strip()
    media = media or []
    comments = [c.strip() for c in (comments or []) if c and c.strip()]
    results: dict = {}
    for name in platforms:
        fn = _PUBLISHERS.get(name)
        if not fn:
            results[name] = {"platform": name, "posted": False, "reason": "unknown_platform"}
            continue
        try:
            results[name] = await fn(text, media, comments, dry_run)
        except Exception as e:  # never let one platform's crash sink the others
            logger.exception("promo publish failed for %s", name)
            results[name] = {"platform": name, "posted": False, "error": str(e)}
    return {"platforms": results}
