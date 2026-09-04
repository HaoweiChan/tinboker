"""One episode, one vocus article and one Substack post — forever.

Neither platform dedupes: every call mints a fresh article. The shared Postgres ledger
is the only thing that stops a second copy, and it has to work *across environments* —
dev, staging and production run the same publishing credentials, which is how vocus
ended up with three duplicate pairs whose only difference was an ``api.`` versus
``staging-api.`` cover URL.
"""

import pytest

from src.routers.social import _syndicate_once
from src.services import social_ledger


def _ok(**extra):
    async def run():
        return {"platform": "vocus", "posted": True, "article_id": "a1",
                "url": "https://vocus.cc/article/a1", **extra}
    return run


@pytest.mark.asyncio
async def test_the_second_call_is_refused_and_points_at_the_first(temp_db):
    first = await _syndicate_once("vocus", "EP1", _ok(), dry_run=False)
    assert first["posted"] is True

    second = await _syndicate_once("vocus", "EP1", _ok(), dry_run=False)
    assert second["posted"] is False
    assert second["reason"] == "already_syndicated"
    assert second["url"] == "https://vocus.cc/article/a1"


@pytest.mark.asyncio
async def test_a_refused_call_never_reaches_the_platform(temp_db):
    await _syndicate_once("substack", "EP2", _ok(), dry_run=False)
    calls = []

    async def run():
        calls.append(1)
        return {"posted": True, "draft_id": 7}

    await _syndicate_once("substack", "EP2", run, dry_run=False)
    assert calls == [], "the publisher must not be called at all — it would create a post"


@pytest.mark.asyncio
async def test_the_two_platforms_are_tracked_apart(temp_db):
    await _syndicate_once("vocus", "EP3", _ok(), dry_run=False)

    async def substack():
        return {"posted": True, "draft_id": 42, "url": "https://x.substack.com/p/y"}

    assert (await _syndicate_once("substack", "EP3", substack, dry_run=False))["posted"] is True


@pytest.mark.asyncio
async def test_a_failed_publish_releases_the_claim(temp_db):
    async def nothing_created():
        return {"posted": False, "reason": "credential_expired"}

    await _syndicate_once("vocus", "EP4", nothing_created, dry_run=False)
    # Nothing exists on the platform, so the next run must be free to try again.
    assert social_ledger.already_posted("vocus", "EP4") is False
    assert (await _syndicate_once("vocus", "EP4", _ok(), dry_run=False))["posted"] is True


@pytest.mark.asyncio
async def test_a_raising_publisher_releases_the_claim(temp_db):
    async def boom():
        raise RuntimeError("network gone")

    with pytest.raises(RuntimeError):
        await _syndicate_once("vocus", "EP5", boom, dry_run=False)
    assert social_ledger.already_posted("vocus", "EP5") is False


@pytest.mark.asyncio
async def test_an_unverified_publish_still_counts_as_created(temp_db):
    """vocus reports posted=False when the read-back cannot confirm the article is
    public — but the article exists. Releasing that claim would mint the duplicate."""
    async def unverified():
        return {"posted": False, "reason": "publish_unverified",
                "article_id": "a9", "url": "https://vocus.cc/article/a9"}

    await _syndicate_once("vocus", "EP6", unverified, dry_run=False)
    assert social_ledger.already_posted("vocus", "EP6") is True


@pytest.mark.asyncio
async def test_a_dry_run_claims_nothing(temp_db):
    """It converts and reports; nothing reaches the platform, so it must not burn the
    one claim the real publish needs."""
    async def dry():
        return {"posted": False, "reason": "dry_run"}

    await _syndicate_once("vocus", "EP7", dry, dry_run=True)
    assert social_ledger.already_posted("vocus", "EP7") is False
