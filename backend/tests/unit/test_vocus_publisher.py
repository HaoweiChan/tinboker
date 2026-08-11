"""The vocus publisher's failure paths.

vocus's API is undocumented and its credential expires weekly, so the cases that matter
are the ones where something is wrong: they must fail loudly rather than look like a
successful no-op. A silent skip here means weeks of articles that were never published.
"""

import base64
import json
import time

import httpx
import pytest

from src.services import vocus_publisher as vp


@pytest.fixture(autouse=True)
def _isolate_token_source(monkeypatch):
    """No live Secret Manager call, and no token cached across tests.

    current_token() prefers a fresh GSM read so a rotated token takes effect without a
    restart; in tests that must be inert, or a stale cache silently decides the result.
    """
    monkeypatch.setattr(vp, "_fetch_token_from_gsm", lambda: None)
    monkeypatch.setattr(vp, "_token_cache", None, raising=False)
    yield
    vp._token_cache = None


def _token(exp_offset: int) -> str:
    """A token shaped like vocus's, with a chosen expiry. Never signed — the publisher
    only reads `exp`, it does not verify anything."""
    payload = base64.urlsafe_b64encode(
        json.dumps({"exp": int(time.time()) + exp_offset, "loginID": "x"}).encode()
    ).decode().rstrip("=")
    return f"header.{payload}.signature"


# ── token_status ─────────────────────────────────────────────────────────────

def test_missing_token_is_unconfigured_and_expired():
    s = vp.token_status("")
    assert s["configured"] is False and s["expired"] is True


def test_live_token_reports_time_remaining():
    s = vp.token_status(_token(5 * 24 * 3600))
    assert s["configured"] and not s["expired"] and not s["expiring_soon"]
    assert s["seconds_left"] > 4 * 24 * 3600


def test_token_inside_the_warning_window_is_flagged_early():
    # Flagged while there is still time to replace it, not once posting already broke.
    s = vp.token_status(_token(24 * 3600))
    assert s["expired"] is False and s["expiring_soon"] is True


def test_expired_token_is_expired():
    assert vp.token_status(_token(-60))["expired"] is True


def test_unparseable_token_is_treated_as_unusable():
    # Assuming a malformed credential works would fail at publish time instead.
    s = vp.token_status("not-a-jwt")
    assert s["expired"] is True


# ── publish_summary guard rails ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_expired_credential_is_reported_not_silently_dry_run(monkeypatch):
    monkeypatch.setattr(vp.settings, "vocus_id_token", _token(-60), raising=False)
    monkeypatch.setattr(vp.settings, "vocus_user_id", "u1", raising=False)
    result = await vp.publish_summary("ep1", "T", "# 標題\n\n內容", dry_run=False)
    assert result["posted"] is False
    assert result["reason"] == "credential_expired"


@pytest.mark.asyncio
async def test_blank_summary_never_creates_an_empty_article(monkeypatch):
    monkeypatch.setattr(vp.settings, "vocus_id_token", _token(3600), raising=False)
    monkeypatch.setattr(vp.settings, "vocus_user_id", "u1", raising=False)
    result = await vp.publish_summary("ep1", "T", "   ", dry_run=False)
    assert result["posted"] is False and result["reason"] == "no_summary_content"


@pytest.mark.asyncio
async def test_dry_run_reports_a_preview_without_posting(monkeypatch):
    monkeypatch.setattr(vp.settings, "vocus_id_token", _token(3600), raising=False)
    monkeypatch.setattr(vp.settings, "vocus_user_id", "u1", raising=False)
    result = await vp.publish_summary("ep1", "T", "# 標題\n\n內容", dry_run=True)
    assert result["posted"] is False and result["reason"] == "dry_run"
    assert result["preview"]["block_count"] >= 2
    assert result["preview"]["canonical_url"].endswith("/episode/ep1")


@pytest.mark.asyncio
async def test_a_401_mid_flight_surfaces_as_credential_expired(monkeypatch):
    monkeypatch.setattr(vp.settings, "vocus_id_token", _token(3600), raising=False)
    monkeypatch.setattr(vp.settings, "vocus_user_id", "u1", raising=False)

    async def _401(self, method, url, **kw):
        return httpx.Response(401, request=httpx.Request(method, url))

    monkeypatch.setattr(httpx.AsyncClient, "request", _401)
    result = await vp.publish_summary("ep1", "T", "# 標題\n\n內容", dry_run=False)
    assert result["posted"] is False and result["reason"] == "credential_expired"


@pytest.mark.asyncio
async def test_writes_that_succeed_but_do_not_go_public_are_not_reported_as_posted(monkeypatch):
    """The status integer is inferred. If vocus accepts every write but the article is
    still not public, that must surface — never as a success."""
    monkeypatch.setattr(vp.settings, "vocus_id_token", _token(3600), raising=False)
    monkeypatch.setattr(vp.settings, "vocus_user_id", "u1", raising=False)

    async def _ok(self, method, url, **kw):
        req = httpx.Request(method, url)
        if method == "GET":
            # Read-back says it is still a draft.
            return httpx.Response(200, json={"status": vp.STATUS_DRAFT}, request=req)
        return httpx.Response(200, json={"_id": "art123"}, request=req)

    monkeypatch.setattr(httpx.AsyncClient, "request", _ok)
    result = await vp.publish_summary("ep1", "T", "# 標題\n\n內容", dry_run=False)
    assert result["posted"] is False
    assert result["reason"] == "publish_unverified"
    assert result["article_id"] == "art123"


@pytest.mark.asyncio
async def test_a_verified_publish_reports_posted_with_the_article_url(monkeypatch):
    monkeypatch.setattr(vp.settings, "vocus_id_token", _token(3600), raising=False)
    monkeypatch.setattr(vp.settings, "vocus_user_id", "u1", raising=False)

    async def _ok(self, method, url, **kw):
        req = httpx.Request(method, url)
        if method == "GET":
            return httpx.Response(200, json={"status": vp.STATUS_PUBLIC}, request=req)
        return httpx.Response(200, json={"_id": "art123"}, request=req)

    monkeypatch.setattr(httpx.AsyncClient, "request", _ok)
    result = await vp.publish_summary("ep1", "T", "# 標題\n\n內容", dry_run=False)
    assert result["posted"] is True
    assert result["url"] == "https://vocus.cc/article/art123"


def test_a_rotated_token_takes_effect_without_a_restart(monkeypatch):
    """The whole point of the live GSM read: replacing the weekly token must not
    require redeploying the backend."""
    monkeypatch.setattr(vp.settings, "vocus_id_token", _token(-60), raising=False)  # stale boot value
    fresh = _token(6 * 24 * 3600)
    monkeypatch.setattr(vp, "_fetch_token_from_gsm", lambda: fresh)
    vp._token_cache = None

    assert vp.current_token() == fresh
    assert vp.token_status()["expired"] is False


def test_boot_time_value_is_used_when_secret_manager_is_unreachable(monkeypatch):
    monkeypatch.setattr(vp.settings, "vocus_id_token", _token(3600), raising=False)
    monkeypatch.setattr(vp, "_fetch_token_from_gsm", lambda: None)
    vp._token_cache = None

    assert vp.token_status()["expired"] is False
