"""Thin GCS client factory and basic helpers.

Domain-specific upload logic stays in each service; this module provides
the connection setup and primitive operations shared by both.
"""

import json
import os
from pathlib import Path
from typing import Optional

from google.cloud import storage
from google.oauth2 import service_account


def create_gcs_client(
    project_id: Optional[str] = None,
    credentials_json: Optional[str] = None,
    credentials_path: Optional[str] = None,
) -> storage.Client:
    """Create a GCS client from env vars or explicit args.

    Resolution order for each param:
      explicit arg -> GCS_* env var -> GCP_* env var -> ADC fallback
    """
    project_id = project_id or os.getenv("GCS_PROJECT_ID") or os.getenv("GCP_PROJECT_ID")
    creds_json = credentials_json or os.getenv("GCS_CREDENTIALS_JSON") or os.getenv("GCP_CREDENTIALS_JSON")
    creds_path = credentials_path or os.getenv("GCS_CREDENTIALS_PATH") or os.getenv("GCP_CREDENTIALS_PATH")

    credentials = None
    if creds_json:
        creds_dict = json.loads(creds_json) if isinstance(creds_json, str) else creds_json
        credentials = service_account.Credentials.from_service_account_info(creds_dict)
        project_id = project_id or creds_dict.get("project_id")
    elif creds_path:
        cred_path = Path(creds_path).expanduser().resolve()
        credentials = service_account.Credentials.from_service_account_file(str(cred_path))
        with cred_path.open() as f:
            project_id = project_id or json.load(f).get("project_id")

    if credentials and project_id:
        return storage.Client(credentials=credentials, project=project_id)
    return storage.Client(project=project_id)


def get_bucket(
    bucket_name: Optional[str] = None,
    client: Optional[storage.Client] = None,
) -> storage.Bucket:
    """Get a bucket handle, creating a client if needed."""
    name = bucket_name or os.getenv("GCS_BUCKET_NAME", "graphfolio-articles")
    c = client or create_gcs_client()
    return c.bucket(name)
