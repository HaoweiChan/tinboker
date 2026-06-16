"""Insight doc coercion: dirty start_time/index values must not 500 the feed.

Regression for the /api/ticker-insights/recent 500 — some reason/risk docs carry
`start_time` as a "MM:SS.mmm" string instead of integer ms, which crashed the
collection-group response when the blended feed surfaced them.
"""
import src.services.insight_service as ins


def test_coerce_ms_numeric_passthrough():
    assert ins._coerce_ms(73939) == 73939
    assert ins._coerce_ms(0) == 0
    assert ins._coerce_ms(None) == 0
    assert ins._coerce_ms(True) == 0  # bool is not a real ms value


def test_coerce_ms_timestamp_strings():
    assert ins._coerce_ms("01:13.939") == 73939   # 1m 13.939s
    assert ins._coerce_ms("00:05") == 5000        # 5s
    assert ins._coerce_ms("1:02:03") == 3723000   # 1h 2m 3s
    assert ins._coerce_ms("88000") == 88000       # plain ms string
    assert ins._coerce_ms("garbage") == 0
    assert ins._coerce_ms("") == 0


def test_safe_int():
    assert ins._safe_int("12") == 12
    assert ins._safe_int(12.9) == 12
    assert ins._safe_int("x") == 0
    assert ins._safe_int(None) == 0


def test_doc_to_insight_tolerates_dirty_times():
    doc = {
        "schema_version": 3,
        "episode_id": "e1", "podcaster": "P", "podcast_launch_time": "2026-06-16T00:00:00Z",
        "ticker": "NVDA", "bluf_thesis": "x", "time_horizon": "中期", "sentiment_label": "BULLISH",
        "reasons": [{"title": "r", "description": "d", "start_time": "01:13.939",
                     "end_time": "01:20", "start_index": "5", "end_index": 9}],
        "risks": [{"title": "k", "description": "d", "start_time": "bad", "severity": "HIGH"}],
        "created_at": "2026-06-16T00:00:00Z",
    }
    out = ins._doc_to_insight(doc)  # must not raise
    assert out["reasons"][0]["start_time"] == 73939
    assert out["reasons"][0]["end_time"] == 80000
    assert out["reasons"][0]["start_index"] == 5
    assert out["risks"][0]["start_time"] == 0
