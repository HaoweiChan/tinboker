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


@pytest.mark.parametrize(
    ("theme_id", "off_theme_symbols"),
    [
        ("electric_vehicles", {"MSFT", "NVDA", "INTC", "GOOGL", "QCOM"}),
        ("autonomous_driving", {"ALB", "QS", "EVGO"}),
        ("battery_materials", {"LIN", "APD", "BE", "PLUG", "FCEL"}),
        ("lithium_mining", {"RIO"}),
        ("robotics", {"DE", "GOOGL", "NVDA"}),
        ("fintech", {"RIOT", "MARA", "CIFR"}),
        ("social_media", {"GRPN", "FVRR", "ANGI"}),
        ("quantum_computing", {"QMCO", "MSFT", "NVDA"}),
        ("residential_reits", {"PSA", "EXR", "CUBE", "ARE", "SMA"}),
    ],
)
def test_narrow_baskets_exclude_misleading_post_leaders(theme_id, off_theme_symbols):
    """Guard the review's concrete wrong-copy cases, not the entire membership list."""
    theme = next(t for t in US_THEMES if t["exposure_id"] == f"us_theme_{theme_id}")
    assert not off_theme_symbols.intersection(theme["members"])


@pytest.mark.parametrize(
    ("theme_id", "name", "representative"),
    [
        ("memory", "記憶體", "MU"),
        ("taiwan_adrs", "台廠 ADR", "TSM"),
        ("quantum_computing", "量子電腦", "IONQ"),
        ("semiconductor_equipment", "半導體設備", "AMAT"),
    ],
)
def test_requested_missing_themes_are_usable(theme_id, name, representative):
    theme = next(t for t in US_THEMES if t["exposure_id"] == f"us_theme_{theme_id}")
    assert theme["name"] == name
    assert len(theme["members"]) >= 6
    assert representative in theme["members"]
