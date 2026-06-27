import asyncio
import logging
from datetime import datetime

from src.database.postgres import SessionLocal
from src.database.models import ScheduledSocialPost
from src.services import facebook_publisher, threads_publisher, promo_publisher
from src.services.podcast import PodcastService
from src.services.gcs_content import GCSContentService

logger = logging.getLogger(__name__)

_gcs = GCSContentService()
_PUBLISHERS = {"threads": threads_publisher, "facebook": facebook_publisher}
podcast_service = PodcastService()


async def _resign_media(stored: list) -> list:
    """Re-sign GCS paths in stored media into fresh 12h URLs for publishing."""
    out = []
    for m in stored or []:
        url = None
        if m.get("path"):
            try:
                url = await _gcs.generate_signed_url(m["path"], expiration_hours=12)
            except Exception as e:
                logger.warning("scheduled worker media re-sign failed for %s: %s", m.get("path"), e)
        out.append({
            "type": m.get("type"),
            "url": url,
            "path": m.get("path"),
            "filename": m.get("filename")
        })
    return out


async def process_scheduled_posts() -> int:
    """Scan and process pending scheduled posts that are due.

    Returns the number of processed posts.
    """
    db = SessionLocal()
    try:
        now = datetime.utcnow()
        # Find pending posts scheduled in the past
        posts = (
            db.query(ScheduledSocialPost)
            .filter(
                ScheduledSocialPost.status == "pending",
                ScheduledSocialPost.scheduled_for <= now
            )
            .order_by(ScheduledSocialPost.scheduled_for.asc())
            .all()
        )

        if not posts:
            return 0

        logger.info("Found %d scheduled posts due for publishing", len(posts))
        processed = 0

        for post in posts:
            # Atomic transition to "processing" to avoid duplicate posting in multi-env VPS
            affected = (
                db.query(ScheduledSocialPost)
                .filter(
                    ScheduledSocialPost.id == post.id,
                    ScheduledSocialPost.status == "pending"
                )
                .update({"status": "processing"})
            )
            db.commit()

            if affected == 0:
                logger.info("Post %d was already claimed by another worker", post.id)
                continue

            logger.info("Processing scheduled post %d (type=%s)", post.id, post.post_type)
            results = {}
            overall_success = False
            error_msg = None

            try:
                if post.post_type == "episode":
                    if not post.episode_id:
                        raise ValueError("episode_id is missing for episode post type")

                    episode = await podcast_service.get_episode_admin(post.episode_id)
                    if not episode:
                        raise ValueError(f"Episode {post.episode_id} not found in store")

                    # Auto-render card PNGs if needed
                    cards = getattr(episode, "social_cards", None) or []
                    if cards and not any(c.get("image_url") for c in cards):
                        try:
                            episode = await podcast_service.render_social_card_pngs(post.episode_id)
                        except Exception as render_err:
                            logger.warning(
                                "auto-render before scheduled publish failed for episode %s: %s",
                                post.episode_id,
                                render_err
                            )

                    # Publish to selected platforms
                    for platform_name in post.platforms:
                        pub = _PUBLISHERS.get(platform_name)
                        if not pub:
                            results[platform_name] = {
                                "platform": platform_name,
                                "posted": False,
                                "reason": "unknown_platform"
                            }
                            continue
                        try:
                            res = await pub.publish_episode(episode, dry_run=False)
                            results[platform_name] = res
                            if res.get("posted"):
                                overall_success = True
                        except Exception as pub_err:
                            logger.exception("scheduled publish failed for platform %s on episode %s", platform_name, post.episode_id)
                            results[platform_name] = {
                                "platform": platform_name,
                                "posted": False,
                                "error": str(pub_err)
                            }

                elif post.post_type == "promo":
                    # Re-sign media paths
                    resigned_media = await _resign_media(post.media)
                    # Publish promo
                    promo_res = await promo_publisher.publish_promo(
                        text=post.text,
                        media=resigned_media,
                        platforms=post.platforms,
                        comments=post.comments,
                        dry_run=False
                    )
                    results = promo_res.get("platforms", {})
                    # If any platform was posted successfully
                    for p_name, p_res in results.items():
                        if p_res.get("posted"):
                            overall_success = True

                else:
                    raise ValueError(f"Invalid post type: {post.post_type}")

            except Exception as e:
                logger.exception("Failed processing scheduled post %d", post.id)
                error_msg = str(e)

            # Update DB with final result
            final_status = "posted" if overall_success else "failed"
            db.query(ScheduledSocialPost).filter(ScheduledSocialPost.id == post.id).update({
                "status": final_status,
                "posted_at": datetime.utcnow() if overall_success else None,
                "published_results": results,
                "error_message": error_msg,
                "updated_at": datetime.utcnow()
            })
            db.commit()
            logger.info("Scheduled post %d processing completed. Status=%s", post.id, final_status)
            processed += 1

        return processed
    finally:
        db.close()


async def run_periodic_scheduled_posts(interval_seconds: float = 60.0) -> None:
    """Loop to periodically run the scheduled posts processor."""
    logger.info("Starting scheduled social posts background worker (interval=%.1fs)", interval_seconds)
    while True:
        try:
            await process_scheduled_posts()
        except Exception:
            logger.exception("scheduled social posts worker cycle encountered an error")
        await asyncio.sleep(interval_seconds)
