"""LLM configuration and prompt loading utilities.

All roles run on OpenRouter (``OPENROUTER_API_KEY`` required).
Hidden reasoning is disabled for every call so structured-JSON outputs cannot
be truncated mid-array by a reasoning budget (reasoning-capable models like
deepseek-v4-flash ignore the field gracefully).

Model selection is **entirely config-driven — no model name is hardcoded here**,
so switching models is a one-var change with no code edit. For each role the model
id is resolved by this precedence:

  1. DB override  — ``pipeline_config_overrides`` (admin config plane), per role
  2. per-role env — ``EXTRACTOR_MODEL`` / ``WRITER_MODEL`` / ``MARP_WRITER_MODEL`` /
     ``TICKER_EXTRACTOR_MODEL`` / ``KEY_INSIGHTS_EXTRACTOR_MODEL`` / ``SOCIAL_COPY_WRITER_MODEL``
  3. global env   — ``PIPELINE_LLM_MODEL`` (one switch for every role)

If none is set the pipeline fails loud (``_model_name`` raises) rather than
silently picking a model. Prefix any id with ``openrouter:`` to select it; a bare
model name is forwarded to OpenRouter as-is. The DB overrides are read once at
import time.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_PROMPTS_DIR = Path(__file__).parent / "prompts"
_MAX_RETRIES = 2
_log = logging.getLogger(__name__)

_GLOBAL_MODEL_ENV = "PIPELINE_LLM_MODEL"  # one var to switch every role at once
_OPENROUTER_PREFIX = "openrouter:"
_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# role -> the per-role env var that overrides the global PIPELINE_LLM_MODEL.
_ROLE_ENV: dict[str, str] = {
    "extractor": "EXTRACTOR_MODEL",
    "writer": "WRITER_MODEL",
    "marp_writer": "MARP_WRITER_MODEL",
    "ticker_extractor": "TICKER_EXTRACTOR_MODEL",
    "key_insights_extractor": "KEY_INSIGHTS_EXTRACTOR_MODEL",
    "social_copy_writer": "SOCIAL_COPY_WRITER_MODEL",
    "sector_verifier": "SECTOR_VERIFIER_MODEL",
}


def _load_db_overrides() -> dict[str, Any]:
    """Try to load admin overrides from Postgres (best-effort, never blocks)."""
    db_url = os.getenv("PLATFORM_DATABASE_URL") or os.getenv("EPISODE_DATABASE_URL")
    if not db_url:
        return {}
    try:
        import sqlalchemy as sa
        engine = sa.create_engine(db_url, pool_pre_ping=True)
        with engine.connect() as conn:
            row = conn.execute(
                sa.text("SELECT overrides FROM pipeline_config_overrides WHERE namespace = 'default' LIMIT 1")
            ).fetchone()
        engine.dispose()
        if row and row[0]:
            overrides = row[0] if isinstance(row[0], dict) else json.loads(row[0])
            _log.info("Loaded pipeline config overrides from DB: %s", list(overrides.get("llm", {}).keys()))
            return overrides
    except Exception as exc:
        _log.debug("Could not load pipeline overrides from DB: %s", exc)
    return {}


_DB_OVERRIDES = _load_db_overrides()
_LLM_OVERRIDES = _DB_OVERRIDES.get("llm", {})

def _resolve_model(role: str) -> str | None:
    """Resolve a role's model id from config, or None if nothing is configured.

    DB override > per-role env > global ``PIPELINE_LLM_MODEL``. Re-read live (not
    cached) so a var set after import — e.g. by ``secrets_bootstrap`` — is still
    picked up.
    """
    return (
        _LLM_OVERRIDES.get(f"{role}_model")
        or os.getenv(_ROLE_ENV.get(role, ""))
        or os.getenv(_GLOBAL_MODEL_ENV)
        or None
    )

_TEMPERATURE_MAP: dict[str, float] = {
    "extractor": _LLM_OVERRIDES.get("temperatures", {}).get("extractor", 0.1),
    "writer": _LLM_OVERRIDES.get("temperatures", {}).get("writer", 0.4),
    "marp_writer": _LLM_OVERRIDES.get("temperatures", {}).get("marp_writer", 0.4),
    "ticker_extractor": _LLM_OVERRIDES.get("temperatures", {}).get("ticker_extractor", 0.1),
    "key_insights_extractor": _LLM_OVERRIDES.get("temperatures", {}).get("key_insights_extractor", 0.3),
    "sector_verifier": _LLM_OVERRIDES.get("temperatures", {}).get("sector_verifier", 0.1),
}

_MAX_TOKENS_MAP: dict[str, int] = {
    # Long episodes (1000+ sentences) produce a topic list whose JSON exceeded the
    # old 2048 cap — the reply truncated mid-array, failed to parse, and the episode
    # ended up with zero events (no chapters). 8192 covers even very long shows.
    "extractor": 8192,
    "writer": 8192,
    "marp_writer": 16384,
    # Verbose models emit ticker reasons/risks whose JSON, on long & ticker-dense
    # episodes (30-40+ tickers), truncated mid-string at the old 4096 cap
    # ("Unterminated string") — which raised and aborted the WHOLE episode (summary
    # included), so the episode never got generated/backfilled. 16384 fits a large
    # multi-ticker payload; deepseek-v4-pro supports the larger completion.
    "ticker_extractor": 16384,
    "key_insights_extractor": 2048,
    "sector_verifier": 2048,
}


@lru_cache(maxsize=8)
def load_prompt(name: str) -> dict[str, str]:
    """Load a prompt YAML file and return system/user templates."""
    path = _PROMPTS_DIR / f"{name}.yaml"
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _model_name(role: str) -> str:
    model = _resolve_model(role)
    if not model:
        env = _ROLE_ENV.get(role, role.upper() + "_MODEL")
        raise RuntimeError(
            f"No LLM model configured for role '{role}'. Set {_GLOBAL_MODEL_ENV} "
            f"(applies to all roles) or {env} (this role only) — "
            f"e.g. {_GLOBAL_MODEL_ENV}=openrouter:<provider>/<model>."
        )
    return model


def _model_source(role: str) -> str:
    """Which config layer supplied this role's model — for admin visibility into drift.

    Returns the DB override, the per-role env var name, the global var name, or
    "unset", mirroring the precedence in ``_resolve_model``.
    """
    if _LLM_OVERRIDES.get(f"{role}_model"):
        return "db_override"
    if os.getenv(_ROLE_ENV.get(role, "")):
        return _ROLE_ENV[role]
    if os.getenv(_GLOBAL_MODEL_ENV):
        return _GLOBAL_MODEL_ENV
    return "unset"


def effective_llm_config() -> dict[str, Any]:
    """The live, resolved LLM config — the single source of truth for which models
    actually run. Flat ``<role>_model`` keys so it merges with the admin override
    shape; models resolve via ``_resolve_model`` (DB override > per-role env >
    ``PIPELINE_LLM_MODEL``). ``model_sources`` reports where each came from.

    Read-only and secret-free — safe to surface on the admin ``/api/config`` endpoint
    so the Pipeline Settings page reflects reality instead of a static file.
    """
    cfg: dict[str, Any] = {"default_provider": "openrouter"}
    for role in _ROLE_ENV:
        cfg[f"{role}_model"] = _resolve_model(role)
    cfg["temperatures"] = dict(_TEMPERATURE_MAP)
    cfg["token_limits"] = dict(_MAX_TOKENS_MAP)
    cfg["model_sources"] = {role: _model_source(role) for role in _ROLE_ENV}
    cfg["global_model_env"] = _GLOBAL_MODEL_ENV
    cfg["global_model"] = os.getenv(_GLOBAL_MODEL_ENV)
    return cfg


def _is_openrouter(model: str) -> bool:
    return model.startswith(_OPENROUTER_PREFIX)


def get_model(role: str):
    """Get a configured LangChain chat model for a pipeline role.

    Always returns a ``ChatOpenAI`` pointed at OpenRouter. The ``openrouter:``
    prefix is stripped from the model id before sending; bare model ids (no
    prefix) are forwarded to OpenRouter as-is.
    """
    from langchain_openai import ChatOpenAI

    model = _model_name(role)
    temperature = _TEMPERATURE_MAP.get(role, 0.2)
    or_model = model[len(_OPENROUTER_PREFIX):] if _is_openrouter(model) else model

    return ChatOpenAI(
        model=or_model,
        temperature=temperature,
        max_tokens=_MAX_TOKENS_MAP.get(role, 4096),
        base_url=_OPENROUTER_BASE_URL,
        api_key=os.getenv("OPENROUTER_API_KEY"),
        default_headers={
            "HTTP-Referer": os.getenv("OPENROUTER_SITE_URL", "https://tinboker.com"),
            "X-Title": "TinBoker content pipeline",
        },
        # Every role emits structured JSON; disable hidden reasoning so it can't burn
        # the max_tokens budget and truncate the JSON mid-array (reasoning-capable
        # models like deepseek-v4-flash). Non-reasoning models ignore this field.
        extra_body={"reasoning": {"enabled": False}},
    )


def _sanitize_json_text(text: str) -> str:
    """Strip markdown fences that some models wrap JSON in."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
    return text


def _json_kwargs(model: str) -> dict[str, Any]:
    """OpenAI-compatible JSON-mode hint for ``model.invoke``.

    All models now run on OpenRouter, so we always use the OpenAI response_format.
    Models that don't support it ignore it; the retry loop in invoke_json recovers.
    """
    return {"response_format": {"type": "json_object"}}


def invoke_json(role: str, messages: list[dict], schema: dict | None = None) -> dict:
    """Invoke the role's LLM and parse the response as JSON.

    Asks the provider for JSON natively (Gemini ``response_mime_type`` / OpenAI-style
    ``response_format``), strips any markdown fences, and retries up to ``_MAX_RETRIES``
    times on parse failures. ``strict=False`` tolerates stray control characters.
    """
    model_obj = get_model(role)
    model_name = _model_name(role)
    json_kwargs = _json_kwargs(model_name)
    last_err: Exception | None = None

    for attempt in range(_MAX_RETRIES + 1):
        try:
            response = model_obj.invoke(messages, **json_kwargs)
        except Exception as exc:  # noqa: BLE001 — some models reject the JSON-mode kwarg
            if json_kwargs:
                print(f"  ⚠ JSON-mode kwarg rejected ({exc}); retrying without it")
                json_kwargs = {}
                response = model_obj.invoke(messages)
            else:
                raise
        raw = _sanitize_json_text(
            response.content if isinstance(response.content, str) else str(response.content)
        )
        try:
            return json.loads(raw, strict=False)
        except json.JSONDecodeError as exc:
            last_err = exc
            if attempt < _MAX_RETRIES:
                wait = 2 ** attempt
                print(f"  ⚠ JSON parse failed (attempt {attempt + 1}): {exc} — retrying in {wait}s")
                time.sleep(wait)
    raise ValueError(f"LLM JSON output unparseable after {_MAX_RETRIES + 1} attempts: {last_err}")
