"""LLM configuration and prompt loading utilities."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

import yaml
from langchain_google_genai import ChatGoogleGenerativeAI


_PROMPTS_DIR = Path(__file__).parent / "prompts"

_MODEL_MAP: dict[str, str] = {
    "extractor": os.getenv("EXTRACTOR_MODEL", "gemini-2.5-flash"),
    "writer": os.getenv("WRITER_MODEL", "gemini-2.5-flash"),
    "marp_writer": os.getenv("MARP_WRITER_MODEL", "gemini-2.5-flash"),
    "ticker_extractor": os.getenv("TICKER_EXTRACTOR_MODEL", "gemini-2.5-flash"),
}

_TEMPERATURE_MAP: dict[str, float] = {
    "extractor": 0.1,
    "writer": 0.4,
    "marp_writer": 0.4,
    "ticker_extractor": 0.1,
}


@lru_cache(maxsize=8)
def load_prompt(name: str) -> dict[str, str]:
    """Load a prompt YAML file and return system/user templates."""
    path = _PROMPTS_DIR / f"{name}.yaml"
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_model(role: str) -> ChatGoogleGenerativeAI:
    """Get a configured LLM instance for a given pipeline role."""
    model_name = _MODEL_MAP.get(role, "gemini-2.5-flash")
    temperature = _TEMPERATURE_MAP.get(role, 0.2)

    return ChatGoogleGenerativeAI(
        model=model_name,
        temperature=temperature,
        google_api_key=os.getenv("GOOGLE_API_KEY"),
    )


def invoke_json(role: str, messages: list[dict], schema: dict | None = None) -> dict:
    """Invoke the LLM and parse the response as JSON.

    Uses Gemini's native JSON mode (response_mime_type) for reliable
    structured output.
    """
    model = get_model(role)
    response = model.invoke(messages, response_mime_type="application/json")
    result = json.loads(response.content)
    return result
