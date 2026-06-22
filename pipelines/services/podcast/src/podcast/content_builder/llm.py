"""LLM configuration and prompt loading utilities.

All roles run on OpenRouter (``OPENROUTER_API_KEY`` required).
Default model: ``deepseek/deepseek-v4-pro`` (via ``openrouter:`` prefix).
Hidden reasoning is disabled for every call so structured-JSON outputs cannot
be truncated mid-array by a reasoning budget (reasoning-capable models like
deepseek-v4-flash ignore the field gracefully).

Per-role models are configured via env vars (``EXTRACTOR_MODEL``, ``WRITER_MODEL``,
``MARP_WRITER_MODEL``, ``TICKER_EXTRACTOR_MODEL``). Prefix any model id with
``openrouter:`` to select it; a bare model name (no prefix) is also passed to
OpenRouter as-is.

Admin overrides from the platform DB (``pipeline_config_overrides`` table) take
precedence over env vars when available. The pipeline reads them once at import time.
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

_DEFAULT_MODEL = "openrouter:deepseek/deepseek-v4-pro"
_OPENROUTER_PREFIX = "openrouter:"
_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


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

_MODEL_MAP: dict[str, str] = {
    "extractor": _LLM_OVERRIDES.get("extractor_model") or os.getenv("EXTRACTOR_MODEL", _DEFAULT_MODEL),
    "writer": _LLM_OVERRIDES.get("writer_model") or os.getenv("WRITER_MODEL", _DEFAULT_MODEL),
    "marp_writer": _LLM_OVERRIDES.get("marp_writer_model") or os.getenv("MARP_WRITER_MODEL", _DEFAULT_MODEL),
    "ticker_extractor": _LLM_OVERRIDES.get("ticker_extractor_model") or os.getenv("TICKER_EXTRACTOR_MODEL", _DEFAULT_MODEL),
    "key_insights_extractor": _LLM_OVERRIDES.get("key_insights_extractor_model") or os.getenv("KEY_INSIGHTS_EXTRACTOR_MODEL", _DEFAULT_MODEL),
    "social_copy_writer": _LLM_OVERRIDES.get("social_copy_writer_model") or os.getenv("SOCIAL_COPY_WRITER_MODEL", _DEFAULT_MODEL),
}

_TEMPERATURE_MAP: dict[str, float] = {
    "extractor": _LLM_OVERRIDES.get("temperatures", {}).get("extractor", 0.1),
    "writer": _LLM_OVERRIDES.get("temperatures", {}).get("writer", 0.4),
    "marp_writer": _LLM_OVERRIDES.get("temperatures", {}).get("marp_writer", 0.4),
    "ticker_extractor": _LLM_OVERRIDES.get("temperatures", {}).get("ticker_extractor", 0.1),
    "key_insights_extractor": _LLM_OVERRIDES.get("temperatures", {}).get("key_insights_extractor", 0.3),
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
}


@lru_cache(maxsize=8)
def load_prompt(name: str) -> dict[str, str]:
    """Load a prompt YAML file and return system/user templates."""
    path = _PROMPTS_DIR / f"{name}.yaml"
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _model_name(role: str) -> str:
    return _MODEL_MAP.get(role, _DEFAULT_MODEL)


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
