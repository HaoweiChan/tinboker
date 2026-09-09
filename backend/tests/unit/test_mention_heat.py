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


def test_the_index_is_anchored_to_the_busiest_ticker_not_to_a_share():
    """A raw share is unreadable: over 30 days the median mentioned ticker holds 0.059%
    of all discussion and would print as "0.0%". The index divides by the maximum."""
    body = inspect.getsource(mentions._heat_index)
    assert "func.max(" in body
    assert "min(100, round(" in body   # clamped to the 0-100 the UI promises


def test_the_index_decays_like_every_other_heat_number_here():
    body = inspect.getsource(mentions._heat_index)
    assert "func.power(0.5" in body and "_HEAT_HALF_LIFE_DAYS" in body


def test_the_index_window_matches_the_label_on_the_card_it_feeds():
    """The consensus tile says 近 30 天; an index over a different window would be a
    quiet lie sitting inside that heading."""
    assert mentions._HEAT_INDEX_DAYS == 30
