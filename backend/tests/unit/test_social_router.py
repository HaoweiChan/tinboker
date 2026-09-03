"""Unit tests for the admin Social router helpers.

The publish/generate endpoints are thin wrappers over already-tested code
(threads_publisher.publish_episode / facebook_publisher.publish_episode and the
pipeline's social-copy endpoint). These tests lock the new router-local logic:
platform parsing/validation and the per-platform posted + readiness mapping the
admin list and editor badges rely on.
"""
import pytest
from fastapi import HTTPException

from src.models.podcast import Episode
from src.routers import social


def _ep(ep_id="EP1", **kw) -> Episode:
    return Episode(
        id=ep_id, podcast_name="股癌", episode_title=kw.get("title", "本集重點"),
        social_thread=kw.get("social_thread"), social_cards=kw.get("social_cards") or [],
        created_time=1, released_at_ms=kw.get("released_ms", 1),
    )


def test_parse_platforms_normalizes_case_and_whitespace():
    assert social._parse_platforms("Threads, FACEBOOK ") == ["threads", "facebook"]


def test_parse_platforms_rejects_unknown():
    with pytest.raises(HTTPException) as e:
        social._parse_platforms("threads,tiktok")
    assert e.value.status_code == 422


def test_parse_platforms_rejects_empty():
    with pytest.raises(HTTPException) as e:
        social._parse_platforms(" , ")
    assert e.value.status_code == 422


def test_social_list_item_reports_copy_images_and_posted():
    ep = _ep(
        "EP9",
        social_thread={"post": "hi", "comments": [{"heading": "a", "text": "x"}, {"heading": "b", "text": ""}]},
        social_cards=[{"kind": "theme", "title": "a", "image_url": "u"}, {"kind": "cover", "title": "c"}],
    )
    item = social._social_list_item(ep, {"threads": {"EP9"}, "facebook": set()})
    assert item["has_copy"] is True
    assert item["comment_count"] == 1          # only the non-empty comment counts
    assert item["theme_card_count"] == 1       # cover excluded
    assert item["has_images"] is True
    assert item["posted"] == {"threads": True, "facebook": False}


def test_social_list_item_empty_when_no_copy_or_cards():
    item = social._social_list_item(_ep("EP10"), {"threads": set(), "facebook": set()})
    assert item["has_copy"] is False
    assert item["has_images"] is False
    assert item["posted"] == {"threads": False, "facebook": False}


def test_posted_status_reads_both_ledgers(monkeypatch):
    monkeypatch.setattr(social.threads_publisher, "already_posted", lambda eid: eid == "EPX")
    monkeypatch.setattr(social.facebook_publisher, "already_posted", lambda eid: False)
    assert social._posted_status("EPX") == {"threads": True, "facebook": False}


@pytest.mark.asyncio
async def test_syndicate_passes_publish_substack_through(monkeypatch):
    """The pipeline has sent publish_substack=true since Step 5f shipped; the endpoint
    used to drop the unknown query param silently, leaving every episode a draft."""
    seen = {}

    async def _fake_get_episode(episode_id):
        return _ep(episode_id)

    async def _fake_substack(episode_id, title, summary, **kw):
        seen.update(kw)
        return {"platform": "substack", "posted": True}

    monkeypatch.setattr(social.podcast_service, "get_episode_admin", _fake_get_episode)
    monkeypatch.setattr(social.substack_publisher, "create_summary_draft", _fake_substack)
    monkeypatch.setattr(social, "_public_base_url", lambda request: "https://api.test")

    await social.syndicate_episode(
        "EP1", request=None, platforms="substack",
        dry_run=True, publish=False, publish_substack=True, _=None,
    )
    assert seen["publish"] is True
    assert seen["send_email"] is False


@pytest.mark.asyncio
async def test_syndicate_skips_show_with_publishing_disabled(monkeypatch):
    """A muted show is skipped before either syndication target is contacted."""
    calls = []

    async def _fake_get_episode(episode_id):
        return _ep(episode_id)

    async def _boom(*a, **kw):
        calls.append(a)
        return {"posted": True}

    monkeypatch.setattr(social.podcast_service, "get_episode_admin", _fake_get_episode)
    monkeypatch.setattr(social.substack_publisher, "create_summary_draft", _boom)
    monkeypatch.setattr(social.vocus_publisher, "publish_summary", _boom)
    monkeypatch.setattr(social, "social_enabled_for", lambda name: False)
    monkeypatch.setattr(social, "_public_base_url", lambda request: "https://api.test")

    result = await social.syndicate_episode(
        "EP1", request=None, platforms="vocus,substack",
        dry_run=False, publish=True, publish_substack=True, _=None,
    )
    assert calls == []
    assert {p: r["reason"] for p, r in result["platforms"].items()} == {
        "vocus": "social_disabled_for_show",
        "substack": "social_disabled_for_show",
    }
