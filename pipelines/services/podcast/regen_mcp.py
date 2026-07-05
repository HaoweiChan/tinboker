#!/usr/bin/env python3
"""Launcher for the content-regeneration MCP server (stdio).

Mirrors ``main.py``: putting this file's directory (the podcast service root) on
``sys.path`` so the ``from src...`` imports resolve regardless of the launching
CWD. Registered in the repo-root ``.mcp.json``; run via::

    uv run --directory pipelines --package tinboker-podcast \
        python services/podcast/regen_mcp.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Populate os.environ from Secret Manager (OPENROUTER_API_KEY, GROQ_API_KEY, …)
# before any LLM client is constructed. Without this the inline sector_verifier
# LLM call in derive_sector_exposures fails auth and falls back to keep-all,
# silently disabling sector verification. Mirrors main.py's entry-point bootstrap.
from src.secrets_bootstrap import bootstrap  # noqa: E402

bootstrap()

from src.podcast.regen.mcp_server import main  # noqa: E402

if __name__ == "__main__":
    main()
