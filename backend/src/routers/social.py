"""Admin/service endpoints for publishing episode summaries to Threads.

The publish endpoint accepts the TINBOKER_SOCIAL_TOKEN service token as well as an
admin JWT, so the agents' podcast pipeline can call it right after an ingest run to
fan the new episode out to Threads. It is idempotent and dry-run by default.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from src.auth.admin_auth import AdminAccess, get_admin_access, get_social_access
from src.services import threads_publisher

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/threads", tags=["admin", "social"])


@router.post("/publish")
async def publish_to_threads(
    dry_run: bool = Query(default=True, description="Compose only; do not post (default)"),
    limit: int = Query(default=10, ge=1, le=50, description="How many recent episodes to scan"),
    max_age_days: int = Query(
        default=None,
        ge=0,
        description="Only post episodes published within N days (default: configured threads_max_age_days)",
    ),
    _: AdminAccess = Depends(get_social_access),
):
    """Scan recent episodes and post any not-yet-posted ones to Threads.

    Defaults to dry-run (returns the composed drafts). Pass ``dry_run=false`` to
    actually publish. Forced to dry-run when Threads credentials are unconfigured.
    """
    try:
        return await threads_publisher.publish_recent(
            limit=limit, dry_run=dry_run, max_age_days=max_age_days
        )
    except Exception as e:
        logger.exception("Threads publish run failed")
        raise HTTPException(status_code=500, detail=f"Threads publish failed: {e}")


@router.get("/posts")
async def list_threads_posts(
    limit: int = Query(default=50, ge=1, le=200),
    _: AdminAccess = Depends(get_admin_access),
):
    """List episodes already posted to Threads (idempotency ledger)."""
    return {"posts": threads_publisher.list_posted(limit=limit)}
