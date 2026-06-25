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


# --- on-demand card render (PodcastService.render_social_card_pngs) -----------

import hashlib
from types import SimpleNamespace

from src.services.podcast import PodcastService

_DECK = "---\nmarp: true\n---\n<style>\nsection{x:1}\n</style>\n\n# A\n\n---\n\n## B\n"


def _svc(monkeypatch, *, images, cards, deck=_DECK):
    """A PodcastService with all I/O stubbed; returns (svc, sink) where sink
    collects the social_cards written back to Firestore."""
    svc = object.__new__(PodcastService)  # skip __init__ (no GCP/Firestore needed)
    sink: dict = {}

    ep = SimpleNamespace(id="EP1", podcast_name="股癌", marp_markdown_content=deck, social_cards=cards)

    async def _get_admin(eid, *a, **k):
        return ep
    svc.get_episode_admin = _get_admin
    svc.firestore_service = SimpleNamespace(
        get_document=lambda col, eid: {"social_cards": [dict(c) for c in cards]},
        set_document=lambda col, eid, data, merge: sink.update(data),
    )

    async def _upload(bucket, path, data, ctype):
        return f"https://cdn/{path}"
    svc.gcs = SimpleNamespace(upload_bytes_public=_upload)

    async def _noop(*a, **k):
        return None
    svc._invalidate_episode_cache = _noop
    svc._purge_api_host_cdn = _noop

    class _Resp:
        def raise_for_status(self): pass
        def json(self): return {"success": True, "images": images}

    class _Client:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, *a, **k): return _Resp()

    monkeypatch.setattr("src.services.podcast.httpx.AsyncClient", _Client)
    return svc, sink


@pytest.mark.asyncio
async def test_render_cards_stamps_cachebusted_urls_in_order(monkeypatch):
    cards = [{"kind": "cover"}, {"kind": "theme"}]
    svc, sink = _svc(monkeypatch, images=["IMG0", "IMG1"], cards=cards)
    await svc.render_social_card_pngs("EP1")
    written = sink["social_cards"]
    assert written[0]["image_url"] == f"https://cdn/social_cards/EP1/0.png?v={hashlib.md5(b'IMG0').hexdigest()[:10]}"
    assert written[1]["image_url"] == f"https://cdn/social_cards/EP1/1.png?v={hashlib.md5(b'IMG1').hexdigest()[:10]}"


@pytest.mark.asyncio
async def test_render_cards_refuses_count_mismatch(monkeypatch):
    # One PNG for two cards must NOT desync the carousel — hard error, no write.
    svc, sink = _svc(monkeypatch, images=["IMG0"], cards=[{"kind": "cover"}, {"kind": "theme"}])
    with pytest.raises(HTTPException) as e:
        await svc.render_social_card_pngs("EP1")
    assert e.value.status_code == 500
    assert sink == {}


@pytest.mark.asyncio
async def test_render_cards_requires_inline_theme(monkeypatch):
    svc, _ = _svc(monkeypatch, images=["IMG0"], cards=[{"kind": "cover"}], deck="# no style block")
    with pytest.raises(HTTPException) as e:
        await svc.render_social_card_pngs("EP1")
    assert e.value.status_code == 409
