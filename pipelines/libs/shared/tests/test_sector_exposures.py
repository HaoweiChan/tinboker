import json

import pytest
from shared.sectors import (
    LiveUniverseRequiredError,
    aggregate_unresolved_trends,
    current_exposure_ids,
    find_exposure_matches,
    load_universe,
    resolve_text,
)

# The universe used to arrive from a taxonomy fixture committed to the repo. It is now
# fetched live and cached per machine, so these tests state the universe they mean —
# aliases copied from the live registry, plus a bare "AI" on the hardware exposure so the
# longest-match test still has a shorter alias to lose to.
_UNIVERSE = {
    "max_tickers": 10,
    "exposures": [
        {
            "exposure_id": "sector_semiconductor",
            "display_name": "半導體",
            "exposure_type": "industry",
            "aliases": ["半導體", "晶片", "晶圓", "護國神山", "semiconductor", "chip", "chips"],
            "members": [
                {"ticker": "2330", "name": "台積電", "market": "TW"},
                {"ticker": "2303", "name": "聯電", "market": "TW"},
                {"ticker": "2454", "name": "聯發科", "market": "TW"},
                {"ticker": "3711", "name": "日月光投控", "market": "TW"},
            ],
        },
        {
            "exposure_id": "sector_ai_server",
            "display_name": "AI 伺服器組裝",
            "exposure_type": "theme",
            "aliases": ["AI 伺服器組裝", "AI 伺服器", "ai server"],
            "members": [{"ticker": "6669", "name": "緯穎", "market": "TW"}],
        },
        {
            "exposure_id": "sector_ai_hardware",
            "display_name": "AI與電子硬體",
            "exposure_type": "industry",
            "aliases": ["AI", "AI 硬體", "電子硬體"],
            "members": [{"ticker": "2317", "name": "鴻海", "market": "TW"}],
        },
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


def test_resolved_tickers_are_tw_only():
    # US exposures were split out to a separate topics tab; the sector universe is TW-only.
    out = resolve_text("今天半導體供應鏈很強", max_tickers=10)
    exposure = out["sector_exposures"][0]

    markets = {t["market"] for t in exposure["resolved_tickers"]}
    assert markets == {"TW"}
    assert exposure["confidence"] == 1.0


def test_english_normalization_handles_case_and_plural():
    singular = resolve_text("Semiconductor demand is improving")
    plural = resolve_text("semiconductors are recovering")

    assert singular["sector_exposures"][0]["exposure_id"] == "sector_semiconductor"
    assert plural["sector_exposures"][0]["exposure_id"] == "sector_semiconductor"


def test_cross_lingual_aliases_and_many_to_many_indexing():
    matches = find_exposure_matches("護國神山和 semiconductor foundry 都是焦點")
    ids = {m.exposure["exposure_id"] for m in matches}

    assert "sector_semiconductor" in ids


def test_longest_match_first_prefers_ai_server_over_shorter_ai_alias():
    out = resolve_text("AI 伺服器供應鏈轉強，AI 題材延續")

    assert out["sector_exposures"][0]["exposure_id"] == "sector_ai_server"
    assert out["sector_exposures"][0]["mention_text"] == "AI 伺服器"


def test_resolved_tickers_are_capped_but_total_matches_preserved():
    out = resolve_text("半導體族群", max_tickers=3)
    exposure = out["sector_exposures"][0]

    assert len(exposure["resolved_tickers"]) == 3
    assert exposure["total_matches"] > 3


def test_unresolved_trend_aggregation_threshold():
    rows = [
        {"mention_text": "CPO", "normalized_text": "cpo"},
        {"mention_text": "CPO", "normalized_text": "cpo"},
        {"mention_text": "ASIC", "normalized_text": "asic"},
    ]

    assert aggregate_unresolved_trends(rows, threshold=2) == [
        {
            "normalized_text": "cpo",
            "count": 2,
            "examples": rows[:2],
        }
    ]


def test_unresolved_market_trend_emitted_for_unmapped_uppercase_concept():
    out = resolve_text("主持人提到 XYZ 會帶動下一波光通訊需求")

    assert {"xyz"} <= {item["normalized_text"] for item in out["unresolved_market_trends"]}


def test_universe_prefers_live_platform_fetch(monkeypatch):
    import shared.sectors as sectors

    sectors._universe.cache_clear()
    monkeypatch.setattr(
        sectors,
        "fetch_sectors_universe",
        lambda: {
            "max_tickers": 3,
            "exposures": [
                {
                    "exposure_id": "sector_live",
                    "display_name": "Live",
                    "aliases": ["live alias"],
                    "members": [{"ticker": "1001", "market": "TW"}],
                }
            ],
        },
    )

    out = resolve_text("live alias", require_live_universe=True)

    assert out["sector_exposures"][0]["exposure_id"] == "sector_live"
    assert current_exposure_ids(require_live_universe=True) == {"sector_live"}


def test_universe_backup_fallback_warns_and_can_be_disallowed(monkeypatch, caplog, tmp_path):
    import shared.sectors as sectors

    sectors._universe.cache_clear()
    monkeypatch.setattr(sectors, "fetch_sectors_universe", lambda: None)
    # The fallback is this machine's own cache of the last live read, not a fixture.
    cache = tmp_path / "sectors_universe.json"
    cache.write_text(json.dumps({"max_tickers": 10, "exposures": [
        {"exposure_id": "sector_ospat", "display_name": "封測代工", "members": []},
    ]}), encoding="utf-8")
    monkeypatch.setattr(sectors, "_CACHE_PATH", cache)

    with caplog.at_level("WARNING"):
        universe = load_universe()

    assert universe["exposures"]
    assert str(cache) in caplog.text
    assert "stale" in caplog.text
    try:
        load_universe(require_live_universe=True)
    except LiveUniverseRequiredError:
        pass
    else:
        raise AssertionError("require_live_universe should reject backup fallback")


def test_backup_fallback_does_not_poison_live_universe_cache(monkeypatch, caplog, tmp_path):
    import shared.sectors as sectors

    live_payload = {
        "max_tickers": 3,
        "exposures": [
            {
                "exposure_id": "sector_live_after_backup",
                "display_name": "Live After Backup",
                "aliases": ["live after backup"],
                "members": [{"ticker": "1001", "market": "TW"}],
            }
        ],
    }
    responses = [None, live_payload]

    cache = tmp_path / "sectors_universe.json"
    cache.write_text(json.dumps({"max_tickers": 10, "exposures": [
        {"exposure_id": "sector_cached", "display_name": "Cached", "members": []},
    ]}), encoding="utf-8")
    sectors._alias_index.cache_clear()
    sectors._universe.cache_clear()
    monkeypatch.setattr(sectors, "_CACHE_PATH", cache)
    monkeypatch.setattr(sectors, "fetch_sectors_universe", lambda: responses.pop(0))

    with caplog.at_level("WARNING"):
        fallback = load_universe()

    assert fallback["exposures"]
    assert "Using the cached sector taxonomy" in caplog.text

    out = resolve_text("live after backup")

    assert out["sector_exposures"][0]["exposure_id"] == "sector_live_after_backup"
