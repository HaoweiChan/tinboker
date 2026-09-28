"""Release-language gate for the scheduled podcast ingest."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts/run_scheduled_ingest.sh"


@pytest.mark.parametrize(
    ("languages", "english_enabled"),
    [
        (None, False),
        ("", True),
        (" ", True),
        ("[]", True),
        ("zh-TW", False),
        ("ja", False),
        ("en", True),
        ("zh-TW,en", True),
        ("zh-TW, en", True),
        ('["en"]', True),
        ('["zh-TW", "en"]', True),
        ('["zh-TW,en"]', False),
    ],
)
def test_english_ingest_follows_release_scope(tmp_path, languages, english_enabled):
    # Mirror the script's layout so its preferred .venv/bin/python is the stub,
    # even when the developer's real checkout already has a .venv.
    workspace = tmp_path / "workspace"
    script = workspace / "services/podcast/scripts/run_scheduled_ingest.sh"
    script.parent.mkdir(parents=True)
    script.write_bytes(_SCRIPT.read_bytes())
    fake_python = workspace / ".venv/bin/python"
    fake_python.parent.mkdir(parents=True)
    fake_python.write_text(
        '#!/bin/sh\n'
        'if [ "$1" = "-c" ]; then exec "$REAL_PYTHON" "$@"; fi\n'
        'printf "%s\\n" "$*" >> "$CALLS_LOG"\n'
    )
    fake_python.chmod(0o755)

    calls_log = tmp_path / "calls.log"
    env = os.environ.copy()
    env["CALLS_LOG"] = str(calls_log)
    env["REAL_PYTHON"] = sys.executable
    if languages is None:
        env.pop("RELEASE_PODCAST_LANGUAGES", None)
    else:
        env["RELEASE_PODCAST_LANGUAGES"] = languages

    subprocess.run(["bash", str(script), "--limit", "2"], env=env, check=True, capture_output=True)
    calls = calls_log.read_text().splitlines()
    assert calls == [
        "main.py --config podcasts_tw.json --fill-limit --limit 2",
        *(["main.py --config podcasts_en.json --fill-limit --limit 2"] if english_enabled else []),
    ]
