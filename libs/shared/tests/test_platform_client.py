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
