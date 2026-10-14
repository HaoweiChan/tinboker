"""Native names must not depend on whether the main deck rendered first."""
import copy

from shared import tickers
from src.podcast.content_builder.nodes.marp_converter import convert_marp, convert_marp_ticker


def test_ticker_deck_cold_and_warm_use_same_native_names(monkeypatch):
    monkeypatch.setattr(tickers, "fetch_translation_aliases", lambda: [])
    calls = []

    def batch(symbols):
        calls.append(set(symbols))
        return [{"ticker": "00991A", "name_zh_tw": "主動復華未來50", "market": "TW"}]

    monkeypatch.setattr(tickers, "fetch_translations_batch", batch)
    old_primed = set(tickers._PRIMED)
    tickers._index.cache_clear()
    tickers._PRIMED.clear()
    state = {"episode_title": "Test", "source": "Any show", "related_tickers": ["00991A"],
             "marp_slides": {"slides": [{"heading": "Context", "bullet_points": ["Original theme"]}]},
             "ticker_insights": {"ticker_recommendations": [{"ticker": "00991A", "sentiment_score": 0.5,
                 "reasons": [{"description": "Original company context", "start_time": 1000}], "risks": []}]}}
    original = copy.deepcopy(state)
    try:
        cold = convert_marp_ticker(state)["ticker_marp_markdown"]
        main = convert_marp(state)["marp_markdown"]
        warm = convert_marp_ticker(state)["ticker_marp_markdown"]
        assert cold == warm
        assert "主動復華未來50" in cold and "主動復華未來50" in main
        assert "Original company context" in cold and "Original company context" in main
        assert calls == [{"00991A"}]
        assert state == original
    finally:
        tickers._index.cache_clear()
        tickers._PRIMED.clear()
        tickers._PRIMED.update(old_primed)
