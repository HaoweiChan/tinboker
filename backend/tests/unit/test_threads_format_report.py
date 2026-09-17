"""Per-format engagement roll-up: the yardstick for which Threads formats survive."""
from src.services.threads_insights_service import group_by_format


def test_groups_by_format_with_median_views_and_summed_shares():
    rows = [
        {"format": "episode_thread", "metrics": {"views": 100, "shares": 1}},
        {"format": "episode_thread", "metrics": {"views": 10_000, "shares": 40}},
        {"format": "episode_thread", "metrics": {"views": 300, "shares": 2}},
        {"format": "post_hoc_winner", "metrics": {"views": 900, "shares": 9}},
    ]
    report = {r["format"]: r for r in group_by_format(rows)}
    assert report["episode_thread"]["posts"] == 3
    assert report["episode_thread"]["views_median"] == 300   # not the 3,466 mean
    assert report["episode_thread"]["views_total"] == 10_400
    assert report["episode_thread"]["shares"] == 43
    assert report["post_hoc_winner"]["views_median"] == 900


def test_unmeasured_and_legacy_rows_are_counted_but_do_not_skew_stats():
    rows = [
        {"format": None, "metrics": {"views": 5}},
        {"format": "episode_thread", "metrics": {}, "error": "boom"},
        {"format": "episode_thread", "metrics": {"views": 50}},
    ]
    report = {r["format"]: r for r in group_by_format(rows)}
    assert report["unknown"]["posts"] == 1
    assert report["episode_thread"] == {
        "format": "episode_thread", "posts": 2, "measured": 1, "views_median": 50,
        "views_total": 50, "likes": 0, "replies": 0, "reposts": 0, "quotes": 0, "shares": 0,
    }
