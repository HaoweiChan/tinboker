import json

from src.services.episode_sentiments import _parse


def test_parse_accepts_sentiment_and_sentiment_label_fields():
    content = json.dumps(
        {
            "ticker_recommendations": [
                {"ticker": "NVDA", "sentiment": "BULLISH"},
                {"ticker": "ORCL", "sentiment_label": "BEARISH"},
                {"ticker": "TSM", "sentiment": "UNKNOWN"},
                {"ticker": "", "sentiment": "BULLISH"},
            ]
        }
    )

    assert _parse(content) == {"NVDA": "BULLISH", "ORCL": "BEARISH"}
