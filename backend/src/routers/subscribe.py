"""
TinBoker → Substack subscription funnel (issue #424).

A minimal, measurable *outbound* funnel — not an ESP. Two moving parts:

  * ``GET  /api/subscribe``       — the stable outbound entry point owned by TinBoker.
                                     Records an outbound-click event (attributed to
                                     ``?source=``) and 302-redirects to the config-driven
                                     newsletter destination (Substack today).
  * ``POST /api/subscribe/view``  — fire-and-forget beacon the landing page posts once on
                                     mount, so we can measure landing views vs. clicks.

Counts live in Redis sorted sets keyed by ``source`` so ``/api/admin/analytics/subscribe``
can rank which CTA slot drives the most intent. No PII, no account linkage, no payment.
See ``docs/features/subscription-funnel.md`` for the event/param contract.
"""
import logging
import re

from fastapi import APIRouter, BackgroundTasks, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, field_validator

from src.cache.redis_client import get_redis
from src.config import settings

router = APIRouter(prefix="/api/subscribe", tags=["subscribe"])
logger = logging.getLogger(__name__)

# Redis ZSETs: member = source slot, score = cumulative count.
VIEW_KEY = "analytics:subscribe:view"
CLICK_KEY = "analytics:subscribe:click"

# The endpoints are public (fire-and-forget from the web app), so ``source`` is tightly
# bounded — an attacker could otherwise grow the ZSETs with unlimited unique members until
# the shared cache OOMs. Slots are snake_case identifiers chosen by CTA authors, not free
# text; anything else collapses to ``unknown`` (still counted, never rejected).
_SOURCE_RE = re.compile(r"^[a-z0-9_]{1,64}$")
UNKNOWN_SOURCE = "unknown"


def normalize_source(raw: str | None) -> str:
    """Coerce an attribution slot to a safe, bounded identifier."""
    if not raw:
        return UNKNOWN_SOURCE
    value = raw.strip().lower()
    return value if _SOURCE_RE.match(value) else UNKNOWN_SOURCE


async def _record(key: str, source: str) -> None:
    try:
        redis = await get_redis()
        if not redis:
            return
        await redis.zincrby(key, 1, source)
    except Exception as e:  # never let analytics break the redirect
        logger.error("Error recording subscribe funnel event %s/%s: %s", key, source, e)


class SubscribeView(BaseModel):
    source: str = UNKNOWN_SOURCE

    @field_validator("source", mode="before")
    @classmethod
    def _clean(cls, v: object) -> str:
        return normalize_source(v if isinstance(v, str) else None)


@router.get("", include_in_schema=True)
async def subscribe_outbound(
    background_tasks: BackgroundTasks,
    source: str = Query(default=UNKNOWN_SOURCE, description="CTA slot that sent the user"),
):
    """Record the outbound click and 302-redirect to the newsletter destination.

    Recording server-side (rather than a fire-and-forget beacon that races the navigation)
    makes the click count reliable. The destination is config-driven so it can move off
    Substack without a code change.
    """
    slot = normalize_source(source)
    background_tasks.add_task(_record, CLICK_KEY, slot)
    logger.info("subscribe outbound click source=%s -> %s", slot, settings.newsletter_subscribe_url)
    # 302 (not 307): a transient redirect to an external host; never cache it.
    return RedirectResponse(url=settings.newsletter_subscribe_url, status_code=302)


@router.post("/view", status_code=202)
async def subscribe_view(event: SubscribeView, background_tasks: BackgroundTasks):
    """Fire-and-forget beacon: the subscribe landing page was viewed."""
    background_tasks.add_task(_record, VIEW_KEY, event.source)
    return {"status": "accepted"}
