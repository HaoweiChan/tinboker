from shared.sectors import (
    aggregate_unresolved_trends,
    find_exposure_matches,
    resolve_text,
)


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
