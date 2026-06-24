"""Admin API endpoints for system status and monitoring."""

import asyncio
import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from src.auth.admin_auth import AdminAccess, get_admin_access
from src.cache.redis_client import cache_get, cache_set
from src.schemas.system import SystemStatusResponse
from src.services.firestore_service import FirestoreService
from src.services.system_service import get_system_status

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/admin/system",
    tags=["admin", "system"],
)


class UserCountResponse(BaseModel):
    count: int


@router.get("/status", response_model=SystemStatusResponse)
async def system_status(
    admin: AdminAccess = Depends(get_admin_access),
):
    """
    Get system status for admin dashboard.

    Returns health metrics for:
    - Backend service (uptime, version)
    - Redis (connection status, memory usage)
    - PostgreSQL (connection pool status)
    - System metrics (CPU, memory, disk - if psutil available)
    """
    return await get_system_status()


@router.get("/user-count", response_model=UserCountResponse)
async def user_count(admin: AdminAccess = Depends(get_admin_access)):
    """Total registered users (Firestore `users` collection). Cached 5 min."""
    cached = await cache_get("admin:user_count")
    if cached is not None:
        return UserCountResponse(count=int(cached))
    count = await asyncio.to_thread(FirestoreService().count_collection, "users")
    await cache_set("admin:user_count", str(count), ttl=300)
    return UserCountResponse(count=count)
