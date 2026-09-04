"""Shared idempotency ledger for social publishing (Threads, Facebook, vocus, Substack).

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
from datetime import datetime
from typing import Optional

from sqlalchemy.exc import IntegrityError

from src.database.models import SocialPostLedger
from src.database.postgres import session_scope

logger = logging.getLogger(__name__)


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
) -> None:
    """Fill in the ids of a claimed row once the post is actually live."""
    with session_scope() as db:
        row = db.get(SocialPostLedger, (platform, episode_id))
        if row is None:  # claim skipped (manual publish path) — insert outright
            row = SocialPostLedger(platform=platform, episode_id=episode_id)
            db.add(row)
        row.media_id = media_id
        row.url = url
        row.child_ids = child_ids or []
        row.posted_at = datetime.utcnow()


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
                "media_id": row.media_id, "url": row.url,
                "posted_at": row.posted_at.isoformat() if row.posted_at else None}


def list_posted(platform: str, limit: int = 50) -> list[dict]:
    with session_scope() as db:
        rows = (
            db.query(SocialPostLedger)
            .filter(SocialPostLedger.platform == platform)
            .order_by(SocialPostLedger.posted_at.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "episode_id": r.episode_id,
                "media_id": r.media_id,
                "url": r.url,
                "child_ids": r.child_ids or [],
                "posted_at": r.posted_at.isoformat() if r.posted_at else None,
            }
            for r in rows
        ]
