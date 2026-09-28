#!/usr/bin/env python3
"""Start the podcast regeneration MCP server from the pipeline uv workspace."""

import sys
from pathlib import Path


def main() -> None:
    service_root = Path(__file__).resolve().parents[2] / "pipelines/services/podcast"
    sys.path.insert(0, str(service_root))

    from src.secrets_bootstrap import bootstrap_regen

    bootstrap_regen()

    from src.podcast.regen.mcp_server import main as serve

    serve()


if __name__ == "__main__":
    main()
