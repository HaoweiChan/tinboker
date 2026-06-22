"""Unit tests for Apple-Podcasts-chart channel popularity ranking.

Covers the pure parse/match logic in PodcastService — no network, no Firestore.
"""
from src.services.podcast import PodcastService


def _entry(apple_id: str, name: str) -> dict:
    """Shape of one Apple top-podcasts RSS feed entry."""
    return {
        "id": {"attributes": {"im:id": apple_id}},
        "im:name": {"label": name},
    }


def test_parse_apple_charts_ranks_in_order_across_genres():
    business = [_entry("1", "Gooaye 股癌"), _entry("2", "財經一路發")]
    technology = [_entry("9", "曲博科技教室")]

    ranks = PodcastService._parse_apple_charts([business, technology])

    # Business chart ranks first (1, 2), Technology backfills after it (3).
    assert ranks["gooaye 股癌"] == 1
    assert ranks["財經一路發"] == 2
    assert ranks["曲博科技教室"] == 3


def test_parse_apple_charts_dedupes_show_in_two_charts_keeping_best_rank():
    business = [_entry("1", "Gooaye 股癌"), _entry("2", "財報狗")]
    technology = [_entry("2", "財報狗"), _entry("9", "曲博科技教室")]

    ranks = PodcastService._parse_apple_charts([business, technology])

    assert ranks["財報狗"] == 2          # keeps the earlier (Business) rank
    assert ranks["曲博科技教室"] == 3      # not bumped by the duplicate


def test_parse_apple_charts_handles_malformed_entries():
    ranks = PodcastService._parse_apple_charts([
        ["not-a-dict", {}, _entry("1", "Gooaye 股癌"), {"im:name": {"label": ""}}],
    ])
    assert ranks == {"gooaye 股癌": 1}


def test_popularity_rank_for_matches_chart_title_with_tagline():
    # Apple titles often carry a tagline; our stored name is the bare show name.
    ranks = {
        "財報狗 - 掌握台股美股時事議題": 12,
        "macromicro 財經m平方": 10,
        "美股投資學-財女珍妮": 15,
    }
    assert PodcastService._popularity_rank_for("財報狗", ranks) == 12
    assert PodcastService._popularity_rank_for("財經M平方", ranks) == 10
    assert PodcastService._popularity_rank_for("財女珍妮", ranks) == 15


def test_popularity_rank_for_unranked_show_is_none():
    ranks = {"gooaye 股癌": 1}
    assert PodcastService._popularity_rank_for("不存在的節目", ranks) is None
    assert PodcastService._popularity_rank_for("Gooaye 股癌", {}) is None
    assert PodcastService._popularity_rank_for("", ranks) is None


def test_popularity_rank_for_returns_best_rank_on_multiple_matches():
    ranks = {"股癌": 5, "gooaye 股癌": 1}
    # source "Gooaye 股癌" contains/contained-by both; takes the lower (better) rank.
    assert PodcastService._popularity_rank_for("Gooaye 股癌", ranks) == 1
