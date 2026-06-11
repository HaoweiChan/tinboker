"""Unit tests for the Massive (Polygon) per-key pool + per-minute rotation."""

import pytest

import src.services.massive_service as m


def test_config_pool_prefers_plural_and_dedups():
    from src.config import Settings
    s = Settings(massive_api_keys=" k1, k2 ,k2 ", massive_api_key="solo")
    assert s.massive_api_key_pool == ["k1", "k2"]
    assert Settings(massive_api_key="solo").massive_api_key_pool == ["solo"]
    assert Settings().massive_api_key_pool == []


class _FakeRC:
    def __init__(self, key):
        self.key = key


def _fresh_service(monkeypatch, keys, per_min):
    # Patch the live settings singleton + module globals directly (env is read at settings
    # init in production, so setenv here wouldn't take effect).
    monkeypatch.setattr(m.settings, "massive_api_keys", keys or None, raising=False)
    monkeypatch.setattr(m.settings, "massive_api_key", None, raising=False)
    monkeypatch.setattr(m, "RESTClient", _FakeRC)
    monkeypatch.setattr(m, "_MASSIVE_PER_MIN", per_min)
    m._minute_counts.clear()
    return m


def test_rotation_load_balances_then_falls_back(monkeypatch):
    m = _fresh_service(monkeypatch, "k1,k2", per_min=2)
    svc = m.MassiveAPIService()
    assert [kid for kid, _ in svc._clients] == ["0", "1"]
    seq = [svc.client.key for _ in range(5)]
    # 2/key budget across 2 keys: k1,k1 -> k2,k2 -> all spent -> fall back to first
    assert seq == ["k1", "k1", "k2", "k2", "k1"]


def test_single_key_still_works(monkeypatch):
    m = _fresh_service(monkeypatch, "only", per_min=5)
    svc = m.MassiveAPIService()
    assert svc.client.key == "only"
    svc._check_client()  # does not raise


def test_no_keys_raises_on_check(monkeypatch):
    m = _fresh_service(monkeypatch, "", per_min=5)
    # Force empty pool (no env key)
    monkeypatch.setattr(m.settings, "massive_api_keys", None, raising=False)
    monkeypatch.setattr(m.settings, "massive_api_key", None, raising=False)
    svc = m.MassiveAPIService()
    assert svc.client is None
    with pytest.raises(m.MassiveAPIError):
        svc._check_client()
