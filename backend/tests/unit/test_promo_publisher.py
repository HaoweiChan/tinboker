"""Per-platform media rules for free-form promo posts.

Threads may mix images+videos in a carousel; Facebook cannot mix types or carry
multiple videos. These pin the planning logic so a refactor can't silently let a
Facebook mixed-media post through (the product decision is to block it).
"""
import pytest

from src.services.facebook_service import FACEBOOK_MAX_ALBUM
from src.services.promo_publisher import (
    THREADS_MAX_MEDIA,
    PromoError,
    plan_facebook,
    plan_threads,
    publish_promo,
)
from src.services.threads_service import THREADS_MAX_CHARS

IMG = {"type": "image", "url": "https://x/i.jpg"}
VID = {"type": "video", "url": "https://x/v.mp4"}


def test_threads_shapes():
    assert plan_threads("hi", [])["kind"] == "text"
    assert plan_threads("", [IMG])["kind"] == "single"
    assert plan_threads("", [IMG, VID])["kind"] == "carousel"  # mixed allowed on Threads


@pytest.mark.parametrize("call,reason", [
    (lambda: plan_threads("", []), "empty"),
    (lambda: plan_threads("x" * (THREADS_MAX_CHARS + 1), [IMG]), "text_too_long"),
    (lambda: plan_threads("", [IMG] * (THREADS_MAX_MEDIA + 1)), "too_many_media"),
])
def test_threads_rejections(call, reason):
    with pytest.raises(PromoError, match=reason):
        call()


def test_facebook_shapes():
    assert plan_facebook("hi", [])["kind"] == "text"
    assert plan_facebook("", [IMG])["kind"] == "photo"
    assert plan_facebook("", [IMG, IMG])["kind"] == "album"
    assert plan_facebook("", [VID])["kind"] == "video"


@pytest.mark.parametrize("call,reason", [
    (lambda: plan_facebook("", [IMG, VID]), "fb_mixed_media"),      # the headline rule
    (lambda: plan_facebook("", [VID, VID]), "fb_multiple_videos"),
    (lambda: plan_facebook("", [IMG] * (FACEBOOK_MAX_ALBUM + 1)), "fb_too_many_photos"),
])
def test_facebook_rejections(call, reason):
    with pytest.raises(PromoError, match=reason):
        call()


async def test_publish_dry_run_is_independent_per_platform():
    """A FB mixed-media block must not stop Threads; unconfigured → forced dry-run."""
    out = await publish_promo("promo!", [IMG, VID], ["threads", "facebook"], dry_run=True)
    th = out["platforms"]["threads"]
    fb = out["platforms"]["facebook"]
    assert th["posted"] is False and th["reason"] == "dry_run" and th["plan"] == "carousel"
    # Facebook is blocked on the mix regardless of dry-run/credentials.
    assert fb["posted"] is False and fb["reason"] == "fb_mixed_media"


async def test_comments_counted_and_blank_dropped():
    out = await publish_promo("hi", [], ["threads", "facebook"], comments=["a", "  ", "b"], dry_run=True)
    assert out["platforms"]["threads"]["comment_count"] == 2  # blank dropped
    assert out["platforms"]["facebook"]["comment_count"] == 2


async def test_threads_overlong_comment_blocked_even_in_dry_run():
    out = await publish_promo("hi", [], ["threads"], comments=["x" * (THREADS_MAX_CHARS + 1)], dry_run=True)
    assert out["platforms"]["threads"]["reason"] == "comment_too_long"
