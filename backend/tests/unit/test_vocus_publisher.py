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
            # The public bucket does not contain our article.
            return httpx.Response(200, json={"articles": [{"_id": "someone-else"}]}, request=req)
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
            # Verification lists the status=2 bucket; ours is in it.
            return httpx.Response(200, json={"articles": [{"_id": "art123"}]}, request=req)
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


def test_lexical_and_command_logs_are_sent_as_json_strings():
    """vocus rejects an object here: `model.Draft.LexicalObj: ReadString: expects " or n,
    but found {`. Both the create and draft-save payloads hit this, so it is pinned."""
    import json as _json
    field = vp._lexical_field({"root": {"children": []}})
    assert isinstance(field, str)
    assert _json.loads(field)["root"]["children"] == []


@pytest.mark.asyncio
async def test_tags_are_sent_as_taginfo_objects_not_strings():
    """Two failure modes, only one of which is loud.

    A list of strings is rejected: "cannot unmarshal string into Go struct field
    Article.ArticleInfo.tags of type model.TagInfo". An object with the wrong keys is
    ACCEPTED with a 200 and silently stored as {"title": "", "totalScore": 0} — the
    wizard then shows blank chips and nothing anywhere reports a problem. An empty list
    unmarshals either way, which is how both survived every earlier smoke test."""
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json
        if request.method == "PATCH" and request.url.path.count("/") == 3:
            seen.update(json.loads(request.content))
        return httpx.Response(200, json={})

    client = vp.VocusClient(token="t", user_id="u", salon_id="s")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        await client.save_settings(http, "art1", title="T", abstract="A",
                                   canonical_url="https://tinboker.com/episode/EP1",
                                   tags=["股癌", "台股"])

    assert seen["tags"] == [{"title": "股癌"}, {"title": "台股"}]
    # newCategory is a model.BertClassify object; a bare id string is rejected with
    # "cannot unmarshal string into ... newCategory of type model.BertClassify".
    assert seen["newCategory"] == {"_id": vp.VOCUS_CATEGORY_ID,
                                   "title": vp.VOCUS_CATEGORY_TITLE, "score": 0}


@pytest.mark.asyncio
async def test_a_thumbnail_switches_the_cover_source_to_custom():
    """coverSource="article" makes vocus look for an image inside the body; our bodies have
    none, which is what left the vocus placeholder cover on the first real draft."""
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json
        if request.method == "PATCH":
            seen.update(json.loads(request.content))
        return httpx.Response(200, json={})

    client = vp.VocusClient(token="t", user_id="u", salon_id="s")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        await client.save_settings(http, "a", title="T", abstract="A",
                                   canonical_url="https://tinboker.com/episode/EP1",
                                   tags=[], thumbnail_url="https://img.test/cover.jpg")
    assert seen["thumbnailUrl"] == "https://img.test/cover.jpg"
    assert seen["coverSource"] == "custom"


@pytest.mark.asyncio
async def test_without_a_thumbnail_vocus_is_left_to_find_one():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json
        if request.method == "PATCH":
            seen.update(json.loads(request.content))
        return httpx.Response(200, json={})

    client = vp.VocusClient(token="t", user_id="u", salon_id="s")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        await client.save_settings(http, "a", title="T", abstract="A",
                                   canonical_url="https://tinboker.com/episode/EP1", tags=[])
    assert seen["coverSource"] == "article"
