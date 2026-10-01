"""free_insight_counts: the rows a non-member can read on a /stock page, per ticker.

The sitemap lists a stock page on this count, and the crawler middleware serves exactly
these rows, so the window sent to the store is the contract.
"""
import asyncio
from datetime import datetime, timedelta, timezone

from src.services import insight_service as svc


class _Store:
    def __init__(self, docs):
        self.docs = docs
        self.calls = []

    def query_collection_group(self, collection, filters, order_by, direction, limit):
        self.calls.append((collection, filters))
        return self.docs


def test_counts_supported_rows_per_ticker_inside_the_free_window():
    v = svc.SCHEMA_VERSION
    store = _Store([
        {"ticker": "2330", "schema_version": v},
        {"ticker": "2330", "schema_version": 2},
        {"ticker": "NVDA", "schema_version": v},
        {"ticker": "2330", "schema_version": 1},   # legacy row the API never serves
        {"ticker": "", "schema_version": v},
    ])
    service = svc.InsightService.__new__(svc.InsightService)
    service._fs = store

    counts = asyncio.run(service.free_insight_counts())

    assert counts == {"2330": 2, "NVDA": 1}
    (collection, filters), = store.calls
    assert collection == svc.INSIGHTS_SUBCOLLECTION
    (f1, op1, start), (f2, op2, end) = filters
    assert (f1, op1, f2, op2) == ("podcast_launch_time", ">=", "podcast_launch_time", "<=")
    now = datetime.now(timezone.utc)
    assert start == (now - timedelta(days=90)).strftime("%Y-%m-%dT00:00:00Z")
    # The newest paywall_days are members-only, so they must not make a page "listable".
    assert end[:10] == (now - timedelta(days=svc.INSIGHT_PAYWALL_DAYS)).strftime("%Y-%m-%d")
    # Stored timestamps look like 2026-09-30T07:54:31Z and are compared as strings.
    assert len(end) == len("2026-09-30T07:54:31Z") and end.endswith("Z")
