"""Shared idempotency ledger for social publishing (Threads, Facebook, vocus).

One table, one row per (platform, episode_id). Replaces the two container-local
SQLite ledgers that were lost on every redeploy.

Because dev, staging and production share this Postgres *and* the publishing
credentials, the ledger is also what stops two environments from posting the same
episode twice — which is exactly how vocus ended up with duplicate articles whose only
difference was an ``api.`` versus ``staging-api.`` cover URL.

The contract is claim-then-publish:

    if not claim("threads", ep):   # someone else has it (or it is already posted)
        skip
    try:
        media_id = publish(...)
        record("threads", ep, media_id, url, child_ids)
    except Exception:
        release("threads", ep)     # nothing went out — let the next run retry
        raise
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.exc import IntegrityError

from src.database.models import SocialPostLedger
from src.database.postgres import session_scope

logger = logging.getLogger(__name__)


def parse_threads_timestamp(value: Optional[str]) -> datetime:
    if not value:
        raise ValueError("missing timestamp")
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("invalid timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


def claim(platform: str, episode_id: str) -> bool:
    """Reserve this episode for posting. False when it is already claimed/posted.

    The INSERT is the lock: the (platform, episode_id) primary key makes a second
    claim fail, so concurrent triggers cannot both start publishing the same episode.
    """
    try:
        with session_scope() as db:
            db.add(SocialPostLedger(platform=platform, episode_id=episode_id, child_ids=[]))
        return True
    except IntegrityError:
        return False


def record(
    platform: str,
    episode_id: str,
    media_id: str,
    url: str,
    child_ids: Optional[list[str]] = None,
    fmt: Optional[str] = None,
    subject: Optional[str] = None,
    *,
    origin: Optional[str] = None,
    delivery: Optional[str] = None,
    permalink: Optional[str] = None,
    post_snapshot: Optional[dict] = None,
    provider_snapshot: Optional[dict] = None,
    tracking_error: Optional[str] = None,
) -> None:
    """Fill in the ids of a claimed row once the post is actually live."""
    with session_scope() as db:
        row = db.get(SocialPostLedger, (platform, episode_id))
        if row is None:  # claim skipped (manual publish path) — insert outright
            row = SocialPostLedger(platform=platform, episode_id=episode_id)
            db.add(row)
        if row.media_id is None:
            row.posted_at = datetime.utcnow()
        row.media_id = media_id
        row.url = url
        row.child_ids = child_ids or []
        row.format = fmt
        row.subject = subject
        if origin is not None:
            row.origin = origin
        if delivery is not None:
            row.delivery = delivery
        if permalink is not None:
            row.permalink = permalink
        if post_snapshot is not None:
            row.post_snapshot = post_snapshot
        if provider_snapshot is not None:
            row.provider_snapshot = provider_snapshot
        row.tracking_error = tracking_error


def import_threads_post(
    media: dict, owned_replies: Optional[list[dict]] = None, *, replies_truncated: bool = False
) -> tuple[str, bool]:
    """Upsert a provider-discovered root by media ID, without replacing publish-time copy."""
    media_id = str(media.get("id") or "")
    if not media_id:
        raise ValueError("Threads provider post is missing its media ID")
    timestamp = media.get("timestamp")
    posted_at = parse_threads_timestamp(timestamp)
    provider_snapshot = {
        "source": "threads_api",
        "fetched_at": datetime.utcnow().isoformat() + "Z",
        "timestamp": timestamp,
        "text": media.get("text"),
        "media_type": media.get("media_type"),
        "media_url": media.get("media_url"),
        "children": media.get("children") or [],
        "username": media.get("username"),
        "owner_id": (media.get("owner") or {}).get("id"),
        "is_reply": bool(media.get("is_reply")),
        "root_post_id": (media.get("root_post") or {}).get("id"),
        "replied_to_id": (media.get("replied_to") or {}).get("id"),
        "owned_replies": [
            {k: r.get(k) for k in ("id", "text", "timestamp", "permalink", "replied_to", "root_post")}
            for r in (owned_replies or [])
            if r.get("is_reply_owned_by_me") is True and r.get("id")
        ],
        "owned_replies_loaded": owned_replies is not None,
        "owned_replies_truncated": bool(replies_truncated),
    }
    with session_scope() as db:
        row = (
            db.query(SocialPostLedger)
            .filter(SocialPostLedger.platform == "threads", SocialPostLedger.media_id == media_id)
            .order_by(SocialPostLedger.posted_at.asc())
            .first()
        )
        created = row is None
        if created:
            row = SocialPostLedger(
                platform="threads",
                episode_id=f"threads-api:{media_id}",
                media_id=media_id,
                child_ids=[],
                format="api_import",
                permalink=media.get("permalink"),
                posted_at=posted_at,
            )
            db.add(row)
        else:
            if not row.permalink and media.get("permalink"):
                row.permalink = media["permalink"]
            if owned_replies is None:
                previous = row.provider_snapshot or {}
                provider_snapshot["owned_replies"] = previous.get("owned_replies", [])
                provider_snapshot["owned_replies_loaded"] = previous.get("owned_replies_loaded", False)
                provider_snapshot["owned_replies_truncated"] = previous.get("owned_replies_truncated", False)
        existing_children = row.child_ids or []
        reply_ids = [str(r["id"]) for r in owned_replies or [] if r.get("is_reply_owned_by_me") is True and r.get("id")]
        row.child_ids = list(dict.fromkeys([*existing_children, *reply_ids]))
        row.provider_snapshot = provider_snapshot
        # Existing origin and publish-time snapshot are authoritative; imported records
        # deliberately keep origin NULL rather than guessing manual vs automated.
        return row.episode_id, created


def release(platform: str, episode_id: str) -> None:
    """Drop a claim whose publish failed, so a later run can try again."""
    try:
        with session_scope() as db:
            row = db.get(SocialPostLedger, (platform, episode_id))
            if row is not None:
                db.delete(row)
    except Exception:  # a stuck claim only costs one skipped episode — never raise here
        logger.exception("failed to release %s ledger claim for %s", platform, episode_id)


def already_posted(platform: str, episode_id: str) -> bool:
    with session_scope() as db:
        return db.get(SocialPostLedger, (platform, episode_id)) is not None


def posted_record(platform: str, episode_id: str) -> Optional[dict]:
    """The ledger row for one episode, or None. Read for the URL a refused claim points at."""
    with session_scope() as db:
        row = db.get(SocialPostLedger, (platform, episode_id))
        if row is None:
            return None
        return {"platform": row.platform, "episode_id": row.episode_id,
                "media_id": row.media_id, "url": row.url, "permalink": row.permalink,
                "posted_at": row.posted_at.isoformat() if row.posted_at else None}


def list_posted(platform: str, limit: int = 50, days: Optional[int] = None) -> list[dict]:
    """Newest first; ``days`` restricts to rows posted inside that window."""
    with session_scope() as db:
        q = db.query(SocialPostLedger).filter(SocialPostLedger.platform == platform)
        if days:
            q = q.filter(SocialPostLedger.posted_at >= datetime.utcnow() - timedelta(days=days))
        rows = (
            q.order_by(SocialPostLedger.posted_at.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "episode_id": r.episode_id,
                "media_id": r.media_id,
                "url": r.url,
                "child_ids": r.child_ids or [],
                "format": r.format,
                "subject": r.subject,
                "origin": r.origin or "unknown",
                "delivery": r.delivery,
                "permalink": r.permalink,
                "post_snapshot": r.post_snapshot or {},
                "provider_snapshot": r.provider_snapshot or {},
                "tracking_error": r.tracking_error,
                "posted_at": r.posted_at.isoformat() if r.posted_at else None,
            }
            for r in rows
        ]
