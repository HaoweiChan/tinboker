"""Secret resolution for the pipelines tier: env var → env file → GSM fallback.

P6 (GCP decommission). Secrets now live in:
  - an env file on the VPS — ``/root/tinboker/pipelines/.env``, injected by the
    systemd units via ``EnvironmentFile=-/root/tinboker/pipelines/.env``;
  - GitHub Actions repo secrets for anything CI/CD needs.

Google Secret Manager is retained ONLY as a last-resort fallback so a deploy
still works before the operator has migrated a value. Every resolution logs its
source by NAME (never the value); once ``source=gsm`` stops appearing in
``journalctl -u podcast-api``, delete ``_gsm_client`` / ``_load_from_gsm`` and
the ``google-cloud-secret-manager`` dependency.

Env file format — one ``KEY=value`` per line, ``#`` comments, no ``export``:

    OPENROUTER_API_KEY=<value>
    WIKI_DATABASE_URL=<value>

Usage:
    from shared.secrets import bootstrap
    bootstrap()
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Iterable, Optional

logger = logging.getLogger(__name__)

_DEFAULT_PROJECT_ID = "gen-lang-client-0901363254"

# Searched in order when no explicit env_path is given. cwd is the service dir
# (e.g. services/podcast) under systemd/run_*.sh, so the pipelines-root .env —
# the one the systemd units point EnvironmentFile at — must be reachable too.
_ENV_FILE_CANDIDATES: tuple[Path, ...] = (
    Path(".env"),
    Path("../../.env"),
)

_loaded = False


def _load_env_files(env_path: Optional[Path] = None) -> None:
    """Load env file(s) into os.environ without overriding what is already set."""
    from dotenv import load_dotenv

    for path in (env_path,) if env_path else _ENV_FILE_CANDIDATES:
        if path.exists():
            load_dotenv(path, override=False)
            logger.info("secrets: loaded env file %s", path)


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


def _gsm_client():  # pragma: no cover - exercised only on the legacy fallback path
    """Construct the Secret Manager client. Patched out in tests to prove that a
    fully-populated environment never reaches GSM."""
    from google.cloud import secretmanager
    return secretmanager.SecretManagerServiceClient()


def _load_from_gsm(names: list[str], *, project_id: str, required: bool) -> None:
    client = _gsm_client()
    for name in names:
        path = f"projects/{project_id}/secrets/{name}/versions/latest"
        try:
            response = client.access_secret_version(name=path)
            os.environ[name] = response.payload.data.decode("utf-8")
            logger.warning("secrets: %s source=gsm (migrate it to the env file)", name)
        except Exception:
            if required:
                raise
            logger.info("secrets: %s unresolved (optional)", name)


def _resolve(
    names: Iterable[str],
    *,
    project_id: str,
    from_file: set[str],
    required: bool,
) -> None:
    """env var → env file → GSM. The GSM client is built only if something is
    still missing after the first two."""
    missing: list[str] = []
    for name in names:
        if os.environ.get(name):
            logger.info(
                "secrets: %s source=%s", name, "env-file" if name in from_file else "env"
            )
        else:
            missing.append(name)
    if missing:
        _load_from_gsm(missing, project_id=project_id, required=required)


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
    """Idempotent bootstrap: env file → YAML constants → GSM fallback."""
    global _loaded
    if _loaded:
        return
    before = set(os.environ)
    _load_env_files(env_path)
    from_file = set(os.environ) - before
    if yaml_path:
        _load_yaml_constants(yaml_path)
    _resolve(gsm_vars, project_id=project_id, from_file=from_file, required=True)
    _resolve(optional_vars, project_id=project_id, from_file=from_file, required=False)
    _loaded = True


def reset() -> None:
    """Reset loaded state (for testing)."""
    global _loaded
    _loaded = False
