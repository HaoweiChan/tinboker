"""What the cover says it is, versus what the post is called."""
from unittest import mock

import pytest

from src.routers import og as og_router


class _Ep:
    podcast_name = "Gooaye 股癌"
    episode_title = "EP684 | 🔦"


@pytest.mark.asyncio
async def test_the_cover_carries_the_same_title_the_post_gets():
    """Built from episode_title directly, the cover read "EP684 | 🔦" while the post was
    "股癌 EP684 | 🔦 摘要" — two names for one thing, from two code paths."""
    captured = {}

    def _svg(title, kicker="", **kw):
        captured.update(title=title, kicker=kicker)
        return "<svg/>"

    with mock.patch.object(og_router.podcast_service, "get_episode_admin",
                           new=mock.AsyncMock(return_value=_Ep())), \
         mock.patch.object(og_router, "_cover_data_uri", new=mock.AsyncMock(return_value="")), \
         mock.patch.object(og_router, "episode_cover_svg", side_effect=_svg):
        await og_router._episode_svg("EP1")

    assert captured["title"] == "EP684 | 🔦 摘要"
    assert captured["kicker"] == "股癌"


@pytest.mark.asyncio
async def test_the_show_name_is_not_printed_twice():
    """The kicker already shows it; repeating it in the title line reads as a stutter."""
    captured = {}

    def _svg(title, kicker="", **kw):
        captured.update(title=title, kicker=kicker)
        return "<svg/>"

    with mock.patch.object(og_router.podcast_service, "get_episode_admin",
                           new=mock.AsyncMock(return_value=_Ep())), \
         mock.patch.object(og_router, "_cover_data_uri", new=mock.AsyncMock(return_value="")), \
         mock.patch.object(og_router, "episode_cover_svg", side_effect=_svg):
        await og_router._episode_svg("EP1")

    assert not captured["title"].startswith(captured["kicker"])
