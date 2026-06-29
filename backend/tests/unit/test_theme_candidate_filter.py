"""Self-check for the theme-candidate ticker/index filter (admin 題材探勘 queue).

The pipeline sometimes mis-files a ticker (NVDA) or an index (SP500) into an
episode's ``unresolved_market_trends``; those must NOT surface as curatable themes.
Mirrors the predicate in PodcastService.theme_candidates.
"""

from src.services.podcast import PodcastService


def _filter(candidates, related_tickers):
    """Replicate theme_candidates' drop rule against a known ticker/index set."""
    tickers = {str(t).split(".")[0].strip().upper() for t in related_tickers}
    stop = PodcastService._THEME_INDEX_STOPWORDS

    def is_ticker_or_index(b):
        return any(
            str(s).strip().upper() in tickers or str(s).strip().upper() in stop
            for s in (b["mention_text"], b["normalized_text"])
        )

    return [b for b in candidates if not is_ticker_or_index(b)]


def test_drops_tickers_and_indices_keeps_real_themes():
    candidates = [
        {"mention_text": "NVDA", "normalized_text": "nvda"},      # ticker
        {"mention_text": "GOOGL", "normalized_text": "googl"},    # ticker (case)
        {"mention_text": "SP500", "normalized_text": "sp500"},    # index stopword
        {"mention_text": "VIX", "normalized_text": "vix"},        # index stopword
        {"mention_text": "CPO", "normalized_text": "copackagedoptics"},  # stopword now
        {"mention_text": "AIPC", "normalized_text": "aipc"},      # stopword now
        {"mention_text": "XYZ", "normalized_text": "xyz"},        # real theme (not in stopword list)
    ]
    # 2330.TW exercises the exchange-suffix strip; NVDA/GOOGL the US symbols.
    related = ["NVDA", "2330.TW", "GOOGL", "AAPL"]

    kept = {b["mention_text"] for b in _filter(candidates, related)}
    assert kept == {"XYZ"}, kept


if __name__ == "__main__":
    test_drops_tickers_and_indices_keeps_real_themes()
    print("OK")
