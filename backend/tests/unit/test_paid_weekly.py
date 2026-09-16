"""The paid weekly's render is pure over plain dicts; these pin the shape a subscriber
pays for: free summary, paywall, the article, then charts + pooled excess vs the index."""

import pytest

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
    "sectors": [], "episodes": [],
}


def _call(show, ticker, day, label, thesis, r, idx):
    return {"podcaster": show, "ticker": ticker, "date": day, "sentiment_label": label,
            "stance": pw._stance(label), "thesis": thesis, "r": r, "idx": idx,
            "excess": None if idx is None else r - idx}


RECORD = {
    "week": "2026-W32", "start": "2026-08-03", "end": "2026-08-09",
    "calls": [
        _call("A", "2330", "2026-08-04", "BULLISH", "x" * 80, 5.0, 2.0),
        _call("A", "2454", "2026-08-05", "BEARISH", "跌", 3.0, 2.0),
        _call("A", "2330", "2026-08-06", "NEUTRAL", "", 1.0, 2.0),
        _call("B", "2330", "2026-08-07", "BULLISH", "漲", -2.0, 2.0),
        _call("B", "3008", "2026-08-07", "BULLISH", "無大盤", 9.0, None),
    ],
}
MOVERS = {"week": "2026-W36", "as_of": "2026-09-06",
          "high": [{"ticker": "2408", "name": "南亞科", "level": 97, "mentions": 9, "shows": 3}],
          "low": []}
ARTICLE = "# 記憶體漲價，節目為何分歧？\n\n[南亞科](https://tinboker.com/stock/2408) 第一段。\n\n第二段 [南亞科](https://tinboker.com/stock/2408)。"


def test_lagged_week_is_four_iso_weeks_back():
    assert pw.lagged_week("2026-W36") == "2026-W32"
    assert pw.lagged_week("2026-W02") == "2025-W50"


def test_summary_is_short_and_sits_above_the_paywall():
    md = pw.render_markdown(ROLLUP, RECORD, MOVERS, article=ARTICLE)["markdown"]
    free, paid = md.split("\n" + pw.PAYWALL + "\n", 1)
    assert free.startswith("## 本期摘要（2026-08-31 → 2026-09-06）")
    assert "本週主題：記憶體漲價，節目為何分歧？\n" in free   # no 。 after a ？
    assert "台積電（2330）、2454" in free
    assert "%" not in free                       # no numbers leak above the wall
    assert paid.index("## 記憶體漲價，節目為何分歧？") < paid.index("## 資料附錄")
    assert "[南亞科（2408）](https://tinboker.com/stock/2408)" in paid.split("## 資料附錄")[1] and "/stock/2330" not in paid  # follows the article
    assert "第一段。\n\n第二段 " in paid and paid.count("記憶體漲價，節目為何分歧") == 1  # H1 not repeated


def test_appendix_has_charts_movers_and_pooled_excess_vs_index():
    out = pw.render_markdown(ROLLUP, RECORD, MOVERS, names={"2454": "聯發科"})
    md = out["markdown"]
    assert "[台積電（2330）](https://tinboker.com/stock/2330)、[聯發科（2454）](https://tinboker.com/stock/2454)" in md
    assert "![" not in md  # no image syntax: the converter has no image node
    assert "- 在自己一年高點（≥90）：南亞科（2408） 97" in md and "一年低點" not in md
    # bulls with an index: +5 vs +2, -2 vs +2 → 2 calls, 50% up, mean +1.5 vs +2.0, 50% beat
    assert "那週有 2 筆看多的個股說法可驢證" not in md
    assert "那週有 2 筆看多的個股說法可驗證。單看漲跌，50% 之後是漲的；" in md
    assert "平均走了 +2.0%，這些個股平均 +1.5%，只有 50% 跑贏同期大盤" in md
    lines = md.splitlines()
    best = lines[lines.index("**相對大盤最強的三筆**") + 1]
    assert best.startswith("- 2026-08-04 A 對 台積電（2330） 看多，之後 20 日 +5.0%（同期大盤 +2.0%）。「" + "x" * 60 + "…」")
    assert lines[lines.index("**相對大盤最弱的三筆**") + 1].startswith("- 2026-08-07 B 對 台積電")
    assert "| A |" not in md                      # no per-show league table
    assert pw.DISCLAIMER in md
    assert out["title"] == "聽播客週報 Pro 2026-W36"
    assert out["stats"] == {"episodes": 3, "calls_scored": 5, "movers": 1, "article": False}
    assert out["thumbnail_url"].startswith("https://api.tinboker.com/api/og/title/") and "?" not in out["thumbnail_url"]


def test_no_resolved_calls_says_so():
    out = pw.render_markdown(ROLLUP, {**RECORD, "calls": []}, {"high": [], "low": []}, article=ARTICLE)
    assert "本節下期補上" in out["markdown"] and "**聲量水位**" not in out["markdown"]
    assert out["title"] == "聽播客週報 Pro 2026-W36｜記憶體漲價，節目為何分歧？"
    payload = out["thumbnail_url"].rsplit("/", 1)[1][:-4]
    assert pw.title_payload("記憶體漲價，節目為何分歧？", "聽播客週報 Pro 2026-W36") == payload


def test_index_return_uses_the_first_session_on_or_after_the_mention():
    series = ([f"2026-08-{d:02d}" for d in range(1, 31)], [100.0 + d for d in range(30)])
    assert pw.index_return(series, "2026-08-03", sessions=5) == pytest.approx((107 / 102 - 1) * 100)  # 08-03 → 08-08
    assert pw.index_return(series, "2026-08-04", sessions=5) == pytest.approx((108 / 103 - 1) * 100)
    assert pw.index_return(series, "2026-08-28", sessions=5) is None


def test_article_tickers_in_order_of_first_link():
    assert pw.article_tickers("[a](/stock/2408) [b](https://tinboker.com/stock/mu) [c](/stock/2408) [d](/stock/2344)", limit=2) == ["2408", "MU"]
    assert pw.article_tickers(None) == []


def test_cited_tickers_covers_all_sections():
    assert pw.cited_tickers(ROLLUP, RECORD, MOVERS) == {"2330", "2454", "3008", "2408"}
