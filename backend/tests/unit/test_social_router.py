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


def test_poll_edit_rejects_duplicate_choices():
    with pytest.raises(ValueError, match="distinct"):
        social.SocialPoll(question="選哪個？", options=["AI", " ai "])


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


@pytest.mark.asyncio
async def test_social_editor_keeps_bad_stored_poll_editable(monkeypatch):
    ep = _ep("EP_BAD", social_thread={"post": "保留的原文", "poll": {"question": "問題？", "options": ["只有一個"]}})
    monkeypatch.setattr(social.podcast_service, "get_episode_admin", lambda _: _return(ep))
    monkeypatch.setattr(social, "_posted_status", lambda _: {"threads": False, "facebook": False})
    bundle = await social.get_social_episode("EP_BAD", _=None)
    assert bundle["post"] == "保留的原文"
    assert bundle["poll"] is None
    assert bundle["poll_error"] == "invalid_social_poll"
    assert bundle["composed"]["main_text"] == ""


async def _return(value):
    return value


@pytest.mark.asyncio
async def test_social_copy_patch_preserves_omitted_poll_and_clears_explicit_null(monkeypatch):
    existing = _ep("EP_PATCH", social_thread={
        "post": "舊文", "poll": {"question": "仍投票？", "options": ["是", "否"]},
        "poll_error": "invalid_poll", "link_hook": "原始來源", "focus_ms": 2000,
    })
    saved = []

    async def get_episode(_):
        return existing

    async def set_thread(_, thread):
        saved.append(thread)
        return existing.model_copy(update={"social_thread": thread})

    monkeypatch.setattr(social.podcast_service, "get_episode_admin", get_episode)
    monkeypatch.setattr(social.podcast_service, "set_social_thread", set_thread)
    await social.save_social_episode("EP_PATCH", social.SocialThreadPatch(post="新文"), _=None)
    assert saved[-1]["poll"]["question"] == "仍投票？"
    assert saved[-1]["poll_error"] == "invalid_poll"
    assert saved[-1]["focus_ms"] == 2000
    await social.save_social_episode("EP_PATCH", social.SocialThreadPatch(post="一般貼文", poll=None), _=None)
    assert "poll" not in saved[-1] and "poll_error" not in saved[-1]


def test_posted_status_reads_both_ledgers(monkeypatch):
    monkeypatch.setattr(social.threads_publisher, "already_posted", lambda eid: eid == "EPX")
    monkeypatch.setattr(social.facebook_publisher, "already_posted", lambda eid: False)
    assert social._posted_status("EPX") == {"threads": True, "facebook": False}


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
    monkeypatch.setattr(social.vocus_publisher, "publish_summary", _boom)
    monkeypatch.setattr(social, "social_enabled_for", lambda name: False)
    monkeypatch.setattr(social, "_public_base_url", lambda request: "https://api.test")
    monkeypatch.setattr(social.settings, "episode_syndication_platforms", "vocus")
    monkeypatch.setattr(social.settings, "syndicate_max_age_days", 0)

    result = await social.syndicate_episode(
        "EP1", request=None, platforms="vocus",
        dry_run=False, publish=True, _=None,
    )
    assert calls == []
    assert {p: r["reason"] for p, r in result["platforms"].items()} == {
        "vocus": "social_disabled_for_show",
    }


@pytest.mark.asyncio
async def test_syndicate_is_off_by_default_since_the_daily_digest(monkeypatch):
    """Per-episode summaries stopped going out on 2026-09-13; the nightly 每日精選 replaced
    them. With the default (empty) policy every platform reports the switch, the episode
    is still looked up (a 404 stays a 404), and no publisher is contacted."""
    calls = []

    async def _fake_get_episode(episode_id):
        return _ep(episode_id)

    async def _boom(*a, **kw):
        calls.append(a)
        return {"posted": True}

    monkeypatch.setattr(social.podcast_service, "get_episode_admin", _fake_get_episode)
    monkeypatch.setattr(social.vocus_publisher, "publish_summary", _boom)
    monkeypatch.setattr(social.settings, "episode_syndication_platforms", "")
    monkeypatch.setattr(social.settings, "syndicate_max_age_days", 0)

    result = await social.syndicate_episode(
        "EP1", request=None, platforms="vocus",
        dry_run=False, publish=True, _=None,
    )
    assert calls == []
    assert {p: r["reason"] for p, r in result["platforms"].items()} == {
        "vocus": "episode_syndication_disabled",
    }


@pytest.mark.asyncio
async def test_syndicate_refuses_old_episodes_unless_allow_old(monkeypatch):
    """On 2026-09-04 a backfill reached this endpoint before the pipeline had an age gate
    and 817 episodes from 2021-2025 went out as new. The endpoint now checks the true
    release date itself; unknown age counts as old."""
    import time as _t
    calls = []

    async def _boom(*a, **kw):
        calls.append(a)
        return {"platform": "vocus", "posted": True, "article_id": "x"}

    monkeypatch.setattr(social.vocus_publisher, "publish_summary", _boom)
    monkeypatch.setattr(social, "_public_base_url", lambda request: "https://api.test")
    monkeypatch.setattr(social.settings, "episode_syndication_platforms", "vocus")
    monkeypatch.setattr(social.settings, "syndicate_max_age_days", 7)

    old_ms = int((_t.time() - 400 * 86400) * 1000)
    fresh_ms = int((_t.time() - 2 * 86400) * 1000)

    async def _old(episode_id):
        return _ep(episode_id, released_ms=old_ms)

    monkeypatch.setattr(social.podcast_service, "get_episode_admin", _old)
    r = await social.syndicate_episode("EP1", request=None, platforms="vocus", dry_run=True, publish=False, allow_old=False, _=None)
    assert r["platforms"]["vocus"]["reason"] == "too_old" and r["platforms"]["vocus"]["age_days"] > 399
    assert calls == []
    r = await social.syndicate_episode("EP1", request=None, platforms="vocus", dry_run=True, publish=False, allow_old=True, _=None)
    assert r["platforms"]["vocus"]["posted"] is True and len(calls) == 1

    async def _fresh(episode_id):
        return _ep(episode_id, released_ms=fresh_ms)

    monkeypatch.setattr(social.podcast_service, "get_episode_admin", _fresh)
    r = await social.syndicate_episode("EP1", request=None, platforms="vocus", dry_run=True, publish=False, allow_old=False, _=None)
    assert r["platforms"]["vocus"]["posted"] is True

    async def _unknown(episode_id):
        return _ep(episode_id, released_ms=None)

    monkeypatch.setattr(social.podcast_service, "get_episode_admin", _unknown)
    r = await social.syndicate_episode("EP1", request=None, platforms="vocus", dry_run=True, publish=False, allow_old=False, _=None)
    assert r["platforms"]["vocus"]["reason"] == "too_old" and r["platforms"]["vocus"]["age_days"] is None
