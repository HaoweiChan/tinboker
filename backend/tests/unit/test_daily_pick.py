"""每日一集: the choice is pure over plain dicts."""

from datetime import date, datetime, timezone

from src.services import daily_pick as dp

PRIORITY = ["Gooaye 股癌", "游庭皓的財經皓角", "財報狗"]
EPISODES = [
    {"id": "hao", "podcast_name": "游庭皓的財經皓角", "released_at_ms": 100},
    {"id": "gooaye-a", "podcast_name": "Gooaye 股癌", "released_at_ms": 200},
    {"id": "gooaye-b", "podcast_name": "Gooaye 股癌", "released_at_ms": 300},
    {"id": "dog", "podcast_name": "財報狗", "released_at_ms": 400},
    {"id": "en", "podcast_name": "CNBC's Fast Money", "released_at_ms": 500},  # not on the list
]
COUNTS = {"hao": 9, "gooaye-a": 3, "gooaye-b": 7, "dog": 12}


def test_show_priority_beats_insight_count_and_more_insights_break_ties_within_a_show():
    picks = dp.select_pick(EPISODES, COUNTS, PRIORITY, limit=1)
    assert [p["id"] for p in picks] == ["gooaye-b"]          # 股癌 first even though 皓角/財報狗 have more insights
    assert picks[0]["insights"] == 7
    assert [p["id"] for p in dp.select_pick(EPISODES, COUNTS, PRIORITY, limit=3)] == ["gooaye-b", "gooaye-a", "hao"]


def test_only_listed_shows_qualify_and_zero_limit_sends_nothing():
    assert dp.select_pick(EPISODES, COUNTS, ["CNBC's Fast Money"], limit=5)[0]["id"] == "en"
    assert dp.select_pick(EPISODES, COUNTS, ["nobody"], limit=5) == []
    assert dp.select_pick(EPISODES, COUNTS, PRIORITY, limit=0) == []


def test_day_bounds_are_taipei_midnight():
    lo, hi = dp.day_bounds_ms(date(2026, 9, 12))
    assert hi - lo == 86_400_000
    assert lo == int(datetime(2026, 9, 11, 16, 0, tzinfo=timezone.utc).timestamp() * 1000)
