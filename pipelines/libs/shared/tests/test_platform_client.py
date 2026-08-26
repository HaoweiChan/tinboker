"""Tests for shared.platform_client — opt-in, offline-safe platform follow-list pull."""

from __future__ import annotations

import json

from shared import platform_client


def test_base_url_none_when_env_unset(monkeypatch):
    monkeypatch.delenv("TINBOKER_PLATFORM_API_URL", raising=False)
    assert platform_client.platform_base_url() is None


def test_base_url_strips_trailing_slash(monkeypatch):
    monkeypatch.setenv("TINBOKER_PLATFORM_API_URL", "https://api.example.com/")
    assert platform_client.platform_base_url() == "https://api.example.com"


def test_fetch_sources_returns_none_when_disabled(monkeypatch):
    # Disabled (no env) → returns None immediately, never touches the network.
    monkeypatch.delenv("TINBOKER_PLATFORM_API_URL", raising=False)

    def _boom(*a, **k):  # pragma: no cover — must not be called
        raise AssertionError("network attempted while disabled")

    monkeypatch.setattr(platform_client.urllib.request, "urlopen", _boom)
    assert platform_client.fetch_sources("podcast") is None


def test_fetch_sources_parses_items(monkeypatch):
    monkeypatch.setenv("TINBOKER_PLATFORM_API_URL", "https://api.example.com")
    captured: dict = {}

    class _Resp:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps({"total": 1, "items": [{"name": "X"}]}).encode()

    def _fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        return _Resp()

    monkeypatch.setattr(platform_client.urllib.request, "urlopen", _fake_urlopen)
    out = platform_client.fetch_sources("news")
    assert out == [{"name": "X"}]
    assert "type=news" in captured["url"] and "active=true" in captured["url"]


def test_fetch_sources_returns_none_on_error(monkeypatch):
    monkeypatch.setenv("TINBOKER_PLATFORM_API_URL", "https://api.example.com")

    def _boom(req, timeout=None):
        raise OSError("network down")

    monkeypatch.setattr(platform_client.urllib.request, "urlopen", _boom)
    assert platform_client.fetch_sources("podcast") is None


def test_fetch_translation_aliases_returns_none_when_disabled(monkeypatch):
    monkeypatch.delenv("TINBOKER_PLATFORM_API_URL", raising=False)

    def _boom(*a, **k):  # pragma: no cover — must not be called
        raise AssertionError("network attempted while disabled")

    monkeypatch.setattr(platform_client.urllib.request, "urlopen", _boom)
    assert platform_client.fetch_translation_aliases() is None


def test_fetch_translation_aliases_parses_items(monkeypatch):
    monkeypatch.setenv("TINBOKER_PLATFORM_API_URL", "https://api.example.com")
    captured: dict = {}

    class _Resp:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps({"items": [{"ticker": "2330", "aliases": ["TSMC"]}]}).encode()

    def _fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        return _Resp()

    monkeypatch.setattr(platform_client.urllib.request, "urlopen", _fake_urlopen)
    out = platform_client.fetch_translation_aliases()
    assert out == [{"ticker": "2330", "aliases": ["TSMC"]}]
    assert captured["url"].endswith("/api/stocks/translations/aliases")


def test_all_requests_carry_the_self_identifying_user_agent(monkeypatch):
    # Cloudflare's bot rules 403 the default `Python-urllib/x.y` UA at the edge — every
    # request this module makes must self-identify instead.
    monkeypatch.setenv("TINBOKER_PLATFORM_API_URL", "https://api.example.com")
    monkeypatch.setenv("TINBOKER_SOCIAL_TOKEN", "sekret")
    captured: list[str | None] = []

    class _Resp:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps({"items": []}).encode()

    def _fake_urlopen(req, timeout=None):
        captured.append(req.get_header("User-agent"))
        return _Resp()

    monkeypatch.setattr(platform_client.urllib.request, "urlopen", _fake_urlopen)
    platform_client.fetch_sources("podcast")
    platform_client.fetch_translation_aliases()
    platform_client.fetch_sectors_universe()

    assert captured == [platform_client.USER_AGENT] * 3


def test_syndication_trigger_is_opt_in_like_the_others(monkeypatch):
    """No env vars, no network call — the opt-in rule every trigger follows."""
    from shared import platform_client as pc

    monkeypatch.delenv("TINBOKER_PLATFORM_API_URL", raising=False)
    monkeypatch.delenv("TINBOKER_SOCIAL_TOKEN", raising=False)
    assert pc.trigger_syndication("EP1") is None


def test_syndication_needs_an_episode_id(monkeypatch):
    """It is per-episode, not "recent N": the platform creates a new draft every call, so
    there is nothing sensible to do without knowing which episode."""
    from shared import platform_client as pc

    monkeypatch.setenv("TINBOKER_PLATFORM_API_URL", "https://api.test")
    monkeypatch.setenv("TINBOKER_SOCIAL_TOKEN", "t")
    assert pc.trigger_syndication("") is None


def test_admin_calls_go_to_a_host_that_mounts_admin_routes(monkeypatch):
    """Production mounts no /api/admin/* routers at all (backend/src/main.py), so pointing
    admin traffic at api.tinboker.com is a guaranteed 404 — by design, not by accident."""
    from shared import platform_client as pc

    monkeypatch.setenv("TINBOKER_PLATFORM_API_URL", "https://api.tinboker.com")
    monkeypatch.setenv("TINBOKER_ADMIN_API_URL", "https://staging-api.tinboker.com")
    assert pc.admin_base_url() == "https://staging-api.tinboker.com"
    assert pc.platform_base_url() == "https://api.tinboker.com"


def test_admin_base_falls_back_to_the_platform_url(monkeypatch):
    """Right for a local run against a dev backend."""
    from shared import platform_client as pc

    monkeypatch.delenv("TINBOKER_ADMIN_API_URL", raising=False)
    monkeypatch.setenv("TINBOKER_PLATFORM_API_URL", "http://localhost:5174")
    assert pc.admin_base_url() == "http://localhost:5174"


def test_social_enabled_for_reads_switch_and_fails_open(monkeypatch):
    """Muted shows report False; unknown shows and an unreachable platform report True."""
    monkeypatch.setattr(platform_client, "_SOCIAL_ENABLED_CACHE", None)
    monkeypatch.setattr(
        platform_client, "fetch_sources",
        lambda *a, **k: [{"name": "財經一路發", "social_enabled": False},
                         {"name": "股癌", "social_enabled": True}],
    )
    assert platform_client.social_enabled_for("財經一路發") is False
    assert platform_client.social_enabled_for("股癌") is True
    assert platform_client.social_enabled_for("沒登記的節目") is True

    # Platform unreachable (fetch_sources returns None) → everything stays enabled.
    monkeypatch.setattr(platform_client, "_SOCIAL_ENABLED_CACHE", None)
    monkeypatch.setattr(platform_client, "fetch_sources", lambda *a, **k: None)
    assert platform_client.social_enabled_for("財經一路發") is True
