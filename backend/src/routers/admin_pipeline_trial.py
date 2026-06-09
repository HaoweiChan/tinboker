"""Admin: pipeline prompt viewing/editing + trial runs.

Prompts are loaded from the pipeline's YAML files. Trial runs execute a single
LLM call against a sample episode transcript with an ad-hoc model choice, storing
results for side-by-side comparison.
"""

import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import Column, DateTime, Integer, JSON, String, Text
from sqlalchemy.orm import Session

from src.auth.admin_auth import get_admin_access, AdminAccess
from src.database.postgres import Base, get_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"])

PROMPTS_DIR = Path(__file__).resolve().parents[3] / "pipelines" / "services" / "podcast" / "src" / "podcast" / "content_builder" / "prompts"

PROMPT_NAMES = ["extractor", "writer", "marp_writer", "ticker_extractor", "key_insights_extractor"]


class TrialRun(Base):
    """Persisted trial run results for model comparison."""
    __tablename__ = "pipeline_trial_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String(36), nullable=False, unique=True, index=True)
    model_id = Column(String(100), nullable=False)
    role = Column(String(50), nullable=False)
    episode_id = Column(String(200), nullable=True)
    episode_title = Column(Text, nullable=True)
    input_preview = Column(Text, nullable=True)
    output = Column(JSON, nullable=True)
    elapsed_ms = Column(Integer, nullable=True)
    error = Column(Text, nullable=True)
    created_by = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# --- Prompts endpoints ---

@router.get("/pipeline-prompts")
async def get_pipeline_prompts(admin: AdminAccess = Depends(get_admin_access)):
    """List all pipeline prompts (YAML content)."""
    prompts = {}
    for name in PROMPT_NAMES:
        path = PROMPTS_DIR / f"{name}.yaml"
        if path.exists():
            prompts[name] = path.read_text(encoding="utf-8")
        else:
            prompts[name] = f"# Prompt file not found: {path}"
    return {"prompts": prompts, "prompt_names": PROMPT_NAMES}


class PromptUpdatePayload(BaseModel):
    content: str


@router.put("/pipeline-prompts/{name}")
async def update_pipeline_prompt(
    name: str,
    payload: PromptUpdatePayload,
    admin: AdminAccess = Depends(get_admin_access),
):
    """Save an edited prompt back to the YAML file."""
    if name not in PROMPT_NAMES:
        raise HTTPException(status_code=404, detail=f"Unknown prompt: {name}")
    path = PROMPTS_DIR / f"{name}.yaml"
    if not path.parent.exists():
        raise HTTPException(status_code=500, detail="Prompts directory not found")
    path.write_text(payload.content, encoding="utf-8")
    logger.info("Prompt '%s' updated by %s", name, admin.email)
    return {"ok": True, "name": name}


# --- Trial Run endpoints ---

class TrialRunRequest(BaseModel):
    model_id: str
    role: str = "marp_writer"
    episode_id: Optional[str] = None


@router.post("/pipeline-trial-run")
async def run_trial(
    req: TrialRunRequest,
    admin: AdminAccess = Depends(get_admin_access),
    db: Session = Depends(get_session),
):
    """Execute a single LLM call with the specified model against a sample episode.

    Returns the raw output for preview. Results are persisted for comparison.
    """
    import asyncio

    run_id = str(uuid.uuid4())

    # Load the prompt
    prompt_path = PROMPTS_DIR / f"{req.role}.yaml"
    if not prompt_path.exists():
        raise HTTPException(status_code=404, detail=f"Prompt not found: {req.role}")

    import yaml
    prompt_data = yaml.safe_load(prompt_path.read_text(encoding="utf-8"))

    # Get a sample episode from Firestore
    episode_data = await _get_sample_episode(req.episode_id)
    if not episode_data:
        raise HTTPException(status_code=404, detail="No episode found for trial run")

    # Build the user message from the prompt template
    system_msg = prompt_data.get("system", "")
    user_template = prompt_data.get("user", "")

    # Prepare template vars based on role
    template_vars = _build_template_vars(req.role, episode_data)
    try:
        user_msg = user_template.format(**template_vars)
    except KeyError as e:
        raise HTTPException(status_code=500, detail=f"Template var missing: {e}")

    # Call the LLM with the specified model
    start = time.time()
    try:
        result = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: _invoke_llm(req.model_id, req.role, system_msg, user_msg),
        )
        elapsed_ms = int((time.time() - start) * 1000)
        error = None
    except Exception as exc:
        elapsed_ms = int((time.time() - start) * 1000)
        result = None
        error = str(exc)

    # Persist the trial run
    trial = TrialRun(
        run_id=run_id,
        model_id=req.model_id,
        role=req.role,
        episode_id=episode_data.get("episode_id"),
        episode_title=episode_data.get("episode_title"),
        input_preview=user_msg[:500],
        output=result,
        elapsed_ms=elapsed_ms,
        error=error,
        created_by=admin.email,
    )
    db.add(trial)
    db.commit()

    return {
        "run_id": run_id,
        "model_id": req.model_id,
        "role": req.role,
        "episode_title": episode_data.get("episode_title"),
        "output": result,
        "elapsed_ms": elapsed_ms,
        "error": error,
    }


@router.get("/pipeline-trial-runs")
async def list_trial_runs(
    admin: AdminAccess = Depends(get_admin_access),
    db: Session = Depends(get_session),
    limit: int = Query(default=20, ge=1, le=100),
):
    """List recent trial runs for comparison."""
    runs = (
        db.query(TrialRun)
        .order_by(TrialRun.created_at.desc())
        .limit(limit)
        .all()
    )
    return {
        "runs": [
            {
                "run_id": r.run_id,
                "model_id": r.model_id,
                "role": r.role,
                "episode_id": r.episode_id,
                "episode_title": r.episode_title,
                "elapsed_ms": r.elapsed_ms,
                "error": r.error,
                "output": r.output,
                "created_by": r.created_by,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in runs
        ]
    }


@router.delete("/pipeline-trial-runs/{run_id}")
async def delete_trial_run(
    run_id: str,
    admin: AdminAccess = Depends(get_admin_access),
    db: Session = Depends(get_session),
):
    """Delete a trial run."""
    run = db.query(TrialRun).filter_by(run_id=run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Trial run not found")
    db.delete(run)
    db.commit()
    return {"ok": True, "deleted": run_id}


# --- Helpers ---

async def _get_sample_episode(episode_id: Optional[str] = None) -> Optional[dict[str, Any]]:
    """Fetch a sample episode from Firestore for trial runs."""
    try:
        from google.cloud import firestore
        db_client = firestore.Client(
            project=os.getenv("GCP_PROJECT_ID", "gen-lang-client-0901363254"),
            database=os.getenv("FIRESTORE_DATABASE_ID", "graphfolio-db"),
        )
        if episode_id:
            doc = db_client.collection("episodes").document(episode_id).get()
            if doc.exists:
                data = doc.to_dict()
                data["episode_id"] = doc.id
                return data
        # Get a random recent episode with transcript
        query = (
            db_client.collection("episodes")
            .order_by("created_time", direction=firestore.Query.DESCENDING)
            .limit(10)
        )
        docs = list(query.stream())
        if not docs:
            return None
        # Pick one that has sentences
        import random
        random.shuffle(docs)
        for doc in docs:
            data = doc.to_dict()
            sentences = data.get("sentences") or data.get("transcript_sentences")
            if sentences and len(sentences) > 50:
                data["episode_id"] = doc.id
                return data
        # Fallback: just use the first one
        data = docs[0].to_dict()
        data["episode_id"] = docs[0].id
        return data
    except Exception as exc:
        logger.warning("Failed to fetch sample episode: %s", exc)
        return None


def _build_template_vars(role: str, episode_data: dict[str, Any]) -> dict[str, str]:
    """Build template variables for the prompt based on role."""
    sentences = episode_data.get("sentences") or episode_data.get("transcript_sentences") or []
    source = episode_data.get("podcast_name", "Podcast")
    episode_title = episode_data.get("episode_title", episode_data.get("title", "Episode"))

    if role in ("extractor",):
        return {
            "sentences": json.dumps(sentences[:200], ensure_ascii=False),
            "source": source,
            "episode_title": episode_title,
        }
    elif role in ("writer", "marp_writer", "ticker_extractor"):
        # These expect clustered events — simulate with a simplified structure
        events = []
        chunk_size = max(1, len(sentences) // 5)
        for i in range(0, min(len(sentences), chunk_size * 5), chunk_size):
            chunk = sentences[i:i + chunk_size]
            texts = [s.get("text") or s.get("content", "") for s in chunk]
            combined = " ".join(t for t in texts if t)
            if combined:
                events.append({
                    "section_topic": f"Topic {i // chunk_size + 1}",
                    "start_index": i,
                    "end_index": min(i + chunk_size - 1, len(sentences) - 1),
                    "start": chunk[0].get("start", i * 30000),
                    "text": combined[:2000],
                })
        return {
            "events": json.dumps(events, ensure_ascii=False),
            "source": source,
            "episode_title": episode_title,
        }
    elif role == "key_insights_extractor":
        # Expects a markdown summary — use a placeholder
        return {
            "markdown": episode_data.get("summary_markdown", "（尚無摘要內容）"),
            "source": source,
            "episode_title": episode_title,
        }
    return {"source": source, "episode_title": episode_title}


def _invoke_llm(model_id: str, role: str, system_msg: str, user_msg: str) -> Any:
    """Call the LLM via OpenRouter (OpenAI-compatible) or Google Gemini."""
    import re
    import httpx

    temperature_map = {
        "extractor": 0.1,
        "writer": 0.4,
        "marp_writer": 0.4,
        "ticker_extractor": 0.1,
        "key_insights_extractor": 0.3,
    }
    temperature = temperature_map.get(role, 0.3)

    messages = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_msg},
    ]

    if model_id.startswith("openrouter:"):
        # OpenRouter uses OpenAI-compatible API
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY not set")
        model_name = model_id[len("openrouter:"):]
        resp = httpx.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "HTTP-Referer": "https://tinboker.com",
                "X-Title": "TinBoker trial run",
                "Content-Type": "application/json",
            },
            json={
                "model": model_name,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": 8192,
                "response_format": {"type": "json_object"},
            },
            timeout=120.0,
        )
        resp.raise_for_status()
        data = resp.json()
        raw = data["choices"][0]["message"]["content"]
    else:
        # Google Gemini via generativelanguage API
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY not set")
        resp = httpx.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent",
            params={"key": api_key},
            headers={"Content-Type": "application/json"},
            json={
                "contents": [
                    {"role": "user", "parts": [{"text": f"{system_msg}\n\n{user_msg}"}]}
                ],
                "generationConfig": {
                    "temperature": temperature,
                    "maxOutputTokens": 8192,
                    "responseMimeType": "application/json",
                },
            },
            timeout=120.0,
        )
        resp.raise_for_status()
        data = resp.json()
        raw = data["candidates"][0]["content"]["parts"][0]["text"]

    # Strip markdown fences
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*\n?", "", raw)
        raw = re.sub(r"\n?```\s*$", "", raw)
    return json.loads(raw, strict=False)
