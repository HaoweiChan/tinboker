"""LLM access for the news pipeline — OpenRouter (OpenAI-compatible API).

``services/news`` depends only on ``tinboker-shared``, so it cannot reuse the
podcast package's ``content_builder/llm.py``. This is the equivalent: a single
JSON chat call routed through OpenRouter, the same provider the podcast pipeline
already uses. The model is config (``NEWS_ENRICH_MODEL``); the default mirrors
the podcast path's Flash-Lite-for-extraction choice.

:func:`call_json` is the one seam the pipeline steps call — tests monkeypatch it
(or pass their own ``llm=`` callable) to run fully offline.
"""

from __future__ import annotations

import json
import os
import re

DEFAULT_MODEL = "google/gemini-2.5-flash-lite"
_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def enrich_model() -> str:
    """The OpenRouter model id for the enrichment call (env-configurable)."""
    return os.getenv("NEWS_ENRICH_MODEL", DEFAULT_MODEL)


def _sanitize_json(text: str) -> str:
    """Strip markdown fences some models wrap JSON in."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
    return text


def call_json(
    system: str,
    user: str,
    *,
    model: str | None = None,
    max_tokens: int = 4096,
) -> dict:
    """One OpenRouter chat completion, parsed as a JSON object.

    Raises ``RuntimeError`` when ``OPENROUTER_API_KEY`` is unset and
    ``ValueError`` when the response is not parseable JSON.
    """
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not set — cannot run news enrichment")

    from openai import OpenAI

    client = OpenAI(base_url=_OPENROUTER_BASE_URL, api_key=api_key)
    response = client.chat.completions.create(
        model=model or enrich_model(),
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.1,
        max_tokens=max_tokens,
        response_format={"type": "json_object"},
        extra_headers={
            "HTTP-Referer": os.getenv("OPENROUTER_SITE_URL", "https://tinboker.com"),
            "X-Title": "TinBoker news pipeline",
        },
    )
    raw = response.choices[0].message.content or "{}"
    parsed = json.loads(_sanitize_json(raw), strict=False)
    if not isinstance(parsed, dict):
        raise ValueError(f"expected a JSON object from the LLM, got {type(parsed).__name__}")
    return parsed
