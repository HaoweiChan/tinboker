"""Unit tests for the post-ingest syndication trigger (Step 5f).

The step imports ``shared.platform_client`` lazily,
so the skip paths return before that import and the fire paths inject a fake module.
"""

from __future__ import annotations

import sys
import types
from datetime import datetime, timedelta, timezone

from src.pipeline.steps import syndicate as sy


def _cfg(rerun=None):
    return types.SimpleNamespace(rerun_from=rerun)


def _ep(summary="內文一段。", episode_id="EP1", key="summary_text", age_days=1,
        with_model=True):
    """An episode fake shaped like the one step 5f actually sees.

    ``summary_text`` is the key the real pipeline writes (summarize.py); a fake shaped
    with a key production never uses is how the silent-skip bug survived these tests.
    ``age_days`` is how long ago it was published — the whole point of the gate.
    """
    released = datetime.now(timezone.utc) - timedelta(days=age_days)
    ms = int(released.timestamp() * 1000)
    return types.SimpleNamespace(
        episode_id=episode_id,
        summary_result=({key: summary} if summary is not None else None),
        episode=(types.SimpleNamespace(resolved_publish_ms=lambda: ms) if with_model else None),
        spotify_metadata=None,
        created_time=None,
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


def test_the_back_catalogue_does_not_get_syndicated(monkeypatch, capsys):
    """Ingest pulls the last 10 episodes per show and walks backwards, so most of what
    it touches is years old. Every one of those is a first-time syndication no ledger
    would stop — 44 posts a day onto a publication nobody asked to flood."""
    monkeypatch.setenv("SYNDICATE_AUTOPUBLISH", "1")
    called = {"n": 0}
    _inject_fake_client(monkeypatch, lambda episode_id, **kw: called.__setitem__("n", called["n"] + 1))
    sy.trigger_syndicate(_cfg(None), None, _ep(age_days=1500))
    assert called["n"] == 0
    assert "1500 days old" in capsys.readouterr().out


def test_a_fresh_episode_still_goes_out(monkeypatch):
    monkeypatch.setenv("SYNDICATE_AUTOPUBLISH", "1")
    called = {"n": 0}

    def _fake(episode_id, **kw):
        called["n"] += 1
        return {"platforms": {}}

    _inject_fake_client(monkeypatch, _fake)
    sy.trigger_syndicate(_cfg(None), None, _ep(age_days=6))
    assert called["n"] == 1


def test_the_window_is_configurable_and_zero_turns_it_off(monkeypatch):
    """0 is the deliberate-backfill escape hatch: without it, syndicating the archive
    on purpose would mean editing code."""
    monkeypatch.setenv("SYNDICATE_AUTOPUBLISH", "1")
    calls = []
    _inject_fake_client(monkeypatch, lambda episode_id, **kw: calls.append(episode_id))

    monkeypatch.setenv("SYNDICATE_MAX_AGE_DAYS", "30")
    sy.trigger_syndicate(_cfg(None), None, _ep(episode_id="in-window", age_days=20))
    monkeypatch.setenv("SYNDICATE_MAX_AGE_DAYS", "0")
    sy.trigger_syndicate(_cfg(None), None, _ep(episode_id="gate-off", age_days=1500))
    assert calls == ["in-window", "gate-off"]


def test_an_unknown_publish_time_is_not_treated_as_new(monkeypatch, capsys):
    """Publishing is public and irreversible; a wrong skip costs one article the admin
    Social page can still stage by hand."""
    monkeypatch.setenv("SYNDICATE_AUTOPUBLISH", "1")
    called = {"n": 0}
    _inject_fake_client(monkeypatch, lambda episode_id, **kw: called.__setitem__("n", called["n"] + 1))
    sy.trigger_syndicate(_cfg(None), None, _ep(with_model=False))
    assert called["n"] == 0
    assert "no publish time" in capsys.readouterr().out


def test_the_release_datetime_is_used_when_the_model_is_missing(monkeypatch):
    """Same fallback chain as ticker_insights_export — and no now() at the end of it,
    which would date the whole back catalogue to the run and open the gate for all of it."""
    monkeypatch.setenv("SYNDICATE_AUTOPUBLISH", "1")
    calls = []
    _inject_fake_client(monkeypatch, lambda episode_id, **kw: calls.append(episode_id))

    old = datetime.now(timezone.utc) - timedelta(days=900)
    ep = _ep(episode_id="from-spotify", with_model=False)
    ep.spotify_metadata = {"release_datetime": old}
    sy.trigger_syndicate(_cfg(None), None, ep)

    fresh = _ep(episode_id="from-created-time", with_model=False)
    fresh.created_time = datetime.now(timezone.utc) - timedelta(days=2)
    sy.trigger_syndicate(_cfg(None), None, fresh)

    assert calls == ["from-created-time"]
