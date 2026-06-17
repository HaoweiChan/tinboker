"""CLI entry point for the podcast processing pipeline."""

import argparse
import sys
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Podcast processing pipeline: download, transcribe, summarize, and upload to Firebase"
    )
    parser.add_argument(
        "--config", type=str, default="podcasts_tw.json",
        help="Path to podcasts configuration JSON file (default: podcasts_tw.json)",
    )
    parser.add_argument(
        "--rerun-from", type=str, default=None,
        choices=["download", "transcribe", "summarize", "upload", "validate", "spotify-metadata"],
        help=(
            "Rerun pipeline from a specific step. Default: None (full pipeline). "
            "Use 'spotify-metadata' to refresh only the Spotify fields on an existing "
            "Firestore episode (no MP3 / transcript / summary work)."
        ),
    )
    parser.add_argument(
        "--transcript-service", type=str, default="groq", dest="transcript_service",
        choices=["whisper", "openai", "groq"],
        help="Speech-to-text service. Default: groq",
    )
    parser.add_argument(
        "--file-mode", action="store_true",
        help="Use file-based mode instead of streaming mode",
    )
    parser.add_argument(
        "--episode", type=str, default=None,
        help="Process episode(s) from Firestore by ID, or 'all'.",
    )
    parser.add_argument(
        "--fill-limit", action="store_true",
        help="Skip processed episodes; process exactly 'limit' non-processed ones",
    )
    parser.add_argument(
        "--show", action="append", default=None, dest="shows", metavar="NAME",
        help=(
            "Only process the show(s) with these exact names (repeatable). "
            "Default: every active show. Useful for ad-hoc single-show ingestion."
        ),
    )
    return parser


def main():
    from src.secrets_bootstrap import bootstrap
    bootstrap()

    from src.podcast.orchestrator import run_pipeline

    parser = build_parser()
    args = parser.parse_args()

    try:
        run_pipeline(
            config_file=Path(args.config),
            rerun_from=args.rerun_from,
            transcript_service=args.transcript_service,
            use_file_mode=args.file_mode,
            reuse_existing_transcript=False,
            episode_id=args.episode,
            fill_limit=args.fill_limit,
            only_shows=args.shows,
        )
    except KeyboardInterrupt:
        print("\n\nPipeline interrupted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
