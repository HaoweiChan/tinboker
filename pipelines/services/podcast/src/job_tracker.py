"""Job tracking system for episode processing."""

from datetime import datetime
from typing import Dict, Optional

import psutil

# In-memory job storage (in production, use Redis or database)
_jobs: Dict[str, Dict] = {}


def create_job(episode_id: str) -> Dict:
    """Create a new job entry."""
    job = {
        "episode_id": episode_id,
        "status": "running",
        "started_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "pid": None,
        "returncode": None,
        "stdout": "",
        "stderr": "",
        "error": None,
    }
    _jobs[episode_id] = job
    return job


def update_job(episode_id: str, **kwargs) -> None:
    """Update job information."""
    if episode_id in _jobs:
        _jobs[episode_id].update(kwargs)
        _jobs[episode_id]["updated_at"] = datetime.now().isoformat()


def get_job(episode_id: str) -> Optional[Dict]:
    """Get job status."""
    if episode_id not in _jobs:
        return None
    
    job = _jobs[episode_id].copy()
    
    # Check if process is still running
    if job.get("pid") and job["status"] == "running":
        try:
            process = psutil.Process(job["pid"])
            if not process.is_running():
                # Process finished
                job["status"] = "completed" if job.get("returncode") == 0 else "failed"
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            # Process no longer exists
            if job["status"] == "running":
                job["status"] = "completed" if job.get("returncode") == 0 else "failed"
    
    return job


def get_all_jobs() -> Dict[str, Dict]:
    """Get all jobs."""
    # Update status for all running jobs
    for episode_id in list(_jobs.keys()):
        get_job(episode_id)
    return _jobs.copy()
