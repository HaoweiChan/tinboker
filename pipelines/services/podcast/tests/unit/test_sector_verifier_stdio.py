"""Sector diagnostics must not corrupt the MCP JSON-RPC stdout stream."""

import copy

import pytest
from src.podcast.content_builder.nodes import sector_exposures as sectors


@pytest.mark.parametrize("verifier_fails", [False, True])
def test_sector_diagnostics_use_stderr_without_changing_filtering(monkeypatch, capsys, verifier_fails):
    keyword = {"exposure_id": "sector_keyword", "display_name": "Keyword sector", "resolved_tickers": []}
    derived = {"exposure_id": "sector_derived", "display_name": "Derived sector", "resolved_tickers": [],
               "_ticker_derived": True}
    original = copy.deepcopy([keyword, derived])
    monkeypatch.setattr(sectors, "resolve_clustered_events", lambda events: {
        "sector_exposures": [keyword], "unresolved_market_trends": [],
    })
    monkeypatch.setattr(sectors, "_ticker_derived_candidates", lambda *args: [derived])

    def verify(candidates):
        assert {c["sector_id"] for c in candidates} == {"sector_keyword", "sector_derived"}
        if verifier_fails:
            raise RuntimeError("test verifier unavailable")
        return {"sector_keyword": False, "sector_derived": False}

    monkeypatch.setattr(sectors, "_verify_relevance", verify)
    result = sectors.derive_sector_exposures({"clustered_events": []})
    captured = capsys.readouterr()
    # invariant-gap: plain diagnostics previously entered the JSON-RPC transport.
    assert captured.out == ""
    if verifier_fails:
        assert "Sector verifier LLM call failed" in captured.err
        assert "dropping 1 ticker-derived" in captured.err
        assert result["sector_exposures"] == [keyword]
    else:
        assert captured.err.count("Filtering out sector exposure") == 2
        assert result["sector_exposures"] == []
    assert result["unresolved_market_trends"] == []
    assert [keyword, derived] == original


def test_disabled_social_cards_keep_mcp_stdout_clean(monkeypatch, capsys):
    from src.podcast.content_builder.nodes import social_cards_builder as cards

    monkeypatch.setattr(cards, "social_enabled_for", lambda source: False)
    assert cards.build_social_cards({"source": "Disabled show"}) == {"social_cards": []}
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Social cards skipped: publishing is off for Disabled show" in captured.err
