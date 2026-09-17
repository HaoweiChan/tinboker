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
    def __init__(self, key, **kwargs):
        self.key = key
        self.kwargs = kwargs


def _fresh_service(monkeypatch, keys, per_min):
    # Patch the live settings singleton + module globals directly (env is read at settings
    # init in production, so setenv here wouldn't take effect).
    monkeypatch.setattr(m.settings, "massive_api_keys", keys or None, raising=False)
    monkeypatch.setattr(m.settings, "massive_api_key", None, raising=False)
    monkeypatch.setattr(m, "RESTClient", _FakeRC)
    monkeypatch.setattr(m, "_MASSIVE_PER_MIN", per_min)
    monkeypatch.setattr(m, "_shared_budget", lambda: None)  # in-process counting
    m._minute_counts.clear()
    return m


def test_rotation_load_balances_then_refuses_once_spent(monkeypatch):
    m = _fresh_service(monkeypatch, "k1,k2", per_min=2)
    svc = m.MassiveAPIService()
    assert [kid for kid, _ in svc._clients] == [m._key_id("k1"), m._key_id("k2")]
    assert all("k1" not in kid and "k2" not in kid for kid, _ in svc._clients)  # never the key
    seq = [svc.client.key for _ in range(4)]
    # 2/key budget across 2 keys: k1,k1 -> k2,k2 -> all spent -> refuse, don't send a sure 429
    assert seq == ["k1", "k1", "k2", "k2"]
    with pytest.raises(m.MassiveAPIError, match="budget"):
        svc.client


def test_sdk_does_not_retry_429s(monkeypatch):
    m = _fresh_service(monkeypatch, "k1", per_min=5)
    assert m.MassiveAPIService()._clients[0][1].kwargs == {"retries": 0}


class _FakeRedis:
    def __init__(self):
        self.store = {}

    def incr(self, name):
        self.store[name] = self.store.get(name, 0) + 1
        return self.store[name]

    def expire(self, name, seconds):
        pass


def test_budget_is_shared_across_environments(monkeypatch):
    """dev, staging and prod each counted their own 5/min against the same keys."""
    m = _fresh_service(monkeypatch, "k1", per_min=3)
    shared = _FakeRedis()
    monkeypatch.setattr(m, "_shared_budget", lambda: shared)
    prod, dev = m.MassiveAPIService(), m.MassiveAPIService()
    prod.client, dev.client, prod.client
    with pytest.raises(m.MassiveAPIError):
        dev.client


def test_image_downloads_take_budget_and_stop_when_spent(monkeypatch):
    m = _fresh_service(monkeypatch, "k1", per_min=1)
    m._IMG_CACHE.clear()
    calls = []

    class _Resp:
        content = b"png"

        def raise_for_status(self):
            pass

    monkeypatch.setattr(m.requests, "get", lambda url, **kw: calls.append(url) or _Resp())
    svc = m.MassiveAPIService()
    assert svc._fetch_image_b64("https://api.massive.com/a.png")  # takes the only unit
    assert svc._fetch_image_b64("https://api.massive.com/b.svg") is None
    assert calls == ["https://api.massive.com/a.png"]


def test_ticker_details_reuse_stored_logos_instead_of_downloading(monkeypatch):
    m = _fresh_service(monkeypatch, "k1", per_min=5)
    from types import SimpleNamespace

    details = SimpleNamespace(ticker="NVDA", name="Nvidia", market_cap=1, description="", currency_name="usd",
                              branding=SimpleNamespace(icon_url="https://x/i.png", logo_url="https://x/l.svg"))
    monkeypatch.setattr(_FakeRC, "get_ticker_details", lambda self, t: details, raising=False)
    monkeypatch.setattr(m, "_stored_images", lambda t: {"icon_image": "ICON", "logo_image": "LOGO"})
    monkeypatch.setattr(m.MassiveAPIService, "_fetch_image_b64", lambda self, url: pytest.fail("downloaded"))
    out = m.MassiveAPIService().get_ticker_details("NVDA")
    assert (out["icon_image"], out["logo_image"]) == ("ICON", "LOGO")


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
