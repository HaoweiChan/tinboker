#!/usr/bin/env python3
"""Find episodes whose summary is a placeholder and rerun summarization on them.

A placeholder summary is what `src/summarize/placeholders.py` writes when summarization
fails. The sentinel text appears as the start of the markdown in GCS (Firestore only
stores the `summary_url`, not the body).

Detection is two-stage:
  1. Firestore filter — episodes with empty `related_tickers` (placeholder summaries
     never have tickers).
  2. GCS verification — fetch the summary markdown and check it starts with one of the
     two known sentinel strings.

Reprocessing reuses the same path the `/api/episodes/rerun-summarize` HTTP endpoint
uses: `python main.py --rerun-from summarize --episode <id>` — serial, to avoid
overwhelming Gemini/Groq rate limits.

Usage:
    uv run python services/podcast/scripts/reprocess_placeholders.py --dry-run
    uv run python services/podcast/scripts/reprocess_placeholders.py --limit 5
    uv run python services/podcast/scripts/reprocess_placeholders.py
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

_SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_SERVICE_ROOT))

from src.service.firestore_service import FirestoreService  # noqa: E402

PLACEHOLDER_PREFIXES = (
    "This is a placeholder summary of the podcast episode",
    "This is a placeholder summary for the podcast episode",
)


def _read_gcs_text(gs_url: str) -> str:
    """Download a gs:// blob as UTF-8. Uses the raw client so we are not
    constrained to a single configured bucket (legacy episodes still live in
    ``podcast-data-web``; new ones in ``graphfolio-articles``)."""
    if not gs_url.startswith("gs://"):
        raise ValueError(f"not a gs:// url: {gs_url}")
    bucket_name, _, blob_path = gs_url[5:].partition("/")
    from google.cloud import storage  # local import: don't pay cost on --help
    return (
        storage.Client()
        .bucket(bucket_name)
        .blob(blob_path)
        .download_as_text(encoding="utf-8")
    )


def find_placeholder_episodes(firestore: FirestoreService) -> list[dict]:
    candidates = [
        ep for ep in firestore.get_all_documents("episodes")
        if not (ep.get("related_tickers") or [])
    ]
    placeholders: list[dict] = []
    for ep in candidates:
        summary_url = ep.get("summary_url")
        if not summary_url:
            continue
        try:
            text = _read_gcs_text(summary_url)
        except Exception as e:
            print(f"  skip {ep.get('id')}: gcs read failed ({e})")
            continue
        head = (text or "")[:500]
        if any(prefix in head for prefix in PLACEHOLDER_PREFIXES):
            placeholders.append(ep)
    return placeholders


async def run_rerun(episode_id: str, project_root: Path) -> int:
    python_exec_path = project_root / ".venv" / "bin" / "python3"
    python_exec = str(python_exec_path) if python_exec_path.exists() else "python3"
    proc = await asyncio.create_subprocess_exec(
        python_exec,
        str(project_root / "main.py"),
        "--rerun-from", "summarize",
        "--episode", episode_id,
        cwd=str(project_root),
    )
    return await proc.wait()


async def _amain() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="list candidates only")
    ap.add_argument("--limit", type=int, help="reprocess at most N episodes")
    args = ap.parse_args()

    firestore = FirestoreService()
    placeholders = find_placeholder_episodes(firestore)
    print(f"Found {len(placeholders)} placeholder episodes")
    for ep in placeholders:
        print(
            f"  {ep.get('id')}  {ep.get('podcast_name')}  "
            f"{ep.get('episode_title')!r}"
        )

    if args.dry_run:
        return 0

    targets = placeholders[: args.limit] if args.limit else placeholders
    failed: list[str] = []
    for i, ep in enumerate(targets, 1):
        ep_id = ep.get("id")
        if not ep_id:
            print(f"[{i}/{len(targets)}] skipping doc with no id")
            continue
        print(f"\n[{i}/{len(targets)}] Reprocessing {ep_id} ...")
        code = await run_rerun(ep_id, _SERVICE_ROOT)
        if code == 0:
            print("  done")
        else:
            print(f"  exit code {code}")
            failed.append(ep_id)

    if failed:
        print(f"\n{len(failed)} failed: {failed}")
        return 1
    return 0


def main() -> int:
    return asyncio.run(_amain())


if __name__ == "__main__":
    sys.exit(main())
