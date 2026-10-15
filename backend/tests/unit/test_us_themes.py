"""Contract checks for the manually curated US theme universe."""

import re

import pytest

from src.data.us_themes import US_THEMES


def test_theme_universe_has_broad_coverage_and_stable_unique_ids():
    assert 50 <= len(US_THEMES) <= 80
    assert len({symbol for theme in US_THEMES for symbol in theme["members"]}) >= 1000
    ids = [theme["exposure_id"] for theme in US_THEMES]
    assert len(ids) == len(set(ids))
    assert all(re.fullmatch(r"us_theme_[a-z0-9_]+", exposure_id) for exposure_id in ids)


@pytest.mark.parametrize("theme", US_THEMES, ids=lambda theme: theme["exposure_id"])
def test_theme_members_and_display_name(theme):
    assert isinstance(theme["name"], str) and theme["name"].strip()
    members = theme["members"]
    assert 6 <= len(members) <= 80
    assert len(members) == len(set(members))
    assert all(re.fullmatch(r"[A-Z]{1,5}(-[A-Z])?", symbol) for symbol in members)
