import pytest

from src.services.taxonomy_validation import TaxonomyValidationError, validate_taxonomy


def _member(ticker: str, reason: str = "", market: str = "TW") -> dict:
    return {
        "ticker": ticker,
        "name": ticker,
        "market": market,
        "source": "test",
        "reason": reason,
    }


def _sector(
    exposure_id: str,
    members: list[dict],
    exposure_type: str = "theme",
    group: str | None = None,
) -> dict:
    return {
        "exposure_id": exposure_id,
        "display_name": exposure_id,
        "exposure_type": exposure_type,
        "group": group,
        "members": members,
    }


def test_duplicate_reason_allows_parent_child_only():
    allowed = [
        _sector("sector_parent", [_member("1001", "same")], "industry"),
        _sector("sector_child", [_member("1001", "same")], "theme", "sector_parent"),
    ]
    validate_taxonomy(allowed, {}, enforce=True)

    rejected = allowed + [_sector("sector_peer", [_member("1001", "same")])]
    with pytest.raises(TaxonomyValidationError) as exc:
        validate_taxonomy(rejected, {}, enforce=True)

    assert exc.value.rule == "duplicate non-empty member reasons"
    assert "sector_peer" in exc.value.offenders[0]


def test_jaccard_overlap_rejects_non_parent_child_overlap():
    seed = [
        _sector("sector_a", [_member("1001"), _member("1002")]),
        _sector("sector_b", [_member("1001"), _member("1002")]),
    ]

    with pytest.raises(TaxonomyValidationError) as exc:
        validate_taxonomy(seed, {}, enforce=True)

    assert exc.value.rule.startswith("redundant sector membership")
    assert exc.value.offenders == ["sector_a / sector_b: 1.00"]


def test_redirect_target_must_exist():
    with pytest.raises(TaxonomyValidationError) as exc:
        validate_taxonomy(
            [_sector("sector_a", [_member("1001")])],
            {"sector_old": "sector_missing"},
            enforce=True,
        )

    assert exc.value.rule == "redirect targets missing from taxonomy"
    assert exc.value.offenders == ["sector_missing"]


def test_rejects_empty_sector_and_us_member():
    with pytest.raises(TaxonomyValidationError) as empty_exc:
        validate_taxonomy([_sector("sector_empty", [])], {}, enforce=True)
    assert empty_exc.value.offenders == ["sector_empty"]

    with pytest.raises(TaxonomyValidationError) as us_exc:
        validate_taxonomy([_sector("sector_us", [_member("AAPL", market="US")])], {}, enforce=True)
    assert us_exc.value.rule == "US tickers leaked into the TW taxonomy"


def test_member_reason_requirement_default_off(monkeypatch):
    monkeypatch.delenv("TAXONOMY_REQUIRE_MEMBER_REASONS", raising=False)

    validate_taxonomy([_sector("sector_a", [_member("1001")])], {}, enforce=False)


def test_member_reason_requirement_rejects_only_new_empty_members(monkeypatch):
    monkeypatch.setenv("TAXONOMY_REQUIRE_MEMBER_REASONS", "true")
    previous = [_sector("sector_a", [_member("1001")])]
    unchanged = [_sector("sector_a", [_member("1001")])]
    added_empty = [_sector("sector_a", [_member("1001"), _member("2002")])]
    added_filled = [_sector("sector_a", [_member("1001"), _member("2002", "new reason")])]

    validate_taxonomy(unchanged, {}, enforce=False, previous_sectors=previous)
    validate_taxonomy(added_filled, {}, enforce=False, previous_sectors=previous)
    with pytest.raises(TaxonomyValidationError) as exc:
        validate_taxonomy(added_empty, {}, enforce=False, previous_sectors=previous)

    assert exc.value.rule == "new members require non-empty reasons"
    assert exc.value.offenders == ["sector_a/2002"]
