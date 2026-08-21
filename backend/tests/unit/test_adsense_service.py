"""AdSense report parsing: cells come back as strings with no type information
beyond the header, and the whole ``totals``/``rows`` block is *absent* while a site
is still under review — both shapes have to survive without a KeyError."""

from src.services import adsense_service as svc

# Trimmed real reports:generate shape (dimension + one tally + one currency + one ratio).
_PAYLOAD = {
    "headers": [
        {"name": "DATE", "type": "DIMENSION"},
        {"name": "PAGE_VIEWS", "type": "METRIC_TALLY"},
        {"name": "ESTIMATED_EARNINGS", "type": "METRIC_CURRENCY", "currencyCode": "USD"},
        {"name": "IMPRESSIONS_CTR", "type": "METRIC_RATIO"},
    ],
    "rows": [
        {"cells": [{"value": "2026-08-18"}, {"value": "1240"}, {"value": "1.83"}, {"value": "0.0142"}]},
        {"cells": [{"value": "2026-08-19"}, {"value": "1310"}, {"value": "2.07"}, {"value": "0.0158"}]},
    ],
    "totals": {"cells": [{"value": ""}, {"value": "2550"}, {"value": "3.90"}, {"value": "0.0150"}]},
}


def test_rows_typed_by_header():
    rows = svc._rows(_PAYLOAD)
    assert rows[0] == {
        "DATE": "2026-08-18",
        "PAGE_VIEWS": 1240,
        "ESTIMATED_EARNINGS": 1.83,
        "IMPRESSIONS_CTR": 0.0142,
    }
    assert isinstance(rows[0]["PAGE_VIEWS"], int)


def test_totals_skip_the_dimension_cell():
    totals = svc._totals(_PAYLOAD)
    assert totals == {"PAGE_VIEWS": 2550, "ESTIMATED_EARNINGS": 3.90, "IMPRESSIONS_CTR": 0.0150}
    assert "DATE" not in totals


def test_empty_report_is_not_an_error():
    """What the API actually returns today: headers only, no rows, no totals."""
    empty = {"headers": _PAYLOAD["headers"]}
    assert svc._rows(empty) == []
    assert svc._totals(empty) == {}


def test_unparseable_cell_degrades_to_zero():
    broken = {"headers": _PAYLOAD["headers"], "rows": [{"cells": [{"value": "d"}, {"value": None}, {}, {}]}]}
    assert svc._rows(broken)[0]["PAGE_VIEWS"] == 0
