#!/usr/bin/env python3
"""Monthly sector-taxonomy maintenance orchestrator (private, PR-free — M5).

RUNBOOK
-------
Cadence: monthly. Run from an operator machine or a private scheduler (VPS cron /
private Actions runner) — never this public repo's GitHub Actions (G6).

Credentials needed in the environment before running:
  TINBOKER_API_BASE_URL   API origin (e.g. https://dev-api.tinboker.com).
  TINBOKER_ADMIN_TOKEN    Admin JWT, used as the Bearer token by every child script.
  OPENROUTER_API_KEY      Optional — if unset, falls back to
                          `gcloud secrets versions access latest --secret=OPENROUTER_API_KEY
                          --project=gen-lang-client-0901363254` (needs an authed gcloud).
  TAXONOMY_EXPORT_GCS_BUCKET (+ friends) — only needed for the separate export step below.

Exact command sequence this script runs (equivalent manual invocation):
  cd pipelines && uv run --package tinboker-shared python \\
      libs/shared/scripts/audit_sector_universe.py --judge --out /tmp/sector_audit_<ts>.md
  python scripts/fill_sector_reasons.py     # skip-existing; drafts only if new empty work

Nothing here ever publishes. Publishing a fill draft is a separate, explicit,
Willy-reviewed call (G5):
  curl -X POST "$TINBOKER_API_BASE_URL/api/admin/taxonomy/bulk/<draft_id>/publish" \\
      -H "Authorization: Bearer $TINBOKER_ADMIN_TOKEN"

G6 export (weekly, on its own schedule — also run on-demand right after a publish):
  TINBOKER_API_BASE_URL=... TINBOKER_ADMIN_TOKEN=... python scripts/export_taxonomy_snapshot.py

Future item (out of scope here, noted per the fix plan): a FinMind membership-refresh
pass (the old Chain-B industry-refresh job's purpose) returns later as another drafted
bulk pass through POST /api/admin/taxonomy/bulk — same draft→review→publish pattern.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PIPELINES_DIR = REPO_ROOT / "pipelines"
FILL_SCRIPT = REPO_ROOT / "scripts" / "fill_sector_reasons.py"
AUDIT_SCRIPT_REL = "libs/shared/scripts/audit_sector_universe.py"
DRAFT_ID_RE = re.compile(r"^draft_id:\s*(\S+)", re.MULTILINE)


def run_audit(*, judge: bool, only: str | None, out_path: Path) -> None:
    cmd = ["uv", "run", "--package", "tinboker-shared", "python", AUDIT_SCRIPT_REL, "--out", str(out_path)]
    if judge:
        cmd.append("--judge")
    if only:
        cmd.extend(["--only", only])
    subprocess.run(cmd, cwd=str(PIPELINES_DIR), check=True)


def run_fill() -> str:
    result = subprocess.run(
        [sys.executable, str(FILL_SCRIPT)],
        check=True,
        capture_output=True,
        text=True,
    )
    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    return result.stdout


def parse_draft_id(fill_stdout: str) -> str | None:
    match = DRAFT_ID_RE.search(fill_stdout)
    return match.group(1) if match else None


def print_summary(report_path: Path, draft_id: str | None) -> None:
    print("\n" + "=" * 72)
    print("TAXONOMY MAINTENANCE SUMMARY")
    print("=" * 72)
    print(f"report: {report_path}")
    print(f"draft_id: {draft_id}" if draft_id else "draft_id: no draft needed (nothing to fill)")
    print(
        "\nPublishing requires Willy's explicit review + go-ahead (G5). "
        "This script never publishes."
    )
    print(
        "\nG6 export (run after review/publish, or standalone weekly):\n"
        "  TINBOKER_API_BASE_URL=<...> TINBOKER_ADMIN_TOKEN=<...> "
        "python scripts/export_taxonomy_snapshot.py"
    )


def main() -> int:
    args = _parse_args()
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    out_path = report_dir / f"sector_audit_{stamp}.md"

    run_audit(judge=not args.no_judge, only=args.only, out_path=out_path)
    fill_stdout = run_fill()
    draft_id = parse_draft_id(fill_stdout)
    print_summary(out_path, draft_id)
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--report-dir", default="/tmp", help="directory for the audit report (default: /tmp)")
    parser.add_argument("--no-judge", action="store_true", help="skip the --judge LLM pass (mechanical metrics only)")
    parser.add_argument("--only", help="limit the audit's --judge pass to a single exposure_id")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
