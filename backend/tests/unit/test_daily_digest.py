"""每日精選: the ranking and the markdown are pure over plain dicts."""

from datetime import date

from src.services import daily_digest as dd

EPISODES = [
    {"id": "e1", "podcast_name": "Gooaye 股癌", "episode_title": "EP700"},
    {"id": "e2", "podcast_name": "財經一路發", "episode_title": "9/12 早盤"},
    {"id": "e3", "podcast_name": "財經一路發", "episode_title": "9/12 晚盤"},
]


def _ins(ep, ticker, label, thesis, podcaster, reasons=1):
    return {"episode_id": ep, "ticker": ticker, "sentiment_label": label, "bluf_thesis": thesis,
            "podcaster": podcaster, "reasons": [{"category": "DEMAND"}] * reasons}


INSIGHTS = [
    _ins("e1", "2330", "BULLISH", "先進封裝產能吃緊，法說會上修資本支出", "Gooaye 股癌", reasons=3),
    _ins("e2", "2330", "NEUTRAL", "台積電漲多，等回檔", "財經一路發"),
    _ins("e3", "2454", "BULLISH", "聯發科 ASIC 訂單能見度到明年", "財經一路發", reasons=2),
    _ins("e2", "2454", "BEARISH", "", "財經一路發"),
    _ins("zz", "9999", "BULLISH", "not today's episode", "別的節目"),
]


def test_rows_rank_by_shows_then_mentions_and_quote_the_best_backed_thesis():
    rows = dd.select_rows(EPISODES, INSIGHTS, {"2330": "台積電"})
    assert [r["ticker"] for r in rows] == ["2330", "2454"]      # 9999 is from an episode not in the day
    tsmc = rows[0]
    assert (tsmc["shows"], tsmc["mentions"], tsmc["bull"], tsmc["neu"]) == (2, 2, 1, 1)
    assert tsmc["thesis"].startswith("先進封裝")                   # 3 reasons beats 1
    assert tsmc["podcaster"] == "Gooaye 股癌" and tsmc["episode_id"] == "e1"
    mtk = rows[1]
    assert mtk["bear"] == 1 and mtk["thesis"].startswith("聯發科")  # the empty thesis is never quoted


def test_render_carries_source_links_and_the_disclaimer():
    rows = dd.select_rows(EPISODES, INSIGHTS, {"2330": "台積電"})
    out = dd.render_digest(date(2026, 9, 12), EPISODES, rows)
    md = out["markdown"]
    assert out["title"].startswith("聽播客每日精選 2026-09-12")
    assert "共 3 集（財經一路發 2 集、Gooaye 股癌 1 集）" in md
    assert "## 台積電（2330）" in md and "2 個節目 · 2 則觀點 · 看多 1 / 中性 1" in md
    assert "《EP700》（https://tinboker.com/episode/e1）" in md
    assert dd.DISCLAIMER in md and "/weekly/2026-W37" in md
    assert out["excerpt"] == "今天節目講到：台積電、2454"
    assert "|" not in md  # vocus renders no tables


def test_day_bounds_are_taipei_midnight():
    from datetime import datetime, timezone
    lo, hi = dd.day_bounds_ms(date(2026, 9, 12))
    assert hi - lo == 86_400_000
    assert lo == int(datetime(2026, 9, 11, 16, 0, tzinfo=timezone.utc).timestamp() * 1000)  # 00:00 Taipei
