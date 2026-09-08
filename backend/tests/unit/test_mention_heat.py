"""The mention-heat endpoint's contract: numerator and denominator share a population."""
import inspect

from src.routers import mentions


def test_the_ticker_and_market_series_come_from_one_call():
    """Two endpoints would let a caller divide counts from different populations.

    The chart plots share-of-attention, so the denominator has to be the same table,
    the same filter and the same window as the numerator.
    """
    body = inspect.getsource(mentions.get_mention_heat)
    assert '"series"' in body and '"market"' in body
    # both branches filter the same mention_type and the same lower bound
    assert body.count('ContentMention.mention_type == "ticker"') == 2
    assert body.count("ContentMention.mentioned_at >= since") == 2


def test_the_half_life_travels_with_the_data():
    """The client applies the decay; if it guesses the constant the two drift apart."""
    body = inspect.getsource(mentions.get_mention_heat)
    assert '"half_life_days": 7' in body


def test_the_window_is_bounded():
    """An unbounded look-back scans the whole table on a public, uncached-by-default route."""
    default = inspect.signature(mentions.get_mention_heat).parameters["days"].default
    bounds = {type(m).__name__: getattr(m, k) for m in default.metadata
              for k in ("ge", "le") if hasattr(m, k)}
    assert bounds == {"Ge": 30, "Le": 1825}
