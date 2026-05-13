"""Router for episode processing endpoints."""

import asyncio
from pathlib import Path
from typing import Dict, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Security
from pydantic import BaseModel

from src.auth import verify_api_key
from src.job_tracker import create_job, get_all_jobs, get_job, update_job

router = APIRouter(prefix="/api/episodes", tags=["episodes"])


class EpisodeRerunRequest(BaseModel):
    """Request model for episode rerun."""
    episode_id: str


class EpisodeRerunResponse(BaseModel):
    """Response model for episode rerun."""
    message: str
    episode_id: str
    status: str


class EpisodeRegenerateResponse(BaseModel):
    """Response model for episode regeneration."""
    message: str
    episode_id: str
    podcast_name: str
    status: str


async def run_episode_rerun(episode_id: str, project_root: Path):
    """
    Run the episode rerun command in the background.
    
    Args:
        episode_id: The episode ID to process
        project_root: Root directory of the project
    """
    # Create job entry
    create_job(episode_id)
    
    try:
        # Build the command - use python3 from venv
        python_exec = project_root / ".venv" / "bin" / "python3"
        if not python_exec.exists():
            # Fallback to system python3
            python_exec = "python3"
        else:
            python_exec = str(python_exec)
        
        cmd = [
            python_exec,
            str(project_root / "main.py"),
            "--rerun-from",
            "summarize",
            "--episode",
            episode_id
        ]
        
        # Run the command
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(project_root)
        )
        
        # Update job with process ID
        update_job(episode_id, pid=process.pid)
        
        # Wait for completion and capture output
        stdout, stderr = await process.communicate()
        
        # Decode output
        stdout_text = stdout.decode("utf-8", errors="replace") if stdout else ""
        stderr_text = stderr.decode("utf-8", errors="replace") if stderr else ""
        
        # Store full output in job tracker (no truncation)
        # We'll truncate only when returning via API if needed
        if process.returncode != 0:
            error_msg = stderr_text or "Unknown error"
            update_job(
                episode_id,
                status="failed",
                returncode=process.returncode,
                stdout=stdout_text,  # Store full output
                stderr=stderr_text,  # Store full output
                error=error_msg[:500]
            )
            print(f"Error running episode rerun for {episode_id}: {error_msg}")
        else:
            update_job(
                episode_id,
                status="completed",
                returncode=process.returncode,
                stdout=stdout_text,  # Store full output
                stderr=stderr_text  # Store full output
            )
            print(f"Successfully completed episode rerun for {episode_id}")
            print(f"Output: {stdout_text[:500]}")  # Print first 500 chars
            
    except Exception as e:
        error_msg = str(e)
        update_job(
            episode_id,
            status="failed",
            error=error_msg,
            stderr=error_msg
        )
        print(f"Exception while running episode rerun for {episode_id}: {e}")


@router.post("/rerun-summarize", response_model=EpisodeRerunResponse)
async def rerun_episode_summarize(
    request: EpisodeRerunRequest,
    background_tasks: BackgroundTasks,
    api_key: str = Security(verify_api_key)
):
    """
    Rerun the summarize step for a specific episode.
    
    This endpoint accepts an episode ID and runs the command:
    python main.py --rerun-from summarize --episode <episode_id>
    
    The command runs in the background, and the API returns immediately.
    
    Args:
        request: Request containing episode_id
        background_tasks: FastAPI background tasks
        
    Returns:
        Response indicating the job has been started
    """
    if not request.episode_id or not request.episode_id.strip():
        raise HTTPException(status_code=400, detail="episode_id is required")
    
    # Get project root (assuming this file is in src/routers)
    project_root = Path(__file__).parent.parent.parent
    
    # Add the background task
    background_tasks.add_task(run_episode_rerun, request.episode_id, project_root)
    
    return EpisodeRerunResponse(
        message=f"Episode rerun job started for episode_id: {request.episode_id}",
        episode_id=request.episode_id,
        status="started"
    )


@router.get("/rerun-summarize/{episode_id}", response_model=EpisodeRerunResponse)
async def rerun_episode_summarize_get(
    episode_id: str,
    background_tasks: BackgroundTasks,
    api_key: str = Security(verify_api_key)
):
    """
    Rerun the summarize step for a specific episode (GET endpoint).
    
    This endpoint accepts an episode ID as a path parameter and runs the command:
    python main.py --rerun-from summarize --episode <episode_id>
    
    The command runs in the background, and the API returns immediately.
    
    Args:
        episode_id: The episode ID to process
        background_tasks: FastAPI background tasks
        
    Returns:
        Response indicating the job has been started
    """
    if not episode_id or not episode_id.strip():
        raise HTTPException(status_code=400, detail="episode_id is required")
    
    # Get project root (assuming this file is in src/routers)
    project_root = Path(__file__).parent.parent.parent
    
    # Add the background task
    background_tasks.add_task(run_episode_rerun, episode_id, project_root)
    
    return EpisodeRerunResponse(
        message=f"Episode rerun job started for episode_id: {episode_id}",
        episode_id=episode_id,
        status="started"
    )


@router.get("/health")
async def health_check():
    """Health check endpoint for episodes router."""
    return {"status": "healthy", "service": "episode-processor"}


class JobStatusResponse(BaseModel):
    """Response model for job status."""
    episode_id: str
    status: str  # running, completed, failed
    started_at: Optional[str] = None
    updated_at: Optional[str] = None
    returncode: Optional[int] = None
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    error: Optional[str] = None


@router.get("/status/{episode_id}", response_model=JobStatusResponse)
async def get_episode_status(
    episode_id: str,
    full: bool = Query(False, description="Return full stdout/stderr (default: truncated to last 5000 chars)"),
    api_key: str = Security(verify_api_key)
):
    """
    Get the status of an episode rerun job.
    
    Args:
        episode_id: The episode ID to check
        full: If True, return full stdout/stderr. If False, return last 5000 chars (default: False)
        api_key: API key for authentication
        
    Returns:
        Job status information
    """
    job = get_job(episode_id)
    
    if not job:
        raise HTTPException(
            status_code=404,
            detail=f"No job found for episode_id: {episode_id}"
        )
    
    # Prepare response data
    response_data = job.copy()
    
    # Truncate stdout/stderr if full=False
    if not full:
        if "stdout" in response_data and response_data["stdout"]:
            response_data["stdout"] = response_data["stdout"][-5000:]
        if "stderr" in response_data and response_data["stderr"]:
            response_data["stderr"] = response_data["stderr"][-5000:]
    
    return JobStatusResponse(**response_data)


@router.get("/status", response_model=Dict[str, JobStatusResponse])
async def get_all_episode_statuses(
    api_key: str = Security(verify_api_key)
):
    """
    Get the status of all episode rerun jobs.
    
    Args:
        api_key: API key for authentication
        
    Returns:
        Dictionary of all job statuses
    """
    jobs = get_all_jobs()
    return {episode_id: JobStatusResponse(**job) for episode_id, job in jobs.items()}
