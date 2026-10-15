"""Risk severity is a rendering contract, not a reason category."""

import copy

import pytest
from src.podcast.regen.schemas import validate_output


@pytest.mark.parametrize("wrapper", ["ticker_insights", "ticker_recommendations"])
@pytest.mark.parametrize("severity", ["LOW", "MEDIUM", "HIGH"])
def test_risk_severity_accepts_contract_values(wrapper, severity):
    output = {wrapper: [{"ticker": "2330", "risks": [{"severity": severity}]}]}
    assert validate_output("ticker_extractor", output) == []


@pytest.mark.parametrize("wrapper", ["ticker_insights", "ticker_recommendations"])
@pytest.mark.parametrize("risk", [
    {"severity": "SUPPLY"}, {"severity": "DEMAND"}, {"severity": "medium"},
    {"severity": ""}, {"severity": None}, {"severity": []}, {},
])
def test_risk_severity_rejects_invalid_or_missing_without_coercion(wrapper, risk):
    # invariant-gap: reason categories previously passed and rendered as unknown risk levels.
    output = {wrapper: [{"ticker": "2330", "risks": [risk]}]}
    original = copy.deepcopy(output)
    errors = validate_output("ticker_extractor", output)
    assert len(errors) == 1
    assert "ticker_insights[0].risks[0].severity" in errors[0]
    assert "LOW, MEDIUM, HIGH" in errors[0]
    assert output == original


@pytest.mark.parametrize("wrapper", ["ticker_insights", "ticker_recommendations"])
@pytest.mark.parametrize("row", [{"ticker": "2330", "risks": []}, {"ticker": "2330"}])
def test_no_risks_needs_no_invented_severity(wrapper, row):
    assert validate_output("ticker_extractor", {wrapper: [row]}) == []


@pytest.mark.parametrize("risks", [None, {}, ["SUPPLY"]])
def test_malformed_risks_rejected_before_inspecting_severity(risks):
    errors = validate_output("ticker_extractor", {"ticker_insights": [{"ticker": "2330", "risks": risks}]})
    assert errors == ["ticker_extractor: ticker_insights[0].risks must be an array of objects."]


def test_reports_each_invalid_risk_with_its_location():
    output = {"ticker_insights": [
        {"ticker": "2330", "risks": [{"severity": "SUPPLY"}, {"severity": "HIGH"}]},
        {"ticker": "2454", "risks": [{}]},
    ]}
    errors = validate_output("ticker_extractor", output)
    assert len(errors) == 2
    assert "ticker_insights[0].risks[0].severity" in errors[0]
    assert "ticker_insights[1].risks[0].severity" in errors[1]
