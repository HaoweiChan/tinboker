import pytest

from src.podcast.content_builder.nodes.sector_exposures import derive_sector_exposures

# The universe is fetched live and cached per machine (the committed fixture it used to
# fall back to is gone), so the test states the two exposures it asserts on.
_UNIVERSE = {
    "max_tickers": 10,
    "exposures": [
        {"exposure_id": "sector_semiconductor", "display_name": "半導體", "exposure_type": "industry",
         "aliases": ["半導體", "晶片", "semiconductor"],
         "members": [{"ticker": "2330", "name": "台積電", "market": "TW"}]},
        {"exposure_id": "sector_ai_server", "display_name": "AI 伺服器組裝", "exposure_type": "theme",
         "aliases": ["AI 伺服器組裝", "AI 伺服器", "ai server"],
         "members": [{"ticker": "6669", "name": "緯穎", "market": "TW"}]},
    ],
}


@pytest.fixture(autouse=True)
def _live_universe(monkeypatch, tmp_path):
    import shared.sectors as sectors

    sectors._universe.cache_clear()
    sectors._alias_index.cache_clear()
    monkeypatch.setattr(sectors, "_CACHE_PATH", tmp_path / "sectors_universe.json")
    monkeypatch.setattr(sectors, "fetch_sectors_universe", lambda: _UNIVERSE)
    yield
    sectors._universe.cache_clear()
    sectors._alias_index.cache_clear()


def test_node_derives_exposures_without_polluting_related_tickers():
    state = {
        "clustered_events": [
            {
                "section_topic": "AI 伺服器與半導體",
                "start": 1000,
                "end": 5000,
                "sentences": [
                    {"index": 0, "content": "AI 伺服器需求帶動半導體供應鏈", "start": 1000, "end": 3000},
                    {"index": 1, "content": "XYZ 也被提到", "start": 3000, "end": 5000},
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
    assert "xyz" in out["unresolved_market_trend_ids"]
