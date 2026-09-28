"""Release-language gate for the scheduled podcast ingest."""

import os
import subprocess
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
        ('["zh-TW", "en"]', True),
    ],
)
def test_english_ingest_follows_release_scope(tmp_path, languages, english_enabled):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_python = fake_bin / "python3"
    fake_python.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$CALLS_LOG"\n')
    fake_python.chmod(0o755)

    calls_log = tmp_path / "calls.log"
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}:{env['PATH']}"
    env["CALLS_LOG"] = str(calls_log)
    if languages is None:
        env.pop("RELEASE_PODCAST_LANGUAGES", None)
    else:
        env["RELEASE_PODCAST_LANGUAGES"] = languages

    subprocess.run(["bash", str(_SCRIPT), "--limit", "2"], env=env, check=True, capture_output=True)
    calls = calls_log.read_text().splitlines()
    assert calls == [
        "main.py --config podcasts_tw.json --fill-limit --limit 2",
        *(["main.py --config podcasts_en.json --fill-limit --limit 2"] if english_enabled else []),
    ]
