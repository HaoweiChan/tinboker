"""Unit tests for the post-ingest syndication trigger (Step 5f).

Same shape as test_social_publish.py: the step imports ``shared.platform_client`` lazily,
so the skip paths return before that import and the fire paths inject a fake module.
"""

from __future__ import annotations

import sys
import types

from src.pipeline.steps import syndicate as sy


def _cfg(rerun=None):
    return types.SimpleNamespace(rerun_from=rerun)


def _ep(summary="內文一段。", episode_id="EP1", key="summary_text"):
    # ``summary_text`` is the key the real pipeline writes (summarize.py). A fake shaped
    # with a key production never uses is how the silent-skip bug survived these tests.
    return types.SimpleNamespace(
        episode_id=episode_id,
        summary_result=({key: summary} if summary is not None else None),
    )


def _inject_fake_client(monkeypatch, fn):
    monkeypatch.setitem(sys.modules, "shared", sys.modules.get("shared") or types.ModuleType("shared"))
    mod = types.ModuleType("shared.platform_client")
    mod.trigger_syndication = fn
    monkeypatch.setitem(sys.modules, "shared.platform_client", mod)


def test_skips_on_rerun():
    """Each call creates fresh drafts — the platform does not dedupe — so a backfill
    would republish everything it touched."""
    sy.trigger_syndicate(_cfg("summarize"), None, _ep())


def test_skips_without_a_summary(capsys):
    sy.trigger_syndicate(_cfg(None), None, _ep(None))
    sy.trigger_syndicate(_cfg(None), None, _ep("   "))
    # The skip must be visible in the run log — a silent return hid a total outage.
    assert "Syndication skipped" in capsys.readouterr().out


def test_fires_for_every_summary_key_the_pipeline_uses(monkeypatch):
    """summary_text (the live ingest shape), markdown_report and summary_content all count."""
    monkeypatch.setenv("SYNDICATE_AUTOPUBLISH", "1")
    for key in ("summary_text", "markdown_report", "summary_content"):
        called = {"n": 0}

        def _fake(episode_id, **kw):
            called["n"] += 1
            return {"platforms": {}}

        _inject_fake_client(monkeypatch, _fake)
        sy.trigger_syndicate(_cfg(None), None, _ep(key=key))
        assert called["n"] == 1, key


def test_skips_when_disabled(monkeypatch):
    monkeypatch.delenv("SYNDICATE_AUTOPUBLISH", raising=False)
    called = {"n": 0}

    def _fake(*a, **kw):
        called["n"] += 1
        return None

    _inject_fake_client(monkeypatch, _fake)
    sy.trigger_syndicate(_cfg(None), None, _ep())
    assert called["n"] == 0


def test_fires_once_for_the_ingested_episode(monkeypatch):
    monkeypatch.setenv("SYNDICATE_AUTOPUBLISH", "1")
    seen = {}

    def _fake(episode_id, **kw):
        seen.update(episode_id=episode_id, **kw)
        return {"platforms": {"vocus": {"posted": True, "url": "u"},
                              "substack": {"posted": True, "url": "v"}}}

    _inject_fake_client(monkeypatch, _fake)
    sy.trigger_syndicate(_cfg(None), None, _ep(episode_id="EP42"))
    assert seen["episode_id"] == "EP42"
    assert seen["publish_vocus"] is False
    assert seen["publish_substack"] is False


def test_each_platform_has_its_own_publish_switch(monkeypatch):
    """Separate on purpose: turning one on must never quietly turn the other on."""
    monkeypatch.setenv("SYNDICATE_AUTOPUBLISH", "1")
    monkeypatch.setenv("SYNDICATE_VOCUS_PUBLISH", "true")
    monkeypatch.delenv("SYNDICATE_SUBSTACK_PUBLISH", raising=False)
    seen = {}

    def _fake(episode_id, **kw):
        seen.update(kw)
        return {"platforms": {}}

    _inject_fake_client(monkeypatch, _fake)
    sy.trigger_syndicate(_cfg(None), None, _ep())
    assert seen["publish_vocus"] is True
    assert seen["publish_substack"] is False


def test_one_platform_failing_does_not_hide_the_other(monkeypatch, capsys):
    monkeypatch.setenv("SYNDICATE_AUTOPUBLISH", "1")
    _inject_fake_client(monkeypatch, lambda episode_id, **kw: {"platforms": {
        "vocus": {"posted": True, "url": "https://vocus.cc/x"},
        "substack": {"posted": False, "reason": "credential_expired"},
    }})
    sy.trigger_syndicate(_cfg(None), None, _ep())
    out = capsys.readouterr().out
    assert "https://vocus.cc/x" in out
    assert "credential_expired" in out


def test_a_client_error_never_breaks_ingestion(monkeypatch):
    monkeypatch.setenv("SYNDICATE_AUTOPUBLISH", "1")

    def _boom(*a, **kw):
        raise RuntimeError("network gone")

    _inject_fake_client(monkeypatch, _boom)
    sy.trigger_syndicate(_cfg(None), None, _ep())   # must not raise


def test_substack_publishing_has_its_own_switch(monkeypatch):
    """And even switched on it cannot email: send_email is hard-wired False in the
    publisher, with no parameter reaching it from here."""
    monkeypatch.setenv("SYNDICATE_AUTOPUBLISH", "1")
    monkeypatch.setenv("SYNDICATE_SUBSTACK_PUBLISH", "1")
    monkeypatch.delenv("SYNDICATE_VOCUS_PUBLISH", raising=False)
    seen = {}

    def _fake(episode_id, **kw):
        seen.update(kw)
        return {"platforms": {}}

    _inject_fake_client(monkeypatch, _fake)
    sy.trigger_syndicate(_cfg(None), None, _ep())
    assert seen["publish_substack"] is True
    assert seen["publish_vocus"] is False
