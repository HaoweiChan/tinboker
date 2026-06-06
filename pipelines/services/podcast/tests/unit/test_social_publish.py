"""Unit tests for the post-ingest Threads trigger step (Step 5e).

The step imports ``shared.platform_client`` lazily (inside the function), since ``shared``
lives in the root workspace venv, not the podcast sub-venv. The skip paths return before
that import, so they run as-is; the fire paths inject a fake ``shared`` module.
(The platform client itself is unit-tested in libs/shared/tests/test_platform_client.py.)
"""

from __future__ import annotations

import sys
import types

from src.pipeline.steps import social_publish as sp


def _cfg(rerun=None):
    return types.SimpleNamespace(rerun_from=rerun)


def _ep(cards):
    return types.SimpleNamespace(summary_result=({"social_cards": cards} if cards is not None else None))


def _inject_fake_client(monkeypatch, fn):
    monkeypatch.setitem(sys.modules, "shared", sys.modules.get("shared") or types.ModuleType("shared"))
    mod = types.ModuleType("shared.platform_client")
    mod.trigger_threads_publish = fn
    monkeypatch.setitem(sys.modules, "shared.platform_client", mod)


def test_skips_on_rerun():
    # Returns before the shared import — safe in the podcast venv.
    sp.trigger_social_publish(_cfg("summarize"), None, _ep([{"kind": "cover"}]))


def test_skips_without_cards():
    sp.trigger_social_publish(_cfg(None), None, _ep(None))
    sp.trigger_social_publish(_cfg(None), None, _ep([]))


def test_fires_on_fresh_run_with_cards(monkeypatch):
    seen = {}
    _inject_fake_client(monkeypatch, lambda **k: seen.update(k) or {"posted_count": 1, "dry_run": False})
    sp.trigger_social_publish(_cfg(None), None, _ep([{"kind": "cover"}]))
    assert seen == {"limit": 5, "dry_run": False}


def test_fire_is_non_fatal_on_client_error(monkeypatch):
    def _boom(**k):
        raise RuntimeError("platform down")
    _inject_fake_client(monkeypatch, _boom)
    sp.trigger_social_publish(_cfg(None), None, _ep([{"kind": "cover"}]))  # must not raise
