from src.podcast.content_builder.nodes.sector_exposures import derive_sector_exposures


def test_node_derives_exposures_without_polluting_related_tickers():
    state = {
        "clustered_events": [
            {
                "section_topic": "AI 伺服器與半導體",
                "start": 1000,
                "end": 5000,
                "sentences": [
                    {"index": 0, "content": "AI 伺服器需求帶動半導體供應鏈", "start": 1000, "end": 3000},
                    {"index": 1, "content": "CPO 也被提到", "start": 3000, "end": 5000},
                ],
            }
        ],
        "related_tickers": ["2330"],
        "ticker_insights": {"ticker_recommendations": [{"ticker": "2330"}]},
    }

    out = derive_sector_exposures(state)

    assert "sector_exposures" in out
    assert "related_tickers" not in out
    assert "ticker_insights" not in out
    assert {"sector_ai_server", "sector_semiconductor"} <= set(out["sector_exposure_ids"])
    assert "cpo" in out["unresolved_market_trend_ids"]
