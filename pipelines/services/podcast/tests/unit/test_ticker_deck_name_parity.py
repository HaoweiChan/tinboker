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


def test_both_decks_prefer_episode_names_without_mutating_registry(monkeypatch):
    from src.podcast.content_builder.nodes import social_cards_builder as sc

    monkeypatch.setattr(sc, "prime_tickers", lambda symbols: None)
    monkeypatch.setattr("src.podcast.content_builder.nodes.marp_converter.prime_tickers", lambda symbols: None)
    monkeypatch.setattr(sc, "_ticker_name_code", lambda ticker: ("Native " + ticker, ticker))
    state = {"episode_title": "Episode", "source": "Any show",
             "writer_output": {"stock_tickers": [
                 {"symbol": "2883.TW", "display_name": " 凱基金 "},
                 {"symbol": "AMZN", "display_name": "   "},
                 {"symbol": "", "display_name": "Ignore"},
                 {"symbol": "META", "display_name": None},
             ]},
             "marp_slides": {"slides": [{"heading": "Context", "bullet_points": ["Keep theme"]}]},
             "ticker_insights": {"ticker_recommendations": [
                 {"ticker": symbol, "sentiment_score": 0.5, "risks": [],
                  "reasons": [{"description": "Keep reason", "start_time": 1000}]}
                 for symbol in ["2883", "AMZN", "META"]]}}
    original = copy.deepcopy(state)
    for converter, key in [(convert_marp, "marp_markdown"), (convert_marp_ticker, "ticker_marp_markdown")]:
        rendered = converter(state)[key]
        assert "凱基金" in rendered and "Native 2883" not in rendered
        assert "Native AMZN" in rendered and "Native META" in rendered
        assert "Keep reason" in rendered
        without_names = {**state, "writer_output": {}}
        assert "Native 2883" in converter(without_names)[key]
    assert state == original
