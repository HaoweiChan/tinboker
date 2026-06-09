"""Shared config loading: YAML files + env var overrides."""

import os
from pathlib import Path
from typing import Any

import yaml


def load_yaml_config(config_path: Path) -> dict[str, Any]:
    """Load a YAML config file, returning empty dict if missing."""
    if config_path.exists():
        with config_path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def get_env(key: str, default: str = "") -> str:
    """Read an env var with a default."""
    return os.getenv(key, default)
