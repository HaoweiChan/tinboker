"""A6: sector-exposure candidates manufactured from ticker->sector membership.

Regression coverage for P1b — an episode can discuss a ticker at length without the
host ever saying the sector's alias out loud, so the string-alias matcher
(``resolve_clustered_events``) never produces a candidate at all. These tests cover
the ticker-derived candidate path in ``derive_sector_exposures``: fan-out cap,
context sourcing from ``ticker_insights`` locations, and fail-closed verifier-error
handling (only for ticker-derived candidates — keyword-matched ones stay fail-open).

``resolve_clustered_events`` (the string-alias matcher) is mocked out in every test
here so behavior doesn't depend on the live/backup sector taxonomy over the network
— only the ticker-derived path (deliberately isolated) is under test.
"""

from __future__ import annotations

import src.podcast.content_builder.nodes.sector_exposures as sx


def _universe(n_sectors: int = 1, ticker: str = "2330") -> dict:
    return {
        "max_tickers": 10,
        "exposures": [
            {
                "exposure_id": f"sector_test_{i}",
                "exposure_type": "sector",
                "display_name": f"測試產業{i}",
                "icon_id": None,
                "color_hex": None,
                "members": [{"ticker": ticker, "name": "台積電", "source": "curated", "rank": 1}],
            }
            for i in range(n_sectors)
        ],
    }


def _state(ticker: str = "2330", with_reason: bool = True) -> dict:
    reasons = [{"title": "r", "start_index": 0, "end_index": 0}] if with_reason else []
    return {
        "clustered_events": [
            {
                "section_topic": "台積電",
                "start": 0,
                "end": 5000,
                "sentences": [{"index": 0, "content": "台積電這季表現不錯", "start": 0, "end": 3000}],
            }
        ],
        "ticker_insights": {
            "ticker_recommendations": [
                {"ticker": ticker, "reasons": reasons, "risks": []},
            ]
        },
    }


_NO_ALIAS_MATCHES = {"sector_exposures": [], "unresolved_market_trends": []}


def test_ticker_derived_candidate_created_when_no_alias_match(monkeypatch):
    """A ticker discussed without the sector alias ever being spoken still yields a
    verifier-gated candidate that gets kept when the verifier says relevant."""
    monkeypatch.setattr(sx, "load_universe", lambda: _universe())
    monkeypatch.setattr(sx, "resolve_clustered_events", lambda events: dict(_NO_ALIAS_MATCHES))
    monkeypatch.setattr(
        "src.podcast.content_builder.llm.load_prompt",
        lambda role: {"system": "sys", "user": "{exposures_json}"},
    )
    monkeypatch.setattr(
        "src.podcast.content_builder.llm.invoke_json",
        lambda role, messages: {"verifications": [{"sector_id": "sector_test_0", "is_relevant": True}]},
    )

    out = sx.derive_sector_exposures(_state())
    assert out["sector_exposure_ids"] == ["sector_test_0"]


def test_ticker_derived_candidate_skipped_without_located_mention(monkeypatch):
    """No reasons/risks location for the ticker -> no context -> no candidate at all
    (never sent to the verifier with empty context)."""
    monkeypatch.setattr(sx, "load_universe", lambda: _universe())
    monkeypatch.setattr(sx, "resolve_clustered_events", lambda events: dict(_NO_ALIAS_MATCHES))

    def boom(*a, **k):
        raise AssertionError("verifier must not be called when there is no candidate")

    monkeypatch.setattr("src.podcast.content_builder.llm.invoke_json", boom)

    out = sx.derive_sector_exposures(_state(with_reason=False))
    assert out["sector_exposure_ids"] == []


def test_fan_out_is_capped(monkeypatch):
    """A ticker that's a curated member of many sectors only creates up to the cap."""
    monkeypatch.setattr(sx, "load_universe", lambda: _universe(n_sectors=20))
    monkeypatch.setattr(sx, "resolve_clustered_events", lambda events: dict(_NO_ALIAS_MATCHES))
    monkeypatch.setattr(
        "src.podcast.content_builder.llm.load_prompt",
        lambda role: {"system": "sys", "user": "{exposures_json}"},
    )

    captured: dict = {}

    def fake_invoke(role, messages):
        captured["messages"] = messages
        return {"verifications": []}

    monkeypatch.setattr("src.podcast.content_builder.llm.invoke_json", fake_invoke)
    sx.derive_sector_exposures(_state())

    user_content = captured["messages"][1]["content"]
    assert user_content.count('"sector_id"') == sx._MAX_TICKER_DERIVED_CANDIDATES


def test_verifier_error_fails_closed_for_ticker_derived_but_open_for_keyword_matched(monkeypatch):
    """On a verifier outage: keyword-alias candidates keep the existing fail-open
    behavior; ticker-derived-only candidates fail closed (dropped)."""
    monkeypatch.setattr(sx, "load_universe", lambda: _universe())
    # A synthetic keyword-matched exposure with NO ticker overlap -> lands in
    # to_verify via the (mocked) string-match path, alongside the ticker-derived one.
    keyword_matched = {
        "exposure_id": "sector_keyword_matched",
        "exposure_type": "sector",
        "display_name": "關鍵字匹配產業",
        "mention_text": "被動元件",
        "confidence": 1.0,
        "resolved_tickers": [],
        "total_matches": 0,
        "start_index": 0,
        "end_index": 0,
        "start_time": 0,
        "end_time": 0,
    }
    monkeypatch.setattr(
        sx, "resolve_clustered_events",
        lambda events: {"sector_exposures": [keyword_matched], "unresolved_market_trends": []},
    )

    def boom(*a, **k):
        raise RuntimeError("LLM down")

    monkeypatch.setattr(
        "src.podcast.content_builder.llm.load_prompt",
        lambda role: {"system": "s", "user": "{exposures_json}"},
    )
    monkeypatch.setattr("src.podcast.content_builder.llm.invoke_json", boom)

    out = sx.derive_sector_exposures(_state())
    ids = set(out["sector_exposure_ids"])
    assert "sector_keyword_matched" in ids   # fail-open (unchanged existing behavior)
    assert "sector_test_0" not in ids        # fail-closed (A6 candidates only)
