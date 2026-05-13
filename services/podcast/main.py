#!/usr/bin/env python3
"""Entry point shim -- delegates to podcast.cli.main()."""

from src.secrets_bootstrap import bootstrap

bootstrap()

from src.podcast.cli import main  # noqa: E402

if __name__ == "__main__":
    main()
