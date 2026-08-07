#!/usr/bin/env python3
"""Draft the bootstrap sector taxonomy into Postgres through the admin API.

Usage:
  TINBOKER_API_BASE_URL=https://dev-api.tinboker.com \\
  TINBOKER_ADMIN_TOKEN=<admin JWT from your shell/session> \\
  python scripts/import_taxonomy_to_db.py

Environment:
  TINBOKER_API_BASE_URL  API origin, e.g. https://dev-api.tinboker.com.
  TINBOKER_ADMIN_TOKEN   Admin JWT used as the Bearer token. Do not store it in git.

The script reads backend/src/data/sectors_seed.py, including SECTOR_REDIRECTS, and
POSTs a full taxonomy draft with actor "bot:import". It prints the diff report and
the explicit publish command for operator review. It never auto-publishes.
"""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
from typing import Any

import requests

REPO_ROOT = Path(__file__).resolve().parents[1]
SEED_PATH = REPO_ROOT / "backend/src/data/sectors_seed.py"
TOKEN_ENV = "TINBOKER_ADMIN_TOKEN"
BASE_URL_ENV = "TINBOKER_API_BASE_URL"


def main() -> int:
    base_url = _required_env(BASE_URL_ENV).rstrip("/")
    token = _required_env(TOKEN_ENV)
    seed, redirects = _load_seed()
    payload = {
        "full": True,
        "actor": "bot:import",
        "entry": "Initial Postgres taxonomy import",
        "rationale": "M2.5 truth migration imports the post-M2 bootstrap fixture.",
        "sectors": seed,
        "redirects": redirects,
    }
    response = requests.post(
        f"{base_url}/api/admin/taxonomy/bulk",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
        timeout=60,
    )
    response.raise_for_status()
    draft = response.json()
    print(json.dumps(draft.get("diff", {}), ensure_ascii=False, indent=2))
    draft_id = draft["draft_id"]
    print("\nReview the diff above. To publish explicitly, run:")
    print(
        "curl -X POST "
        f"\"${BASE_URL_ENV}/api/admin/taxonomy/bulk/{draft_id}/publish\" "
        f"-H \"Authorization: Bearer ${TOKEN_ENV}\""
    )
    return 0


def _load_seed() -> tuple[list[dict[str, Any]], dict[str, str]]:
    spec = importlib.util.spec_from_file_location("sectors_seed", SEED_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {SEED_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return (
        list(getattr(module, "SECTORS_SEED")),
        dict(getattr(module, "SECTOR_REDIRECTS", {})),
    )


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise SystemExit(f"Missing required env var: {name}")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
