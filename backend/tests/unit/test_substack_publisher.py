"""Substack draft staging.

The shapes asserted here are the ones the live API actually accepted; each was found by
being rejected first, so they are pinned rather than assumed.
"""
import httpx
import pytest

from src.services import substack_publisher as sp


def _client(handler):
    transport = httpx.MockTransport(handler)
    return httpx.AsyncClient(transport=transport)


@pytest.mark.asyncio
async def test_create_sends_bylines_as_objects_and_body_as_a_string():
    """A bare list of ids is rejected with ``draft_bylines[0].id: Invalid value``, and an
    object draft_body is rejected too — both cost a round trip to discover."""
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json
        seen.update(json.loads(request.content))
        return httpx.Response(200, json={"id": 42})

    client = sp.SubstackClient(sid="x", subdomain="tinboker", user_id=7)
    async with _client(handler) as http:
        assert await client.create_draft(http, {"type": "doc", "content": []}) == 42

    assert seen["draft_bylines"] == [{"id": 7, "is_guest": False}]
    assert isinstance(seen["draft_body"], str)


@pytest.mark.asyncio
async def test_an_expired_cookie_is_reported_rather_than_retried():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, text="forbidden")

    client = sp.SubstackClient(sid="stale", subdomain="tinboker", user_id=7)
    async with _client(handler) as http:
        with pytest.raises(sp.SubstackError, match="credential_expired"):
            await client.create_draft(http, {"type": "doc", "content": []})


@pytest.mark.asyncio
async def test_api_errors_carry_the_response_body():
    """`http_400` alone tells you nothing against an undocumented API."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text='{"errors":[{"param":"draft_bylines"}]}')

    client = sp.SubstackClient(sid="x", subdomain="tinboker", user_id=7)
    async with _client(handler) as http:
        with pytest.raises(sp.SubstackError, match="draft_bylines"):
            await client.create_draft(http, {"type": "doc", "content": []})


@pytest.mark.asyncio
async def test_unconfigured_reports_instead_of_calling_out():
    result = await sp.create_summary_draft("EP1", "標題", "內文", dry_run=False)
    if result["configured"]:
        pytest.skip("Substack is configured in this environment")
    assert result["posted"] is False
    assert result["reason"] == "not_configured"


def test_draft_url_points_at_the_editor_not_the_public_post():
    """The operator's next action is reviewing and publishing, so the link is the editor."""
    assert sp.draft_url("tinboker", 42) == "https://tinboker.substack.com/publish/post/42"


@pytest.mark.asyncio
async def test_the_draft_limit_is_clamped_to_what_the_api_accepts():
    """Probed live: limit=49 is accepted, limit=50 is rejected with "Invalid value". An
    exclusive max, so a caller asking for more gets clamped instead of a 400."""
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["limit"] = request.url.params.get("limit")
        return httpx.Response(200, json=[])

    client = sp.SubstackClient(sid="x", subdomain="tinboker", user_id=7)
    async with _client(handler) as http:
        await client.draft_ids(http, limit=500)
    assert seen["limit"] == str(sp.MAX_DRAFT_LIMIT)
