"""Populate os.environ from Google Secret Manager + configs/default.yaml.

Replaces the old `.env` + `python-dotenv` flow. Call `bootstrap()` once at
process start (entry points) — it is idempotent.

Auth: uses Application Default Credentials.
  - Local dev:  `gcloud auth application-default login`
  - VPS / CI:   `GOOGLE_APPLICATION_CREDENTIALS=/path/to/sa.json`
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

_PROJECT_ID = "gen-lang-client-0901363254"

_GSM_VARS: tuple[str, ...] = (
    "PODCAST_API_KEY",
    "GROQ_API_KEY",
    "OPENROUTER_API_KEY",
    "FIRESTORE_DATABASE_ID",
    "GCP_CREDENTIALS_JSON",
)

_GSM_OPTIONAL: tuple[str, ...] = (
    "SPOTIFY_ID",
    "SPOTIFY_SECRET",
    "LANGSMITH_API_KEY",
    # Postgres connection string for the knowledge wiki (lives on the VPS).
    # Optional: if absent, wiki ingest is a no-op (best-effort step).
    "WIKI_DATABASE_URL",
    # Postgres connection string for the episode catalog mirror (podcast_db on the VPS).
    # Optional: if absent, the Postgres-episode step is a no-op (best-effort).
    "EPISODE_DATABASE_URL",
)

_YAML_PATH = Path(__file__).resolve().parent.parent / "configs" / "default.yaml"

_loaded = False


def _load_yaml_constants() -> None:
    """Push non-secret deployment constants from default.yaml into os.environ."""
    import yaml  # local import: only needed at bootstrap time

    with _YAML_PATH.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    gcp = cfg.get("gcp", {})
    mapping = {
        "GCP_PROJECT_ID": gcp.get("project_id"),
        "GCS_BUCKET_NAME": gcp.get("gcs_bucket_name"),
    }
    for key, value in mapping.items():
        if value is not None and not os.environ.get(key):
            os.environ[key] = str(value)


def _load_gsm_secrets(names: Iterable[str], *, required: bool = True) -> None:
    """Fetch each secret's latest version and push into os.environ."""
    missing = [n for n in names if not os.environ.get(n)]
    if not missing:
        return

    from google.cloud import secretmanager

    client = secretmanager.SecretManagerServiceClient()
    for name in missing:
        path = f"projects/{_PROJECT_ID}/secrets/{name}/versions/latest"
        try:
            response = client.access_secret_version(name=path)
            os.environ[name] = response.payload.data.decode("utf-8")
        except Exception:
            if required:
                raise
            # Optional secrets silently skipped if missing in GSM.


def bootstrap() -> None:
    """Idempotent: load yaml constants and GSM secrets into os.environ."""
    global _loaded
    if _loaded:
        return
    _load_yaml_constants()
    _load_gsm_secrets(_GSM_VARS, required=True)
    _load_gsm_secrets(_GSM_OPTIONAL, required=False)
    _loaded = True


if __name__ == "__main__":
    bootstrap()
    print("Bootstrapped from GSM. Loaded keys (masked):")
    for k in (*_GSM_VARS, *_GSM_OPTIONAL, "GCP_PROJECT_ID", "GCS_BUCKET_NAME"):
        v = os.environ.get(k, "")
        if v:
            print(f"  {k:24s} prefix={v[:7]}... len={len(v)}")
        else:
            print(f"  {k:24s} <missing>")
