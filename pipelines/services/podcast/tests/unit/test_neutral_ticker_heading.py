"""Neutral mentions retain company context without recommendation framing."""
import copy

import pytest
from src.podcast.content_builder.nodes import social_cards_builder as sc
from src.podcast.content_builder.nodes.marp_converter import convert_marp, convert_marp_ticker


@pytest.fixture(autouse=True)
def no_registry_network(monkeypatch):
    monkeypatch.setattr(sc, "prime_tickers", lambda *args: None)
    monkeypatch.setattr(sc, "_ticker_name_code", lambda ticker: (ticker, ticker))


@pytest.mark.parametrize("converter,key", [
    (convert_marp, "marp_markdown"), (convert_marp_ticker, "ticker_marp_markdown"),
])
@pytest.mark.parametrize("scores,expected", [
    ([0.5, 0.5], "本期提及公司與態度"),
    (["0.5"], "本期提及公司與態度"),
    ([0.5, 0.8], "本期精選標的與態度"),
    ([0.5, 0.2], "本期精選標的與態度"),
    ([0.5] * 8 + [0.8], "本期精選標的與態度"),
    ([0], "本期精選標的與態度"),
    ([None], "本期精選標的與態度"),
    (["unknown"], "本期精選標的與態度"),
    ([], None),
])
def test_neutral_heading_in_both_actual_decks(converter, key, scores, expected):
    state = {
        "episode_title": "Episode", "source": "Any podcast",
        "marp_slides": {"slides": [{"heading": "Context", "bullet_points": ["Keep original context"]}]},
        "ticker_insights": {"ticker_recommendations": [
            {"ticker": f"T{i}", "sentiment_score": score, "risks": [],
             "reasons": [{"description": "Original company context", "start_time": 1000}]}
            for i, score in enumerate(scores)
        ]},
    }
    original = copy.deepcopy(state)
    markdown = converter(state)[key]
    if expected:
        assert expected in markdown
        other = "本期精選標的與態度" if expected == "本期提及公司與態度" else "本期提及公司與態度"
        assert other not in markdown
        assert "Original company context" in markdown
    else:
        assert "本期提及公司與態度" not in markdown
        assert "本期精選標的與態度" not in markdown
        if key == "ticker_marp_markdown":
            assert markdown == ""
        else:
            assert "Keep original context" in markdown
    assert state == original
