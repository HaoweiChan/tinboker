"""Regression tests from the M1 adversarial review (TKB-009).

1. Hidden / redirect-source tag_registry rows must NOT feed the board membership
   index — resolving them into the canonical id would inherit stale members and
   overwrite canonical metadata.
2. Sector-page Firestore queries must include the legacy ``theme_<id>`` alias so
   pre-migration episode snapshots (docs/firestore-contract.md §2.1.1) stay reachable.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from src.services.podcast import PodcastService, _sector_query_ids
from src.tag_registry import TIER_HIDDEN


def _row(exposure_id, tier="canonical", members=None, display="X", etype="theme", parent=None):
    return SimpleNamespace(
        exposure_id=exposure_id,
        tier=tier,
        exposure_type=etype,
        display_zh=display,
        description=None,
        members=members or [],
        parent_id=parent,
        kind="sector",
    )


def _index_with(rows, redirects):
    session = MagicMock()
    session.query.return_value.filter.return_value.all.return_value = rows
    session_local = MagicMock(return_value=session)
    with (
        patch("src.database.postgres.SessionLocal", session_local),
        patch("src.services.podcast._sector_redirects", return_value=redirects),
    ):
        return PodcastService._sector_membership_index()


def test_hidden_redirect_source_row_does_not_pollute_canonical():
    rows = [
        _row("sector_new", members=[{"ticker": "2330", "name": "台積電"}], display="新題材"),
        _row("sector_old", tier=TIER_HIDDEN, members=[{"ticker": "9999", "name": "stale"}], display="舊題材"),
    ]
    idx = _index_with(rows, {"sector_old": "sector_new"})
    assert "9999" not in idx["ticker_to_sectors"], "hidden redirect row leaked members into the board"
    assert "sector_new" in idx["ticker_to_sectors"].get("2330", set())
    assert idx["meta"]["sector_new"]["display_name"] == "新題材"


def test_visible_redirect_source_row_is_still_skipped():
    # Belt-and-braces: even if sync failed to hide it, a redirect-source row must not contribute.
    rows = [
        _row("sector_new", members=[{"ticker": "2330"}], display="新題材"),
        _row("sector_old", members=[{"ticker": "9999"}], display="舊題材"),
    ]
    idx = _index_with(rows, {"sector_old": "sector_new"})
    assert "9999" not in idx["ticker_to_sectors"]
    assert idx["meta"]["sector_new"]["display_name"] == "新題材"


def test_hidden_stale_row_without_redirect_is_skipped():
    rows = [
        _row("sector_new", members=[{"ticker": "2330"}]),
        _row("sector_ic_design", tier=TIER_HIDDEN, members=[{"ticker": "8888"}]),
    ]
    idx = _index_with(rows, {})
    assert "8888" not in idx["ticker_to_sectors"]
    assert "sector_ic_design" not in idx["meta"]


def test_sector_query_ids_include_legacy_theme_alias():
    with patch("src.services.podcast._sector_redirects", return_value={}):
        ids = _sector_query_ids("sector_ai_server")
    assert set(ids) == {"sector_ai_server", "theme_ai_server"}


def test_sector_query_ids_cover_redirect_sources_and_their_theme_aliases():
    redirects = {"sector_jp_wafer": "sector_silicon_wafer"}
    with patch("src.services.podcast._sector_redirects", return_value=redirects):
        ids = _sector_query_ids("sector_silicon_wafer")
    assert set(ids) == {
        "sector_jp_wafer",
        "sector_silicon_wafer",
        "theme_jp_wafer",
        "theme_silicon_wafer",
    }
