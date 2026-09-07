"""The paid weekly's render is pure over three dicts; these pin the numbers a
subscriber pays for (hit rate, mean return, best/worst calls, screener cross-ref)."""

from src.services import paid_weekly as pw

ROLLUP = {
    "week": "2026-W36", "start": "2026-08-31", "end": "2026-09-06", "episode_count": 3,
    "podcasts": [{"name": "A", "episodes": 2}, {"name": "B", "episodes": 1}],
    "tickers": [
        {"ticker": "2330", "name": "台積電", "episodes": 3, "bull": 2, "neu": 1, "bear": 0,
         "prev_bull": 1, "prev_neu": 0, "prev_bear": 0},
        {"ticker": "2454", "name": None, "episodes": 1, "bull": 0, "neu": 0, "bear": 1,
         "prev_bull": 0, "prev_neu": 0, "prev_bear": 0},
    ],
    "sectors": [],
    "episodes": [{"related_tickers": ["2330", "2454"]}, {"related_tickers": ["2330"]}, {"related_tickers": ["2330"]}],
}
RECORD = {
    "week": "2026-W32", "start": "2026-08-03", "end": "2026-08-09",
    "calls": [
        {"podcaster": "A", "ticker": "2330", "date": "2026-08-04", "sentiment_label": "BULLISH",
         "thesis": "x" * 80, "r": 5.0, "hit": True},
        {"podcaster": "A", "ticker": "2454", "date": "2026-08-05", "sentiment_label": "BEARISH",
         "thesis": "跌", "r": 3.0, "hit": False},
        {"podcaster": "A", "ticker": "2330", "date": "2026-08-06", "sentiment_label": "NEUTRAL",
         "thesis": "", "r": 1.0, "hit": None},
        {"podcaster": "B", "ticker": "2330", "date": "2026-08-07", "sentiment_label": "BULLISH",
         "thesis": "漲", "r": -2.0, "hit": False},
    ],
}
SCREENER = {
    "date": "2026-09-05",
    "candidates": [
        {"rank": 1, "ticker": "2454", "final_score": 0.91, "factors": {"ret_5d": 0.0795, "vol_mult": 2.3},
         "is_60d_high": True, "crowded": False},
        {"rank": 2, "ticker": "3008", "final_score": 0.80, "factors": {}, "is_60d_high": False, "crowded": True},
    ],
}


def test_lagged_week_is_four_iso_weeks_back():
    assert pw.lagged_week("2026-W36") == "2026-W32"
    assert pw.lagged_week("2026-W02") == "2025-W50"


def test_render_carries_every_section_and_the_disclaimer():
    md = pw.render_markdown(ROLLUP, RECORD, SCREENER)["markdown"]
    assert "## 本週節目焦點（2026-08-31 → 2026-09-06）" in md
    assert "| 台積電（2330） | 3 | 2（1） | 1（0） | 0（0） |" in md
    assert "## 誰講對了 — 2026-W32" in md
    assert "## 篩選器前十 × 節目提及（2026-09-05）" in md
    assert pw.DISCLAIMER in md


def test_track_record_scores_direction_and_averages_everything():
    md = pw.render_markdown(ROLLUP, RECORD, SCREENER)["markdown"]
    # A: 3 mentions, 1/2 directional hits (neutral not scored), mean (5+3+1)/3 = +3.0%
    assert "| A | 3 | 1/2 | +3.0% |" in md
    assert "| B | 1 | 0/1 | -2.0% |" in md
    # best call first is A's +5% bullish; the thesis is clipped to 60 chars
    lines = md.splitlines()
    best = lines[lines.index("**講得最準的三筆**") + 1]
    assert best.startswith("- 2026-08-04 A 對 台積電（2330） 看多，之後 20 日 +5.0%。「" + "x" * 60 + "…」")
    # worst = the bearish call that went up; direction is scored, not the raw sign
    worst = lines[lines.index("**偏差最大的三筆**") + 1]
    assert "A 對 2454 看空，之後 20 日 +3.0%" in worst


def test_screener_rows_cross_reference_this_weeks_mentions():
    md = pw.render_markdown(ROLLUP, RECORD, SCREENER)["markdown"]
    assert "| 1 | 2454 | 0.91 | +8.0% | 2.3x | ✓ |  | 1 |" in md  # ret_5d stored as a fraction
    assert "| 2 | 3008 | 0.80 | — | — |  | ✓ | 0 |" in md


def test_no_resolved_calls_says_so_instead_of_an_empty_table():
    out = pw.render_markdown(ROLLUP, {**RECORD, "calls": []}, {"date": None, "candidates": []})
    assert "本節下期補上" in out["markdown"]
    assert "本期無篩選器資料" in out["markdown"]
    assert out["stats"] == {"episodes": 3, "calls_scored": 0, "screener_rows": 0}
    assert out["title"] == "聽播客週報 Pro 2026-W36｜誰講對了、篩選器前十"
