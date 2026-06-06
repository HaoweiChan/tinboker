"""Batch CLI for the news ingest pipeline — ``tinboker-news`` / ``python -m news``.

This is what ``run_news.sh`` (the systemd timer's oneshot) invokes. It bootstraps
the secrets the pipeline needs (``WIKI_DATABASE_URL``, ``OPENROUTER_API_KEY``)
then runs the pipeline once.
"""

from __future__ import annotations

import argparse
import sys


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="tinboker-news",
        description="Ingest financial-news RSS feeds into the shared wiki.",
    )
    parser.add_argument(
        "--feeds", default=None, help="path to feeds.json (default: services/news/feeds.json)"
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="cap the number of articles processed"
    )
    parser.add_argument(
        "--no-bootstrap",
        action="store_true",
        help="skip the secrets bootstrap (WIKI_DATABASE_URL / OPENROUTER_API_KEY already in env)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])

    if not args.no_bootstrap:
        from shared.secrets import bootstrap

        bootstrap(gsm_vars=(), optional_vars=("WIKI_DATABASE_URL", "OPENROUTER_API_KEY"))

    # Imported after bootstrap so get_repository() sees WIKI_DATABASE_URL.
    from .orchestrator import run

    summary = run(feeds_path=args.feeds, limit=args.limit)
    return 0 if summary.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
