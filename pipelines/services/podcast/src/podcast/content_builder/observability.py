"""LangSmith tracing configuration.

Set these environment variables to enable tracing:
    LANGSMITH_API_KEY    — your LangSmith API key
    LANGSMITH_PROJECT    — project name (default: "content-builder")
    LANGCHAIN_TRACING_V2 — set to "true" to enable (auto-set by configure())
"""

from __future__ import annotations

import os


def configure() -> None:
    """Enable LangSmith tracing if an API key is available."""
    if os.getenv("LANGSMITH_API_KEY"):
        os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
        os.environ.setdefault("LANGSMITH_PROJECT", "content-builder")
