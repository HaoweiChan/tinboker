"""List endpoints return episode cards, not full episode records.

The tag, sector and stock pages render cards; shipping every episode's sector_exposures
with them made a 17-episode tag page 740 KB and a busy ticker's list 1.75 MB.
"""
import asyncio
import json

from src.models.podcast import CARD_UNUSED_FIELDS, Episode, card_dict
from src.routers import episodes as episodes_router
from src.routers import tags as tags_router


def _episode() -> Episode:
    return Episode(
        id="ep1", podcast_name="股癌", episode_title="EP1", created_time=1,
        related_tickers=["2330"], tags=["ai"], key_insights=["重點一"],
        sector_exposures=[{"exposure_id": "sector_mlcc", "resolved_tickers": [{"ticker": "2327"}]}],
        social_cards=[{"title": "card"}], spotify_description="long description",
    )


def test_card_dict_drops_only_the_unused_fields():
    card = card_dict(_episode())
    assert not CARD_UNUSED_FIELDS & card.keys()
    # What cards and the crawler body do read survives.
    assert card["id"] == "ep1" and card["related_tickers"] == ["2330"]
    assert card["tags"] == ["ai"] and card["key_insights"] == ["重點一"]
    # Already-dumped dicts (the by-sector service result) take the same trim.
    assert card_dict(_episode().model_dump(mode="json")) == card


def test_by_tag_returns_cards_unless_content_is_requested(monkeypatch):
    async def _by_tag(**kwargs):
        return [_episode()]

    monkeypatch.setattr(tags_router.podcast_service, "get_episodes_by_tag", _by_tag)
    monkeypatch.setattr(tags_router, "schedule_ticker_discovery", lambda eps: None)

    slim = asyncio.run(tags_router.get_episodes_by_tag(tag="ai", limit=50, offset=0, include_content=False))
    assert slim.total == 1 and "sector_exposures" not in slim.episodes[0]
    assert slim.episodes[0]["key_insights"] == ["重點一"]

    full = asyncio.run(tags_router.get_episodes_by_tag(tag="ai", limit=50, offset=0, include_content=True))
    assert full.episodes[0]["sector_exposures"][0]["exposure_id"] == "sector_mlcc"


def test_by_ticker_returns_cards_unless_content_is_requested(monkeypatch):
    async def _by_ticker(**kwargs):
        return [_episode()]

    monkeypatch.setattr(episodes_router.podcast_service, "get_episodes_by_ticker", _by_ticker)

    def call(include):
        res = asyncio.run(episodes_router.get_episodes_by_ticker(ticker="2330", limit=50, offset=0, include_content=include))
        return json.loads(res.body) if hasattr(res, "body") else json.loads(json.dumps(res, default=lambda o: o.model_dump(mode="json")))

    assert "sector_exposures" not in call(False)["episodes"][0]
    assert call(True)["episodes"][0]["sector_exposures"][0]["exposure_id"] == "sector_mlcc"


def test_by_sector_returns_cards(monkeypatch):
    async def _by_sector(**kwargs):
        return {"exposure_id": "sector_mlcc", "display_name": "MLCC", "exposure_type": "sector",
                "description": "d", "resolved_tickers": [], "total": 1,
                "episodes": [_episode().model_dump(mode="json")]}

    monkeypatch.setattr(tags_router.podcast_service, "get_episodes_by_sector", _by_sector)
    res = asyncio.run(tags_router.get_episodes_by_sector(exposure_id="sector_mlcc", limit=50, offset=0))
    assert "sector_exposures" not in res.episodes[0] and res.episodes[0]["id"] == "ep1"
