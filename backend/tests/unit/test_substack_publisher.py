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


@pytest.mark.asyncio
async def test_draft_ids_reads_the_posts_key_the_api_actually_returns():
    """The response is {posts, hasMore, nextCursor}. Reading "drafts" instead returned an
    empty list on every call, with a 200 and no error — a cleanup pass silently deleted
    nothing at all."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"posts": [{"id": 1}, {"id": 2}],
                                         "hasMore": False, "nextCursor": None})

    client = sp.SubstackClient(sid="x", subdomain="tinboker", user_id=7)
    async with _client(handler) as http:
        assert await client.draft_ids(http) == [1, 2]


@pytest.mark.asyncio
async def test_a_saved_draft_is_never_primed_to_mail_the_list():
    """A created draft carries should_send_email=True. Left alone, whoever clicks Publish
    mails every subscriber without choosing to — so the field is always sent explicitly."""
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json
        if request.method == "PUT":
            seen.update(json.loads(request.content))
        return httpx.Response(200, json={})

    client = sp.SubstackClient(sid="x", subdomain="tinboker", user_id=7)
    async with _client(handler) as http:
        await client.save_draft(http, 1, title="T", subtitle="S", doc={"type": "doc"})
    assert seen["should_send_email"] is False


@pytest.mark.asyncio
async def test_the_cover_and_seo_description_travel_with_the_draft():
    """Same cover as vocus, so one summary does not look like two things."""
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json
        if request.method == "PUT":
            seen.update(json.loads(request.content))
        return httpx.Response(200, json={})

    client = sp.SubstackClient(sid="x", subdomain="tinboker", user_id=7)
    async with _client(handler) as http:
        await client.save_draft(http, 1, title="T", subtitle="導言。", doc={"type": "doc"},
                                cover_image="https://api.test/og.svg", send_email=True)
    assert seen["cover_image"] == "https://api.test/og.svg"
    assert seen["search_engine_description"] == "導言。"
    assert seen["should_send_email"] is True


@pytest.mark.asyncio
async def test_no_cover_key_is_sent_when_there_is_no_cover():
    """Sending an empty string would blank an existing cover rather than leave it alone."""
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json
        if request.method == "PUT":
            seen.update(json.loads(request.content))
        return httpx.Response(200, json={})

    client = sp.SubstackClient(sid="x", subdomain="tinboker", user_id=7)
    async with _client(handler) as http:
        await client.save_draft(http, 1, title="T", subtitle="S", doc={"type": "doc"})
    assert "cover_image" not in seen


def test_the_image_node_matches_what_the_editor_writes():
    """Transcribed from a real insert, not guessed. Substack stores any node type without
    validating it — three guessed shapes were all accepted and then hung the editor when
    the draft was opened — so the only trustworthy source is what its own editor emits."""
    n = sp.image_node("https://substack-post-media.s3.amazonaws.com/x.png", 1200, 600, 61401)
    assert n["type"] == "captionedImage"
    inner = n["content"][0]
    assert inner["type"] == "image2"
    assert inner["attrs"]["src"].endswith("x.png")
    assert (inner["attrs"]["width"], inner["attrs"]["height"]) == (1200, 600)
    assert inner["attrs"]["bytes"] == 61401
    assert inner["attrs"]["type"] == "image/png"


@pytest.mark.asyncio
async def test_upload_returns_substacks_own_url():
    def handler(request: httpx.Request) -> httpx.Response:
        import json
        assert json.loads(request.content)["image"].startswith("data:image/png;base64,")
        return httpx.Response(200, json={"url": "https://substack-post-media.s3.amazonaws.com/a.png"})

    client = sp.SubstackClient(sid="x", subdomain="tinboker", user_id=7)
    async with _client(handler) as http:
        url = await client.upload_image(http, b"\x89PNG")
    assert url.endswith("a.png")


@pytest.mark.asyncio
async def test_an_upload_with_no_url_is_an_error_not_a_silent_pass():
    """A 200 carrying nothing usable is the failure mode this integration keeps hitting."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})

    client = sp.SubstackClient(sid="x", subdomain="tinboker", user_id=7)
    async with _client(handler) as http:
        with pytest.raises(sp.SubstackError, match="no_url"):
            await client.upload_image(http, b"\x89PNG")


@pytest.mark.asyncio
async def test_publishing_never_offers_a_way_to_email():
    """send_email is hard-wired False with no parameter to flip it. A newsletter cannot be
    recalled, so reaching it should take a code change and a review — not an env var
    somebody typo'd."""
    import inspect
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json
        if request.url.path.endswith("/publish"):
            seen.update(json.loads(request.content))
        return httpx.Response(200, json={})

    client = sp.SubstackClient(sid="x", subdomain="tinboker", user_id=7)
    async with _client(handler) as http:
        await client.publish_draft(http, 42)

    assert seen == {"send_email": False}
    assert "send_email" not in inspect.signature(sp.SubstackClient.publish_draft).parameters


@pytest.mark.asyncio
async def test_a_published_post_reports_the_reader_facing_url():
    """The editor link is right for a draft and wrong for something readers can open."""
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path.endswith("/publish"):
            return httpx.Response(200, json={})
        if request.method == "GET":
            return httpx.Response(200, json={"is_published": True, "slug": "ep684",
                                             "email_sent_at": None})
        return httpx.Response(200, json={"id": 42})

    import unittest.mock as mock
    real_client = httpx.AsyncClient   # captured before the patch, or the lambda recurses
    with mock.patch.object(sp.SubstackClient, "is_configured", return_value=True), \
         mock.patch("httpx.AsyncClient", lambda *a, **k: real_client(
             transport=httpx.MockTransport(handler))), \
         mock.patch.object(sp.settings, "substack_subdomain", "tinboker"), \
         mock.patch.object(sp.settings, "substack_sid", "s"), \
         mock.patch.object(sp.settings, "substack_user_id", 7):
        r = await sp.create_summary_draft("EP1", "T", "內文一段。", publish=True, dry_run=False)

    assert r["published"] is True
    assert r["emailed"] is False
    assert r["url"] == "https://tinboker.substack.com/p/ep684"


def test_the_public_url_falls_back_to_the_publication_without_a_slug():
    assert sp.public_url("tinboker", {"slug": "x"}) == "https://tinboker.substack.com/p/x"
    assert sp.public_url("tinboker", {}) == "https://tinboker.substack.com/"
