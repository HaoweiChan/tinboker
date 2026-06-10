"""Admin endpoints for the episode watcher."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from src.auth import verify_api_key

router = APIRouter(prefix="/api/watcher", tags=["watcher"])


def _get_watcher():
    from app import get_watcher
    watcher = get_watcher()
    if watcher is None:
        raise HTTPException(status_code=503, detail="Watcher not initialized")
    return watcher


@router.get("/status")
async def watcher_status():
    """Current watcher state: last poll, next poll, processing queue."""
    watcher = _get_watcher()
    return watcher.status.to_dict()


@router.post("/trigger", dependencies=[Depends(verify_api_key)])
async def trigger_poll():
    """Manually trigger a single poll cycle. Requires API key."""
    watcher = _get_watcher()
    results = await watcher.trigger_poll()
    return {
        "triggered": True,
        "results": [
            {
                "show_name": r.show_name,
                "new_episodes": r.new_episodes,
                "error": r.error,
            }
            for r in results
        ],
    }
