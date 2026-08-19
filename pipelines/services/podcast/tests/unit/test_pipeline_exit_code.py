"""A scheduled run that accomplished nothing must not report success."""

from __future__ import annotations

import pytest
from src.podcast.orchestrator import PipelineRunError


def test_the_error_names_the_shows_that_failed():
    """systemd shows the last line; it should say which feed broke, not just that one did."""
    e = PipelineRunError(["財經一路發", "韭菜畢業班"])
    assert "2 show(s) failed" in str(e)
    assert "財經一路發" in str(e)
    assert e.shows == ["財經一路發", "韭菜畢業班"]


def test_it_is_an_exception_so_the_process_exits_non_zero():
    """The whole point: previously every show could fail, "Pipeline completed!" printed,
    and the unit exited 0 — which is how a broken DB URL ran hourly for three days
    without anyone noticing."""
    assert issubclass(PipelineRunError, Exception)
    with pytest.raises(PipelineRunError):
        raise PipelineRunError(["x"])


def test_a_failing_show_propagates_out_of_the_run(monkeypatch, tmp_path):
    """End to end through the real _handle_api_mode: one show fails, the error reaches the
    caller instead of being printed and forgotten."""
    from src.podcast import orchestrator as o

    monkeypatch.setattr(o, "_process_single_podcast", lambda **kw: False)
    with pytest.raises(PipelineRunError) as exc:
        o._handle_api_mode(
            podcasts=[{"name": "壞掉的節目"}], config_file=tmp_path / "c.json",
            rerun_from=None, transcript_service="groq", use_file_mode=True,
            reuse_existing_transcript=False, fill_limit=False,
            base_config=object(), service_container=object(),
        )
    assert exc.value.shows == ["壞掉的節目"]


def test_every_show_succeeding_raises_nothing(monkeypatch, tmp_path):
    from src.podcast import orchestrator as o

    monkeypatch.setattr(o, "_process_single_podcast", lambda **kw: True)
    o._handle_api_mode(
        podcasts=[{"name": "好節目"}], config_file=tmp_path / "c.json",
        rerun_from=None, transcript_service="groq", use_file_mode=True,
        reuse_existing_transcript=False, fill_limit=False,
        base_config=object(), service_container=object(),
    )
