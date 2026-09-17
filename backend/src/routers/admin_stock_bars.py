"""Admin: repair stored US daily bars (``services.daily_bars.repair_us_bars``).

Non-production only (mounted under the ``is_production`` gate, like every
``/api/admin/*`` router). dev, staging and prod share ``stock_daily_ohlc``, so one run
from staging repairs all three.

  POST /api/admin/stock-bars/repair-us  — start in the background (a no-op while running)
  GET  /api/admin/stock-bars/repair-us  — progress: done / total / written / failed

~340 tickers at 14 s apart is about 80 minutes.
"""

import asyncio

from fastapi import APIRouter, Depends, Query

from src.auth.admin_auth import AdminAccess, get_admin_access
from src.services import daily_bars

router = APIRouter(prefix="/api/admin/stock-bars", tags=["stock", "admin"])

_task: "asyncio.Task | None" = None


@router.post("/repair-us")
async def start_repair(
    days: int = Query(400, ge=30, le=1825, description="Calendar days to re-fetch per ticker"),
    _: AdminAccess = Depends(get_admin_access),
) -> dict:
    global _task
    # Guard on the task, not REPAIR["running"]: the job marks itself running only after
    # listing tickers, so two quick POSTs would otherwise both start one.
    if _task is None or _task.done():
        _task = asyncio.create_task(daily_bars.repair_us_bars(days=days))
        return {"started": True, **daily_bars.REPAIR}
    return {"started": False, **daily_bars.REPAIR}


@router.get("/repair-us")
async def repair_status(_: AdminAccess = Depends(get_admin_access)) -> dict:
    return dict(daily_bars.REPAIR)
