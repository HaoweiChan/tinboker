"""Admin: pipeline configuration with editable overrides.

The pipeline defaults live in code (pipelines/services/podcast/src/podcast/content_builder/llm.py).
Admins can override specific settings via the admin page; overrides are stored in a Postgres
table and merged on top of code defaults at each pipeline run.
"""

import logging
from typing import Any

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.auth.admin_auth import get_admin_access, AdminAccess
from src.config import settings
from src.data.pipeline_settings_snapshot import PIPELINE_SETTINGS, SNAPSHOT_META
from src.database.models import PipelineConfigOverride
from src.database.postgres import get_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"])

AVAILABLE_MODELS = [
    {"id": "openrouter:xiaomi/mimo-v2.5", "label": "Xiaomi MiMo-V2.5", "price_per_ep": "$0.010", "topic_score": "6/7", "speed": "79s"},
    {"id": "openrouter:deepseek/deepseek-v4-flash", "label": "DeepSeek V4 Flash", "price_per_ep": "$0.007", "topic_score": "5/7", "speed": "170s"},
    {"id": "gemini-2.5-flash", "label": "Gemini 2.5 Flash", "price_per_ep": "$0.040", "topic_score": "5/7", "speed": "208s"},
    {"id": "openrouter:deepseek/deepseek-v3.2", "label": "DeepSeek V3.2", "price_per_ep": "$0.014", "topic_score": "4/7", "speed": "401s"},
]


def _deep_merge(base: dict, overrides: dict) -> dict:
    """Recursively merge overrides into base dict."""
    result = base.copy()
    for key, val in overrides.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = val
    return result


def _get_overrides(db: Session) -> dict[str, Any]:
    """Read the current config overrides from the DB."""
    row = db.query(PipelineConfigOverride).filter_by(namespace="default").first()
    if row and row.overrides:
        return row.overrides
    return {}


@router.get("/pipeline-settings")
async def get_pipeline_settings(
    admin: AdminAccess = Depends(get_admin_access),
    db: Session = Depends(get_session),
):
    """Pipeline config — live from the pipeline service (or snapshot), merged with admin overrides."""
    overrides = _get_overrides(db)

    # Try fetching live config from the pipeline service
    base = (settings.netcup_api_url or "").rstrip("/")
    live_settings = None
    if base:
        headers = {"X-API-Key": settings.podcast_api_key} if settings.podcast_api_key else {}
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{base}/api/config", headers=headers, timeout=8.0)
                resp.raise_for_status()
                payload = resp.json()
            data = payload.get("settings")
            if isinstance(data, dict) and data:
                live_settings = data
        except Exception as e:
            logger.warning("Live pipeline-config read failed (%s); using snapshot", e)

    if live_settings:
        effective = _deep_merge(live_settings, overrides)
        meta = {
            "live": True,
            "read_only": False,
            "source": "tinboker-agents/services/podcast/configs/default.yaml",
            "fetched_from": base,
            "has_overrides": bool(overrides),
        }
    else:
        effective = _deep_merge(PIPELINE_SETTINGS, overrides)
        meta = {**SNAPSHOT_META, "live": False, "stale": True, "has_overrides": bool(overrides)}

    return {
        "meta": meta,
        "settings": effective,
        "overrides": overrides,
        "available_models": AVAILABLE_MODELS,
    }


class PipelineOverridesPayload(BaseModel):
    overrides: dict[str, Any]


@router.put("/pipeline-settings")
async def update_pipeline_settings(
    payload: PipelineOverridesPayload,
    admin: AdminAccess = Depends(get_admin_access),
    db: Session = Depends(get_session),
):
    """Save pipeline config overrides. Takes effect on the next pipeline run."""
    row = db.query(PipelineConfigOverride).filter_by(namespace="default").first()
    if row:
        row.overrides = payload.overrides
        row.updated_by = admin.email
    else:
        row = PipelineConfigOverride(
            namespace="default",
            overrides=payload.overrides,
            updated_by=admin.email,
        )
        db.add(row)
    db.commit()
    db.refresh(row)
    logger.info("Pipeline overrides updated by %s", admin.email)
    return {
        "ok": True,
        "overrides": row.overrides,
        "updated_by": row.updated_by,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }
