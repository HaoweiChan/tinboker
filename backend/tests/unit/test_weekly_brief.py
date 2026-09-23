"""週報素材: topic selection and the writer's markdown are pure over plain dicts."""

from src.services import weekly_brief as wb

EPISODES = {
    "dog": {"id": "dog", "podcast_name": "財報狗", "episode_title": "562. NAND Flash", "date": "2026-09-06"},
    "ch": {"id": "ch", "podcast_name": "兆華與股惑仔", "episode_title": "EP1178", "date": "2026-09-07"},
    "yi": {"id": "yi", "podcast_name": "財經一路發", "episode_title": "9/7 早盤", "date": "2026-09-07"},
    "jn": {"id": "jn", "podcast_name": "財女珍妮", "episode_title": "9/7", "date": "2026-09-07"},
}


def _ins(ep, show, ticker, label, horizon, thesis, cats=("FUNDAMENTAL",), risks=()):
    return {"episode_id": ep, "podcaster": show, "ticker": ticker, "sentiment_label": label, "time_horizon": horizon,
            "bluf_thesis": thesis, "podcast_launch_time": EPISODES.get(ep, {}).get("date", "2026-09-01") + "T08:00:00Z",
            "reasons": [{"category": c, "title": f"{c} 理由", "description": "說明"} for c in cats],
            "risks": [{"title": r, "description": "風險說明"} for r in risks]}


INSIGHTS = [
    _ins("dog", "財報狗", "MU", "BULLISH", "中期", "長約鎖上限但換來能見度", ("FUNDAMENTAL", "DEMAND"), risks=("長約鎖價",)),
    _ins("ch", "兆華與股惑仔", "MU", "BULLISH", "短期", "站上季線", ("TECHNICAL",)),
    _ins("yi", "財經一路發", "MU", "BULLISH", "短期", "大漲 6% 波段低檔確立", ("TECHNICAL",)),
    _ins("jn", "財女珍妮", "MU", "NEUTRAL", "中期", "Kepler 不必恐慌", ("DEMAND",), risks=("新架構",)),
    _ins("dog", "財報狗", "2408", "NEUTRAL", "中期", "長江存儲風險", ("SUPPLY",), risks=("長江存儲",)),
    _ins("ch", "兆華與股惑仔", "2408", "BULLISH", "短期", "營收創高"),
    _ins("yi", "財經一路發", "2408", "BULLISH", "短期", "突破前高", ("TECHNICAL",)),
    _ins("dog", "財報狗", "8299", "BULLISH", "中期", "AI Adaptive"),
    _ins("ch", "兆華與股惑仔", "8299", "BULLISH", "短期", "重回季線"),
    _ins("zz", "別的節目", "9999", "BULLISH", "短期", "不在本週集數"),
]


def test_topics_need_three_shows_and_carry_every_sourced_observation():
    topics = wb.select_topics(INSIGHTS, EPISODES, {"MU": "美光", "2408": "南亞科"})
    assert [t["ticker"] for t in topics] == ["MU", "2408"]      # 8299 has two shows, 9999 is outside the week
    mu = topics[0]
    assert (mu["name"], mu["shows"], mu["observations"]) == ("美光", 4, 4)
    assert mu["stances"] == {"看多": 3, "中性": 1} and mu["horizons"] == {"中期": 2, "短期": 2}
    assert mu["divergence"] == {"stance": True, "horizon": True, "risks_raised_by": ["財報狗", "財女珍妮"]}
    assert mu["reason_mix"]["TECHNICAL"] == 2
    first = mu["rows"][0]
    assert (first["show"], first["date"], first["episode_title"], first["stance"], first["horizon"]) == \
        ("財報狗", "2026-09-06", "562. NAND Flash", "看多", "中期")
    assert first["risks"][0]["title"] == "長約鎖價"


def test_markdown_carries_rules_sources_movers_and_no_returns():
    topics = wb.select_topics(INSIGHTS, EPISODES, {"MU": "美光"})
    brief = {"week": "2026-W37", "start": "2026-09-07", "end": "2026-09-13", "topics": topics,
             "movers": {"as_of": "2026-09-13", "high": [{"ticker": "2408", "name": "南亞科", "level": 97}], "low": []},
             "episodes": list(EPISODES.values())}
    md = wb.render_brief_markdown(brief)
    assert md.startswith("# 週報素材 2026-W37")
    assert "不判哪一邊比較對" in md and "不報收錄規模" in md
    assert "## 題目：美光（MU）" in md and "### 財報狗・2026-09-06・看多・中期" in md
    assert "https://tinboker.com/episode/dog" in md and "- 風險 長約鎖價" in md
    assert "在自己一年高點：南亞科（2408，97）" in md and "在自己一年低點：無" in md
    block = md.split("## 聲量水位")[1].split("## 這週的集數")[0]
    assert "%" not in block and "超額" not in block  # state only in the movers block, never a return


def test_build_weekly_brief_assembles_a_real_brief(monkeypatch):
    """The assembly function itself — the pure ones above never ran it, which is how a
    `date.fromtimestamp(tz=...)` TypeError sat in it for a week while the endpoint 500'd."""
    import asyncio
    from types import SimpleNamespace

    # 2026-09-08 00:30 Taipei, which is still 09-07 in UTC — a converter that skips
    # the timezone dates this episode a day early and can drop it out of the week.
    ep = SimpleNamespace(id="dog", podcast_name="財報狗", episode_title="562. NAND Flash",
                         released_at_ms=1788798600000, created_time=None)

    async def _episodes(**_):
        return [ep]

    async def _insights(*_a, **_k):
        return [_ins("dog", "財報狗", "MU", "BULLISH", "中期", "長約鎖上限", ("FUNDAMENTAL",))]

    async def _movers(*_a, **_k):
        return {"as_of": "2026-09-13", "high": [], "low": []}

    async def _allowed():
        return frozenset({"財報狗"})

    monkeypatch.setattr(wb.podcast_service, "get_recent_episodes", _episodes)
    monkeypatch.setattr(wb.podcast_service, "_allowed_podcast_names", _allowed)
    monkeypatch.setattr(wb, "_insights_for", _insights)
    monkeypatch.setattr(wb, "attention_movers", _movers)
    monkeypatch.setattr(wb, "get_session", lambda: iter([None]))
    monkeypatch.setattr(wb, "query_names", lambda _db, _t: {"MU": "美光"})

    brief = asyncio.run(wb.build_weekly_brief("2026-W37"))
    assert brief["episode_count"] == 1
    assert brief["episodes"][0]["date"] == "2026-09-08"     # Taipei day, not UTC
    assert brief["markdown"].startswith("# 週報素材 2026-W37")
