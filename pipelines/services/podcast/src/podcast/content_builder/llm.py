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
silently picking a model. The DB overrides are read once at import time.

The model id's prefix picks where the call goes:

  ``openrouter:<provider>/<model>``  OpenRouter chat/completions (a bare id, with no
                                     prefix at all, is forwarded to OpenRouter as-is)
  ``local:<model>``                  an OpenAI-compatible server we host — ollama on the
                                     Mac mini — at ``LOCAL_LLM_BASE_URL``
  ``decisions:<provider>/<model>``   OpenRouter's decisions endpoint (TypeSafe Jev): a
                                     typed choice + calibrated probability, never text.
                                     Refused by ``get_model``; callers branch on
                                     ``is_decisions_model()`` and use ``decide()``.

``OPENROUTER_PROVIDER_ORDER`` (comma-separated, cheapest first) pins which providers may
serve an OpenRouter call, with fallbacks left on. It is a price control, not a routing
requirement — see ``_provider_preference``.
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

# ``local:<model>`` routes the role at an OpenAI-compatible server we host instead of
# OpenRouter — ollama on the Mac mini (``/v1``), reached over a tunnel. The base URL is
# env-driven for the same reason model ids are: switching hosts must not need a code edit.
_LOCAL_PREFIX = "local:"
_LOCAL_BASE_URL_ENV = "LOCAL_LLM_BASE_URL"

# ``decisions:<model>`` routes the role at OpenRouter's decisions endpoint (TypeSafe Jev
# and friends). These models return a typed choice + calibrated probability instead of
# text, so they are NOT chat/completions — see ``decide()``. Measured 2026-09-19: the
# roles whose whole answer is a verdict were ~10% of pipeline spend, and a verdict costs
# ~97% less here ($0.042/M in, output free) than the same call on deepseek-v4-pro.
_DECISIONS_PREFIX = "decisions:"
_DECISIONS_URL = "https://openrouter.ai/api/alpha/decisions"

# OpenRouter spreads one model across many providers and does NOT sort them by price.
# Measured 2026-09-19 on deepseek-v4-pro: 16 providers, a 3.7x spread in posted input
# price (StreamLake $0.513/M fp8 .. Azure $1.910/M) and 8x in what we actually paid,
# because prompt-cache hits land per-provider and the cheap ones were also serving them.
# The expensive tail buys nothing — AtlasCloud/BaseTen are fp4 (lower precision) at 3.3x
# StreamLake's fp8 price, and StreamLake matched Azure on throughput. Comma-separated
# allow-list, cheapest first; unset = OpenRouter's default routing.
_PROVIDER_ORDER_ENV = "OPENROUTER_PROVIDER_ORDER"

# role -> the per-role env var that overrides the global PIPELINE_LLM_MODEL.
_ROLE_ENV: dict[str, str] = {
    "extractor": "EXTRACTOR_MODEL",
    "writer": "WRITER_MODEL",
    "marp_writer": "MARP_WRITER_MODEL",
    "ticker_extractor": "TICKER_EXTRACTOR_MODEL",
    "key_insights_extractor": "KEY_INSIGHTS_EXTRACTOR_MODEL",
    "social_copy_writer": "SOCIAL_COPY_WRITER_MODEL",
    "sector_verifier": "SECTOR_VERIFIER_MODEL",
    "macro_extractor": "MACRO_EXTRACTOR_MODEL",
    "name_normalizer": "NAME_NORMALIZER_MODEL",
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
    "macro_extractor": _LLM_OVERRIDES.get("temperatures", {}).get("macro_extractor", 0.1),
}

_MAX_TOKENS_MAP: dict[str, int] = {
    # Long episodes (1000+ sentences) produce a topic list whose JSON exceeded the
    # old 2048 cap — the reply truncated mid-array, failed to parse, and the episode
    # ended up with zero events (no chapters). 8192 then covered every show, until the
    # role was pinned to deepseek-v4-flash-0731: it segments far more finely than
    # v4-pro did (55 events vs 23 on the same 800-sentence chunk), so the same
    # transcript yields a much longer array and the cap came back into reach. The first
    # ingest run after that pin logged two `completion_tokens=8192 … length limit was
    # reached`, and the parse error that followed pointed at char 23992 — a reply cut
    # off exactly at the ceiling, not a malformed one. Raised to match the two roles
    # that already needed the headroom; on flash, completion is $0.10/M, so the extra
    # room costs essentially nothing even when it is used.
    "extractor": 16384,
    "writer": 8192,
    "marp_writer": 16384,
    # Verbose models emit ticker reasons/risks whose JSON, on long & ticker-dense
    # episodes (30-40+ tickers), truncated mid-string at the old 4096 cap
    # ("Unterminated string") — which raised and aborted the WHOLE episode (summary
    # included), so the episode never got generated/backfilled. 16384 fits a large
    # multi-ticker payload; deepseek-v4-pro supports the larger completion.
    "ticker_extractor": 16384,
    "key_insights_extractor": 2048,
    "sector_verifier": 8192,
    # A macro-heavy morning show yields ~10 claims with reasons and a verbatim quote
    # each; 4096 (the default) is the cap that truncated ticker JSON mid-string.
    "macro_extractor": 8192,
}


@lru_cache(maxsize=16)   # one entry per prompt yaml; keep ahead of the file count
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


def _is_local(model: str) -> bool:
    return model.startswith(_LOCAL_PREFIX)


def is_decisions_model(role: str) -> bool:
    """True when ``role`` is configured for a decisions model (``decisions:`` prefix).

    Callers that have a decisions-shaped question branch on this and use ``decide()``;
    everything else keeps the chat/completions path unchanged.

    An unconfigured role answers False rather than raising: this is a routing question,
    and the "no model configured" error belongs to whichever path actually makes the
    call — raising here turned a missing env var into a silent verifier outage, which
    the caller's fallback then read as "drop every ticker-derived candidate".
    """
    return (_resolve_model(role) or "").startswith(_DECISIONS_PREFIX)


def _provider_preference() -> dict[str, Any] | None:
    """OpenRouter provider allow-list from ``OPENROUTER_PROVIDER_ORDER``, or None.

    ``allow_fallbacks`` stays on: pinning is a price preference, not a hard requirement,
    and a pin that can 503 the whole ingest is a worse bug than an expensive call.
    """
    order = [p.strip() for p in os.getenv(_PROVIDER_ORDER_ENV, "").split(",") if p.strip()]
    return {"order": order, "allow_fallbacks": True} if order else None


def get_model(role: str, *, disable_reasoning: bool = True):
    """Get a configured LangChain chat model for a pipeline role.

    Always returns a ``ChatOpenAI`` pointed at OpenRouter. The ``openrouter:``
    prefix is stripped from the model id before sending; bare model ids (no
    prefix) are forwarded to OpenRouter as-is.

    ``disable_reasoning=False`` is the fallback for endpoints that refuse to run
    without reasoning — see the retry in ``invoke_json``.
    """
    from langchain_openai import ChatOpenAI

    model = _model_name(role)
    temperature = _TEMPERATURE_MAP.get(role, 0.2)
    max_tokens = _MAX_TOKENS_MAP.get(role, 4096)

    if _is_local(model):
        # Self-hosted OpenAI-compatible server (ollama et al.). No OpenRouter-only fields:
        # `provider` and `reasoning` are meaningless there, and the api_key is a required
        # placeholder the server ignores.
        base_url = os.getenv(_LOCAL_BASE_URL_ENV)
        if not base_url:
            raise RuntimeError(
                f"{role} is configured for a local model ({model}) but "
                f"{_LOCAL_BASE_URL_ENV} is not set — e.g. {_LOCAL_BASE_URL_ENV}=http://mac-mini:11434/v1"
            )
        return ChatOpenAI(
            model=model[len(_LOCAL_PREFIX):],
            temperature=temperature,
            max_tokens=max_tokens,
            base_url=base_url,
            api_key=os.getenv("LOCAL_LLM_API_KEY", "not-needed"),
        )

    if model.startswith(_DECISIONS_PREFIX):
        raise RuntimeError(
            f"{role} is configured for a decisions model ({model}), which cannot be used "
            "with chat/completions — the caller must branch on is_decisions_model() and "
            "use decide() instead."
        )

    or_model = model[len(_OPENROUTER_PREFIX):] if _is_openrouter(model) else model

    extra_body: dict[str, Any] = {}
    if disable_reasoning:
        # Every role emits structured JSON; disable hidden reasoning so it can't burn
        # the max_tokens budget and truncate the JSON mid-array (reasoning-capable
        # models like deepseek-v4-flash). Non-reasoning models ignore this field.
        extra_body = {"reasoning": {"enabled": False}}
    else:
        # Reasoning tokens come out of the same completion budget, so a forced-reasoning
        # endpoint needs headroom or the JSON truncates mid-array — the exact failure
        # disabling it was meant to prevent.
        max_tokens *= 2

    provider = _provider_preference()
    if provider:
        extra_body["provider"] = provider

    return ChatOpenAI(
        model=or_model,
        temperature=temperature,
        max_tokens=max_tokens,
        base_url=_OPENROUTER_BASE_URL,
        api_key=os.getenv("OPENROUTER_API_KEY"),
        default_headers={
            "HTTP-Referer": os.getenv("OPENROUTER_SITE_URL", "https://tinboker.com"),
            "X-Title": "TinBoker content pipeline",
        },
        extra_body=extra_body,
    )


# OpenRouter's wording when an endpoint refuses ``reasoning.enabled=false``
# (deepseek-v4-pro started returning this, which stalled every summary).
_REASONING_MANDATORY_RE = re.compile(r"reasoning is mandatory", re.IGNORECASE)


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
    reasoning_disabled = True
    last_err: Exception | None = None

    for attempt in range(_MAX_RETRIES + 1):
        try:
            response = model_obj.invoke(messages, **json_kwargs)
        except Exception as exc:  # noqa: BLE001 — some models reject our request shape
            if reasoning_disabled and _REASONING_MANDATORY_RE.search(str(exc)):
                # The reasoning switch lives on the client, not in the call kwargs, so
                # dropping json_kwargs below can never clear it — the retry just hit the
                # same 400 and every episode fell back to the placeholder summarizer.
                # Rebuild the client with reasoning allowed instead.
                print("  ⚠ endpoint mandates reasoning; rebuilding the client with it enabled")
                reasoning_disabled = False
                model_obj = get_model(role, disable_reasoning=False)
                last_err = exc
                continue
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


def decide(role: str, state: Any, questions: dict[str, dict[str, Any]], *, timeout: int = 60) -> dict[str, Any]:
    """Ask the role's decisions model typed questions about ``state``.

    Decisions models (``decisions:typesafe/jev-1.13``) return a typed answer plus a
    calibrated probability rather than text, so they are refused by chat/completions and
    go to a separate endpoint. ``state`` may be a string or any JSON-serializable object;
    ``questions`` is the TypeSafe question map, e.g.::

        {"is_relevant": {"type": "noul", "instructions": "Is the sector really discussed?"}}
        {"segment_type": {"type": "choice", "instructions": "...", "criteria": {...}}}

    Returns the ``answers`` map: ``{"is_relevant": {"type": "noul", "noul": 0.82}}`` /
    ``{"segment_type": {"choice": "analysis", "probabilities": {...}, "confidence": 0.9}}``.
    Raises on transport or API errors — callers that must not fail closed catch and fall
    back to their previous path.
    """
    import requests

    model = _model_name(role)
    if not model.startswith(_DECISIONS_PREFIX):
        raise ValueError(f"{role} is not configured for a decisions model (got {model!r})")
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not set — the decisions endpoint needs it")

    payload = {
        "model": model[len(_DECISIONS_PREFIX):],
        "state": state if isinstance(state, str) else json.dumps(state, ensure_ascii=False),
        "questions": questions,
    }
    last_err: Exception | None = None
    for attempt in range(_MAX_RETRIES + 1):
        try:
            resp = requests.post(
                _DECISIONS_URL,
                json=payload,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                timeout=timeout,
            )
            if resp.status_code >= 400:
                # The body carries the real reason (bad question shape, context overflow);
                # a bare status code has sent us chasing the wrong thing before.
                raise RuntimeError(f"decisions endpoint {resp.status_code}: {resp.text[:300]}")
            answers = resp.json().get("answers")
            if not isinstance(answers, dict):
                raise ValueError(f"decisions reply has no answers map: {resp.text[:200]}")
            return answers
        except Exception as exc:  # noqa: BLE001 — retry transport + transient 5xx alike
            last_err = exc
            if attempt < _MAX_RETRIES:
                wait = 2 ** attempt
                _log.warning("decide(%s) failed (attempt %d): %s — retrying in %ds", role, attempt + 1, exc, wait)
                time.sleep(wait)
    raise RuntimeError(f"decisions call failed after {_MAX_RETRIES + 1} attempts: {last_err}")
