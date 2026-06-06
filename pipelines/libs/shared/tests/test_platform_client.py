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


def test_trigger_threads_publish_disabled_without_token(monkeypatch):
    # Needs BOTH base url and token; with the URL but no token it is a no-op.
    monkeypatch.setenv("TINBOKER_PLATFORM_API_URL", "https://api.example.com")
    monkeypatch.delenv("TINBOKER_SOCIAL_TOKEN", raising=False)

    def _boom(*a, **k):  # pragma: no cover — must not be called
        raise AssertionError("network attempted while disabled")

    monkeypatch.setattr(platform_client.urllib.request, "urlopen", _boom)
    assert platform_client.trigger_threads_publish() is None


def test_trigger_threads_publish_posts_with_bearer(monkeypatch):
    monkeypatch.setenv("TINBOKER_PLATFORM_API_URL", "https://api.example.com")
    monkeypatch.setenv("TINBOKER_SOCIAL_TOKEN", "sekret")
    captured: dict = {}

    class _Resp:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps({"posted_count": 1, "dry_run": False}).encode()

    def _fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["method"] = req.get_method()
        captured["auth"] = req.get_header("Authorization")
        return _Resp()

    monkeypatch.setattr(platform_client.urllib.request, "urlopen", _fake_urlopen)
    out = platform_client.trigger_threads_publish(limit=5, dry_run=False)
    assert out == {"posted_count": 1, "dry_run": False}
    assert captured["method"] == "POST"
    assert captured["auth"] == "Bearer sekret"
    assert "dry_run=false" in captured["url"] and "limit=5" in captured["url"]


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
