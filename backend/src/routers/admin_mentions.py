"""Refresh one persisted episode's derived mentions after ingest or regeneration."""

import asyncio
import logging
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException

from src.auth.admin_auth import AdminAccess, get_content_write_access
from src.cache.cdn_cache import purge_cdn_cache
from src.services import mention_sync

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin/episodes", tags=["admin"])


@router.post("/{episode_id}/sync-mentions")
async def sync_episode_mentions(
    episode_id: str,
    admin: AdminAccess = Depends(get_content_write_access),
) -> dict:
    try:
        counts = await asyncio.to_thread(mention_sync.sync_episode_mentions, episode_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    # The shared table backs every environment; these routes have CDN caching only.
    encoded_id = quote(episode_id, safe="")
    urls = [
        f"https://{host}/api/episodes/{encoded_id}/{suffix}"
        for host in ("api.tinboker.com", "staging-api.tinboker.com", "dev-api.tinboker.com")
        for suffix in ("mentions", "cross-show")
    ]
    try:
        if not await purge_cdn_cache(urls=urls):
            logger.warning("Mention sync CDN purge failed for episode %s", episode_id)
    except Exception:
        logger.warning("Mention sync CDN purge failed for episode %s", episode_id, exc_info=True)
    return {"episode_id": episode_id, **counts}
