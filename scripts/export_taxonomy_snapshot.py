#!/usr/bin/env python3
"""Export a private taxonomy snapshot for G6 backup/restore.

Intended schedule: weekly from a PRIVATE context (VPS cron or private runner), plus
on-demand immediately before and after bulk taxonomy publishes. Do not add a public
GitHub Actions workflow for this job.

Usage:
  TINBOKER_API_BASE_URL=https://dev-api.tinboker.com \\
  TINBOKER_ADMIN_TOKEN=<admin JWT from your shell/session> \\
  python scripts/export_taxonomy_snapshot.py

Environment:
  TINBOKER_API_BASE_URL            API origin.
  TINBOKER_ADMIN_TOKEN             Admin JWT used as the Bearer token.
  TAXONOMY_EXPORT_PATH             Optional local output path. Defaults to /tmp.
  TAXONOMY_EXPORT_AUDIT_LIMIT      Optional audit rows to include. Default: 5000.
  TAXONOMY_EXPORT_GCS_BUCKET       Optional private GCS bucket for upload.
  TAXONOMY_EXPORT_GCS_PREFIX       Optional object prefix. Default: taxonomy-snapshots.
  TAXONOMY_EXPORT_CONFIRMED_PRIVATE Set to 1 if bucket privacy was manually verified.

No token values belong in this repo, docs, commit messages, or transcripts.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests

TOKEN_ENV = "TINBOKER_ADMIN_TOKEN"
BASE_URL_ENV = "TINBOKER_API_BASE_URL"


def main() -> int:
    base_url = _required_env(BASE_URL_ENV).rstrip("/")
    token = _required_env(TOKEN_ENV)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    output = Path(os.getenv("TAXONOMY_EXPORT_PATH") or f"/tmp/taxonomy-snapshot-{stamp}.json")
    audit_limit = int(os.getenv("TAXONOMY_EXPORT_AUDIT_LIMIT", "5000"))

    headers = {"Authorization": f"Bearer {token}"}
    snapshot = _get_json(f"{base_url}/api/admin/taxonomy/snapshot", headers)
    audit = _get_json(f"{base_url}/api/admin/taxonomy/audit?limit={audit_limit}", headers)
    payload: dict[str, Any] = {
        "exported_at": datetime.now(UTC).isoformat(),
        "api_base_url": base_url,
        "taxonomy": snapshot,
        "audit": audit.get("items", []),
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote local snapshot: {output}")

    bucket = os.getenv("TAXONOMY_EXPORT_GCS_BUCKET")
    if bucket:
        prefix = os.getenv("TAXONOMY_EXPORT_GCS_PREFIX", "taxonomy-snapshots").strip("/")
        object_name = f"{prefix}/{output.name}" if prefix else output.name
        _upload_to_gcs(output, bucket, object_name)
        print(f"Uploaded private snapshot: gs://{bucket}/{object_name}")
    return 0


def _get_json(url: str, headers: dict[str, str]) -> dict[str, Any]:
    response = requests.get(url, headers=headers, timeout=60)
    response.raise_for_status()
    return response.json()


def _upload_to_gcs(path: Path, bucket_name: str, object_name: str) -> None:
    from google.cloud import storage

    client = storage.Client()
    bucket = client.bucket(bucket_name)
    bucket.reload()
    pap = getattr(bucket.iam_configuration, "public_access_prevention", None)
    confirmed = os.getenv("TAXONOMY_EXPORT_CONFIRMED_PRIVATE") == "1"
    if pap != "enforced" and not confirmed:
        raise SystemExit(
            "Refusing GCS upload until bucket privacy is confirmed. "
            "Set TAXONOMY_EXPORT_CONFIRMED_PRIVATE=1 after operator verification."
        )
    blob = bucket.blob(object_name)
    blob.upload_from_filename(str(path), content_type="application/json")


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise SystemExit(f"Missing required env var: {name}")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
