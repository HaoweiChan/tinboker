"""Admin: the agents' podcast pipeline configuration (read-only).

Reads it LIVE from the podcast service (GET {netcup_api_url}/api/config), falling back
to a committed static snapshot when the service is unreachable. The tinboker-agents repo
is the source of truth; this view never writes.
"""

import logging

import httpx
from fastapi import APIRouter, Depends

from src.config import settings
from src.auth.admin_auth import get_admin_access, AdminAccess
from src.data.pipeline_settings_snapshot import PIPELINE_SETTINGS, SNAPSHOT_META

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/pipeline-settings")
async def get_pipeline_settings(admin: AdminAccess = Depends(get_admin_access)):
    """Read-only pipeline config — live from the podcast service, snapshot fallback."""
    base = (settings.netcup_api_url or "").rstrip("/")
    if base:
        headers = {"X-API-Key": settings.podcast_api_key} if settings.podcast_api_key else {}
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{base}/api/config", headers=headers, timeout=8.0)
                resp.raise_for_status()
                payload = resp.json()
            data = payload.get("settings")
            if isinstance(data, dict) and data:
                return {
                    "meta": {
                        "live": True,
                        "read_only": True,
                        "source": payload.get(
                            "source", "tinboker-agents/services/podcast/configs/default.yaml"
                        ),
                        "fetched_from": base,
                    },
                    "settings": data,
                }
            logger.warning("Live pipeline-config returned no settings; using snapshot")
        except Exception as e:
            logger.warning("Live pipeline-config read failed (%s); using snapshot", e)
    # Fallback: committed static snapshot (service unreachable or no base URL configured).
    return {"meta": {**SNAPSHOT_META, "live": False, "stale": True}, "settings": PIPELINE_SETTINGS}
