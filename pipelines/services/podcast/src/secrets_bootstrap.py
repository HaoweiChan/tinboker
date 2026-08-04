"""Populate os.environ for the podcast service. Call `bootstrap()` once at
process start (entry points) — it is idempotent.

Resolution order (P6 — GCP decommission): env var → env file → Google Secret
Manager fallback. The resolver itself lives in ``shared.secrets``; this module
only owns the podcast service's variable lists and its configs/default.yaml.

On the VPS the values come from ``/root/tinboker/pipelines/.env``, which the
systemd units inject via ``EnvironmentFile=-``. See ``shared/secrets.py`` for
the file format and for how to retire the GSM fallback.
"""

from __future__ import annotations

import os
from pathlib import Path

from shared.secrets import bootstrap as _bootstrap

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


def bootstrap() -> None:
    """Idempotent: load env file, yaml constants, then GSM for anything missing."""
    _bootstrap(
        project_id=_PROJECT_ID,
        gsm_vars=_GSM_VARS,
        optional_vars=_GSM_OPTIONAL,
        yaml_path=_YAML_PATH,
    )


if __name__ == "__main__":
    bootstrap()
    print("Bootstrapped. Loaded keys (masked):")
    for k in (*_GSM_VARS, *_GSM_OPTIONAL, "GCP_PROJECT_ID", "GCS_BUCKET_NAME"):
        v = os.environ.get(k, "")
        if v:
            print(f"  {k:24s} prefix={v[:7]}... len={len(v)}")
        else:
            print(f"  {k:24s} <missing>")
