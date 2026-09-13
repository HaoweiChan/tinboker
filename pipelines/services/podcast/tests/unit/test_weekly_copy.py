"""Weekly Threads copy: message assembly and output normalisation (no LLM call)."""

from podcast import weekly_copy

ROLLUP = {
    "week": "2026-W37", "start": "2026-09-07", "end": "2026-09-13",
    "episode_count": 36,
    "podcasts": [{"name": "股癌", "episodes": 2}, {"name": "財報狗", "episodes": 3}],
    "tickers": [{"ticker": "NVDA", "name": None, "episodes": 21, "bull": 15, "neu": 4, "bear": 0,
                 "prev_bull": 21, "prev_neu": 6, "prev_bear": 0}],
    "movers": {
        "as_of": "2026-09-12",
        "high": [{"ticker": "2408", "name": "南亞科", "level": 97, "mentions": 4, "shows": 3,
                  "voices": [{"podcaster": "股癌", "side": "看多", "thesis": "DRAM 缺貨。", "when": "2026-09-10"}]}],
        "low": [],
    },
    "sectors": [{"display_name": "記憶體", "episodes": 13, "exposure_id": "sector_memory"}],
}


def test_build_messages_leads_with_movers_and_carries_their_reasons():
    system, user = (m["content"] for m in weekly_copy.build_messages(ROLLUP))
    assert "2026-W37" in user and "2026-09-12" in user           # as_of reaches the model
    assert "南亞科" in user and '"level": 97' in user and "DRAM 缺貨" in user
    assert "{" not in system.split("只輸出 JSON")[0]              # no unformatted placeholder leaked
    # exposure_id is internal plumbing the model has no use for
    assert "sector_memory" not in user and "記憶體" in user


def test_an_empty_end_is_stated_not_left_blank():
    """No low-end movers is an answer; a blank invites the model to invent one."""
    user = weekly_copy.build_messages(ROLLUP)[1]["content"]
    assert "本週沒有任何一檔落在這一端" in user
    no_movers = {**ROLLUP, "movers": None}
    assert user.count("本週沒有任何一檔落在這一端") == 1
    assert weekly_copy.build_messages(no_movers)[1]["content"].count("本週沒有任何一檔落在這一端") == 2


def test_postprocess_always_ends_with_exactly_one_link_comment():
    """The promo publisher adds nothing of its own, so a forgotten link is a dead thread."""
    out = weekly_copy.postprocess({"post": "  一段話  ", "comments": ["A", "B", "C"]})
    assert out["post"] == "一段話"
    assert out["comments"] == ["A", "B", "C", weekly_copy.LINK_COMMENT]

    long = weekly_copy.postprocess({"post": "x", "comments": ["A", "B", "C", "D", "E"]})
    assert len(long["comments"]) == weekly_copy.MAX_COMMENTS
    assert long["comments"][-1] == weekly_copy.LINK_COMMENT

    dup = weekly_copy.postprocess({"post": "x", "comments": ["看這裡 https://tinboker.com/weekly", "B"]})
    assert dup["comments"] == ["B", weekly_copy.LINK_COMMENT]

    assert weekly_copy.postprocess({})["comments"] == [weekly_copy.LINK_COMMENT]
    assert weekly_copy.postprocess("not a dict")["post"] == ""


def test_postprocess_accepts_the_episode_writers_comment_shape():
    out = weekly_copy.postprocess({"post": "x", "comments": [{"heading": "h", "text": "有內容"}]})
    assert out["comments"] == ["有內容", weekly_copy.LINK_COMMENT]
