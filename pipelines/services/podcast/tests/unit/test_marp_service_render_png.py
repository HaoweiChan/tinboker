"""Regression for the /render-png marp command ordering.

`--theme-set` is a greedy *array* option in marp-cli. If the input deck is placed
AFTER `--theme-set` (e.g. `marp --theme-set theme.css deck.md ...`), marp swallows
deck.md as a second theme file, gets no input, prints help, and returns 0 images
(success=true, count=0). The input file must come before `--theme-set`.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from src.podcast.marp_service.main import app


@pytest.fixture
def client():
    app.config.update(TESTING=True)
    return app.test_client()


def test_render_png_puts_input_before_theme_set(client):
    captured = {}

    def _fake_run(cmd, *a, **k):
        captured["cmd"] = cmd
        return MagicMock(returncode=0, stderr="")

    # No files produced — we only assert the command shape, not real rendering.
    with patch("src.podcast.marp_service.main.subprocess.run", side_effect=_fake_run), \
         patch("glob.glob", return_value=[]):
        resp = client.post("/render-png", json={"markdown": "# A\n\n---\n\n# B", "theme_css": "section{}"})

    assert resp.status_code == 200
    cmd = captured["cmd"]
    assert "--theme-set" in cmd
    md_idx = next(i for i, a in enumerate(cmd) if str(a).endswith(".md"))
    assert md_idx < cmd.index("--theme-set"), f"input must precede --theme-set: {cmd}"
