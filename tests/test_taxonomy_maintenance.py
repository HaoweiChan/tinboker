from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "taxonomy_maintenance.py"
SPEC = importlib.util.spec_from_file_location("taxonomy_maintenance", SCRIPT)
maint = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = maint
SPEC.loader.exec_module(maint)


class _FakeCompleted:
    def __init__(self, stdout: str = "", stderr: str = "") -> None:
        self.stdout = stdout
        self.stderr = stderr


def test_run_audit_invokes_uv_with_judge_and_out(monkeypatch, tmp_path):
    captured: dict[str, Any] = {}

    def _fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return _FakeCompleted()

    monkeypatch.setattr(maint.subprocess, "run", _fake_run)
    out_path = tmp_path / "report.md"
    maint.run_audit(judge=True, only=None, out_path=out_path)

    cmd = captured["cmd"]
    assert cmd[:5] == ["uv", "run", "--package", "tinboker-shared", "python"]
    assert maint.AUDIT_SCRIPT_REL in cmd
    assert "--out" in cmd and str(out_path) in cmd
    assert "--judge" in cmd
    assert captured["kwargs"]["cwd"] == str(maint.PIPELINES_DIR)
    assert captured["kwargs"]["check"] is True


def test_run_audit_passes_only_and_omits_judge(monkeypatch, tmp_path):
    captured: dict[str, Any] = {}
    monkeypatch.setattr(maint.subprocess, "run", lambda cmd, **kw: captured.update(cmd=cmd) or _FakeCompleted())
    maint.run_audit(judge=False, only="sector_a", out_path=tmp_path / "r.md")
    assert "--judge" not in captured["cmd"]
    assert captured["cmd"][-2:] == ["--only", "sector_a"]


def test_run_fill_invokes_repo_root_script_with_current_interpreter(monkeypatch):
    captured: dict[str, Any] = {}

    def _fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return _FakeCompleted(stdout="draft_id: 42\n")

    monkeypatch.setattr(maint.subprocess, "run", _fake_run)
    stdout = maint.run_fill()

    assert captured["cmd"] == [maint.sys.executable, str(maint.FILL_SCRIPT)]
    assert captured["kwargs"]["check"] is True
    assert captured["kwargs"]["capture_output"] is True
    assert stdout == "draft_id: 42\n"


def test_parse_draft_id_found():
    assert maint.parse_draft_id("draft_id: 42\ndiff:\n{}") == "42"


def test_parse_draft_id_missing_when_no_draft_needed():
    assert maint.parse_draft_id("No missing sector descriptions or member reasons found.") is None


def test_main_orchestrates_audit_then_fill_and_prints_summary(monkeypatch, tmp_path, capsys):
    calls: list[str] = []

    def _fake_run_audit(*, judge, only, out_path):
        calls.append("audit")
        assert judge is True
        assert only is None

    def _fake_run_fill():
        calls.append("fill")
        return "No missing sector descriptions or member reasons found.\n"

    monkeypatch.setattr(maint, "run_audit", _fake_run_audit)
    monkeypatch.setattr(maint, "run_fill", _fake_run_fill)
    monkeypatch.setattr(sys, "argv", ["taxonomy_maintenance.py", "--report-dir", str(tmp_path)])

    exit_code = maint.main()

    assert exit_code == 0
    assert calls == ["audit", "fill"]
    out = capsys.readouterr().out
    assert "no draft needed" in out
    assert "G5" in out
    assert "export_taxonomy_snapshot.py" in out
