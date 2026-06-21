"""Unified secrets bootstrap: Google Secret Manager + dotenv.

Replaces both podcast/src/secrets_bootstrap.py (GSM-based) and
knowledge-graph/utils/config.py (dotenv-based) with a single module.

Usage:
    from shared.secrets import bootstrap
    bootstrap()  # loads GSM secrets + YAML constants + .env fallback
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, Optional

_DEFAULT_PROJECT_ID = "gen-lang-client-0901363254"
_loaded = False


def _load_dotenv(env_path: Optional[Path] = None) -> None:
    """Load .env file without overriding existing vars."""
    from dotenv import load_dotenv
    path = env_path or Path(".env")
    if path.exists():
        load_dotenv(path, override=False)


def _load_yaml_constants(yaml_path: Path) -> None:
    """Push non-secret deployment constants from YAML into os.environ."""
    if not yaml_path.exists():
        return
    import yaml
    with yaml_path.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    gcp = cfg.get("gcp", {})
    mapping = {
        "GCP_PROJECT_ID": gcp.get("project_id"),
        "GCS_BUCKET_NAME": gcp.get("gcs_bucket_name"),
    }
    for key, value in mapping.items():
        if value is not None and not os.environ.get(key):
            os.environ[key] = str(value)


def _load_gsm_secrets(
    names: Iterable[str],
    *,
    project_id: str,
    required: bool = True,
) -> None:
    """Fetch each secret's latest version from GSM and set in os.environ."""
    from google.cloud import secretmanager
    client = secretmanager.SecretManagerServiceClient()
    for name in names:
        if os.environ.get(name):
            continue
        path = f"projects/{project_id}/secrets/{name}/versions/latest"
        try:
            response = client.access_secret_version(name=path)
            os.environ[name] = response.payload.data.decode("utf-8")
        except Exception:
            if required:
                raise


def bootstrap(
    project_id: str = _DEFAULT_PROJECT_ID,
    gsm_vars: tuple[str, ...] = (
        "PODCAST_API_KEY",
        "GROQ_API_KEY",
        "OPENROUTER_API_KEY",
        "FIRESTORE_DATABASE_ID",
        "GCP_CREDENTIALS_JSON",
    ),
    optional_vars: tuple[str, ...] = (
        "SPOTIFY_ID",
        "SPOTIFY_SECRET",
        "LANGSMITH_API_KEY",
        "TAVILY_API_KEY",
        "WIKI_DATABASE_URL",
    ),
    yaml_path: Optional[Path] = None,
    env_path: Optional[Path] = None,
) -> None:
    """Idempotent bootstrap: dotenv -> YAML constants -> GSM secrets."""
    global _loaded
    if _loaded:
        return
    _load_dotenv(env_path)
    if yaml_path:
        _load_yaml_constants(yaml_path)
    _load_gsm_secrets(gsm_vars, project_id=project_id, required=True)
    _load_gsm_secrets(optional_vars, project_id=project_id, required=False)
    _loaded = True


def reset() -> None:
    """Reset loaded state (for testing)."""
    global _loaded
    _loaded = False
