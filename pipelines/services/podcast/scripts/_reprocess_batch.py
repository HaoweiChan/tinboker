"""Batch-reprocess a fixed list of episode IDs whose summaries are placeholders/empty.

Runs `main.py --rerun-from summarize --episode <id>` serially (Gemini rate limits),
detects the placeholder-fallback signature in each run's output, and retries once.
Writes a JSONL progress log so an external monitor can tail it.

Usage (on the VPS):
  cd /root/tinboker-agents/services/podcast
  GOOGLE_APPLICATION_CREDENTIALS=$PWD/gcp-service-account.json \
  nohup /root/tinboker-agents/.venv/bin/python -u scripts/_reprocess_batch.py \
      > /root/reprocess-batch.out 2>&1 &
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[1]
PYTHON = "/root/tinboker-agents/.venv/bin/python"
PROGRESS = Path("/root/reprocess-progress.jsonl")

IDS = [
    "TheDisciplinedInvestor_7cc77d87faf82fdb", "ExchangesatGoldmanSachs_0b732b473d8c1f75",
    "CNBCsFastMoney_87a8165573b4ac78", "MotleyFoolMoney_8b99ebb8b7f6486f",
    "TheLongView_c60cc9ac78af61fe", "CNBCsFastMoney_9409f2797ca7f47d",
    "MotleyFoolMoney_0fe082673348cdfe", "CNBCsFastMoney_4b2b1f853da6895d",
    "BloombergMastersinBusinessPodc_2f0f826c395baceb", "InsidetheStrategyRoom_7445ae9897ceef44",
    "BloombergMastersinBusinessPodc_67210436f8a70afa", "CapitalAllocators_3629e81ffe89a948",
    "MotleyFoolMoney_f88e55adc67f53c6", "TheDisciplinedInvestor_ce7b6b9cff2e814f",
    "CNBCsFastMoney_4bb6c7e20a3074e5", "ExchangesatGoldmanSachs_5a3c066971fa21a6",
    "TheLongView_82375162a4e5dd36", "f595f5ab_df9d2e650ddebb2d",
    "e55a9f33_3ae991448b8477b8", "Gooaye_e3ed7c7216be0fe3",
    "MotleyFoolMoney_a2fd15b8f12ef59f", "MotleyFoolMoney_ac448377a9b8bc33",
    "547e2c56_8ae1a40c036960ae", "547e2c56_0d49081b7221ee8e",
    "547e2c56_b060e02a9756f9aa", "87a8b530_67463afba943c242",
    "87a8b530_865d05127a30207b", "Gooaye_735bc5f21b4fef8f",
    "547e2c56_1e367a74c6188af1", "547e2c56_4cc32959d8b9bc1c",
    "547e2c56_53bd316c8eedce02", "547e2c56_cd30ca6f60cbf46e",
    "87a8b530_bbf6c27dc6891e1b", "Gooaye_189fc28b1d9ac672",
    "Gooaye_b5ad26d35ab7fe8b", "547e2c56_28f55b19580b21e6",
    "547e2c56_6facf9e28ad7bde6", "547e2c56_adabad87a7d26a37",
    "547e2c56_c91e15588e7f9517", "547e2c56_03966ac0edb46ccc",
    "547e2c56_7f4d9f3061398bc5", "Gooaye_6f16978258c795bf",
    "547e2c56_12e2ac77b2edd631", "547e2c56_2a077260497a90fa",
    "Gooaye_f36a057134691ff0", "547e2c56_91be8225942b308d",
    "547e2c56_e94b42700e9006ad", "Gooaye_1969c2e3f0407a3e",
    "547e2c56_24636b40e9ba3f09", "547e2c56_73135ab21be5e46e",
    "87a8b530_c588d6a5bce96495", "87a8b530_ba4557e2f6254af1",
    "87a8b530_e0f6e0299c5a49a2", "Gooaye_710a596d04da6f15",
    "TheTechMAPodcast_0dc73f3fd7a90143",
]

FAIL_SIGNATURES = (
    "Using placeholder summarizer",
    "unparseable after",
    "Pipeline completed with errors",
    "Skipping episode (no transcript available",
    "does not match configured bucket",
)


def run_one(ep_id: str) -> tuple[bool, str]:
    """Return (success, reason). success=False if a placeholder fallback / error is detected."""
    proc = subprocess.run(
        [PYTHON, "main.py", "--rerun-from", "summarize", "--episode", ep_id],
        cwd=str(SERVICE_ROOT),
        capture_output=True,
        text=True,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        return False, f"exit={proc.returncode}"
    if any(sig in out for sig in FAIL_SIGNATURES):
        return False, "placeholder_fallback"
    if "Pipeline completed successfully" not in out:
        return False, "no_success_marker"
    return True, "ok"


def log(rec: dict) -> None:
    with PROGRESS.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(json.dumps(rec, ensure_ascii=False), flush=True)


def main() -> int:
    ids = IDS
    if len(sys.argv) > 1:
        ids = [ln.strip() for ln in Path(sys.argv[1]).read_text().splitlines() if ln.strip()]
    PROGRESS.write_text("", encoding="utf-8")
    total = len(ids)
    results = {}
    for i, ep_id in enumerate(ids, 1):
        ok, reason = run_one(ep_id)
        if not ok and reason == "placeholder_fallback":
            # one stochastic retry
            time.sleep(5)
            ok2, reason2 = run_one(ep_id)
            if ok2:
                ok, reason = True, "ok_after_retry"
            else:
                reason = f"{reason}->retry:{reason2}"
        results[ep_id] = (ok, reason)
        log({"i": i, "total": total, "id": ep_id, "ok": ok, "reason": reason})
        time.sleep(2)  # gentle pacing between episodes

    ok_n = sum(1 for ok, _ in results.values() if ok)
    failed = [eid for eid, (ok, _) in results.items() if not ok]
    log({"DONE": True, "ok": ok_n, "failed_count": len(failed), "failed_ids": failed})
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
