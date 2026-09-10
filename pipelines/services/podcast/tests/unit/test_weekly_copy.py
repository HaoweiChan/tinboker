"""Weekly Threads copy: message assembly and output normalisation (no LLM call)."""

from podcast import weekly_copy

ROLLUP = {
    "week": "2026-W36", "start": "2026-08-31", "end": "2026-09-06",
    "episode_count": 36,
    "podcasts": [{"name": "股癌", "episodes": 2}, {"name": "財報狗", "episodes": 3}],
    "tickers": [{"ticker": "NVDA", "name": None, "episodes": 21, "bull": 15, "neu": 4, "bear": 0,
                 "prev_bull": 21, "prev_neu": 6, "prev_bear": 0}],
    "flips": [{"ticker": "8046", "name": "南電", "episodes": 8, "bull": 1, "neu": 4, "bear": 3,
               "prev_bull": 5, "prev_neu": 2, "prev_bear": 0, "direction": "bear"}],
    "sectors": [{"display_name": "PCB 載板", "episodes": 13, "exposure_id": "sector_pcb_substrate"}],
}


def test_build_messages_carries_the_numbers_the_prompt_forbids_inventing():
    user = weekly_copy.build_messages(ROLLUP)[1]["content"]
    assert "2026-W36" in user and "36" in user
    assert "8046" in user and "南電" in user and '"direction": "bear"' in user
    assert "PCB 載板" in user and "股癌" in user
    # exposure_id is internal plumbing; the model has no use for it and it invites
    # the model to print it.
    assert "sector_pcb_substrate" not in user


def test_postprocess_always_ends_with_exactly_one_link_comment():
    """The promo publisher adds nothing of its own, so a forgotten link is a dead thread."""
    out = weekly_copy.postprocess({"post": "  一段話  ", "comments": ["A", "B", "C"]})
    assert out["post"] == "一段話"
    assert out["comments"] == ["A", "B", "C", weekly_copy.LINK_COMMENT]

    # an over-long chain is trimmed so the link always fits inside MAX_COMMENTS
    long = weekly_copy.postprocess({"post": "x", "comments": ["A", "B", "C", "D", "E"]})
    assert len(long["comments"]) == weekly_copy.MAX_COMMENTS
    assert long["comments"][-1] == weekly_copy.LINK_COMMENT

    # model already wrote its own link → not duplicated, ours wins
    dup = weekly_copy.postprocess({"post": "x", "comments": ["看這裡 https://tinboker.com/weekly", "B"]})
    assert dup["comments"] == ["B", weekly_copy.LINK_COMMENT]
    assert sum("tinboker.com" in c for c in dup["comments"]) == 1

    # model returned nothing usable → still a publishable thread, never a bare post
    assert weekly_copy.postprocess({})["comments"] == [weekly_copy.LINK_COMMENT]
    assert weekly_copy.postprocess("not a dict")["post"] == ""


def test_postprocess_accepts_the_episode_writers_comment_shape():
    """The episode writer emits [{heading, text}]; a model may copy that habit."""
    out = weekly_copy.postprocess({"post": "x", "comments": [{"heading": "h", "text": "有內容"}]})
    assert out["comments"] == ["有內容", weekly_copy.LINK_COMMENT]
