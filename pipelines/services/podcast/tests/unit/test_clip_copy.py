"""Clip picking: the 30-second cap, the candidate windows, and failing closed."""

from src.podcast import clip_copy as cc


def _md(pairs):
    return "\n".join(f"{text} (#time:{ms})" for ms, text in pairs)


# Three seconds a sentence, with four stance markers far enough apart that each opens a
# window of its own (the dedup drops anything inside another window's 30 seconds).
ROWS = [(i * 3000, f"句子{i}") for i in range(50)]
for _i, _text in ((5, "我覺得這件事沒有那麼複雜"), (17, "很多人一直問這個"),
                  (29, "老實說根本不用管短線"), (41, "最重要的是他自己怎麼想")):
    ROWS[_i] = (_i * 3000, _text)


def test_parse_sentences_reads_time_anchors_and_drops_junk():
    rows = cc.parse_sentences(_md([(0, "第一句"), (3000, "第二句")]) + "\n\n沒有時間戳的行")
    assert rows == [(0, "第一句"), (3000, "第二句")]


def test_window_never_runs_past_the_cap_and_ends_on_a_sentence():
    w = cc.window_at(ROWS, 30000)
    assert w["end_ms"] - w["start_ms"] <= cc.MAX_CLIP_S * 1000
    assert w["end_ms"] in [t for t, _ in ROWS]          # a real boundary, not a hard cut


def test_window_opens_before_the_marker_so_it_does_not_start_mid_thought():
    w = cc.window_at(ROWS, 30000)
    assert w["start_ms"] <= 30000 - cc.LEAD_MS


def test_a_single_very_long_sentence_is_cut_at_the_cap():
    rows = [(0, "開場"), (5000, "一句講了兩分鐘"), (125000, "下一句")]
    w = cc.window_at(rows, 10000)
    assert w["end_ms"] - w["start_ms"] == cc.MAX_CLIP_S * 1000


def test_candidates_are_ranked_by_stance_and_never_overlap():
    got = cc.stance_windows(ROWS)
    assert got, "the stance markers should produce candidates"
    assert len(got) <= cc.MAX_CANDIDATES
    starts = sorted(w["start_ms"] for w in got)
    assert all(b - a >= cc.MAX_CLIP_S * 1000 for a, b in zip(starts, starts[1:]))
    assert got == sorted(got, key=lambda w: (-w["stance_hits"], w["start_ms"]))


def test_an_episode_with_no_stance_marker_offers_nothing():
    assert cc.stance_windows([(i * 3000, f"句子{i}") for i in range(20)]) == []


def test_no_filter_configured_means_no_clip_rather_than_an_unfiltered_one(monkeypatch):
    """Fails CLOSED on purpose: an off-topic clip is worse than no clip."""
    monkeypatch.setattr(cc, "is_decisions_model", lambda role: False)
    assert cc.relevant_score("任何內容") is None
    assert cc.on_topic_windows(_md(ROWS)) == []


def test_only_windows_over_the_floor_reach_the_writer(monkeypatch):
    monkeypatch.setattr(cc, "is_decisions_model", lambda role: True)
    scores = iter([0.05, 0.90, 0.66, 0.99])
    monkeypatch.setattr(cc, "decide", lambda *a, **kw: {"relevant": {"noul": next(scores)}})
    monkeypatch.setattr(cc, "load_prompt", lambda name: {"noul_instructions": "x"})
    kept = cc.on_topic_windows(_md(ROWS))
    assert [round(w["relevant"], 2) for w in kept] == [0.90, 0.99]


def _windows(n=2):
    return [{"start_ms": i * 60000, "end_ms": i * 60000 + 20000, "text": f"第{i}段",
             "relevant": 0.9} for i in range(n)]


def test_the_writers_choice_decides_which_window_is_clipped(monkeypatch):
    monkeypatch.setattr(cc, "on_topic_windows", lambda md: _windows(2))
    monkeypatch.setattr(cc, "write_clip_copy", lambda m: {"choice": 2, "post": "他說的是這個"})
    clip = cc.clip_for_episode({"sentences_markdown_content": "x"})
    assert clip["start_ms"] == 60000 and clip["post"] == "他說的是這個"


def test_declining_every_window_drops_the_clip(monkeypatch):
    """The writer declining IS the quality gate — the decisions model cannot judge it."""
    monkeypatch.setattr(cc, "on_topic_windows", lambda md: _windows(2))
    monkeypatch.setattr(cc, "write_clip_copy", lambda m: {"choice": None, "post": ""})
    assert cc.clip_for_episode({"sentences_markdown_content": "x"}) is None


def test_postprocess_refuses_a_choice_that_is_not_one_of_the_offered_windows():
    assert cc.postprocess({"choice": 3, "post": "有內容"}, 2) == {"choice": None, "post": ""}
    assert cc.postprocess({"choice": 1, "post": "   "}, 2) == {"choice": None, "post": ""}
    assert cc.postprocess("not json at all", 2) == {"choice": None, "post": ""}
    assert cc.postprocess({"choice": "2", "post": "有內容"}, 2)["choice"] == 2


def test_build_messages_numbers_every_candidate_and_names_the_host():
    msgs = cc.build_messages({"windows": [
        {"start_ms": 0, "end_ms": 25000, "text": "第一段話"},
        {"start_ms": 60000, "end_ms": 80000, "text": "第二段話"}],
        "source": "Gooaye 股癌", "episode_title": "EP1", "air_date": "2026-09-18"})
    user = msgs[1]["content"]
    assert "[1] 25秒" in user and "[2] 20秒" in user
    assert "第一段話" in user and "第二段話" in user
    assert "孟恭" in user          # the show's nickname, not 主持人
