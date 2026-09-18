"""Endpoint-level regression for the typeahead 500.

`/api/search/suggest` answered HTTP 500 for a large slice of TW tickers on prod,
staging and dev (2026-09-18: "981", "00646", "0067", "00", "00685L", "2882",
"00919", "981A", "2891", "5871"). The index stores a stock as
[ticker, en_name, zh_name, *aliases] and a TW stock with no English name puts a
None in that list, which reached `kw.lower()` while scoring — so every query whose
prefix matched that stock failed, not just a query for that ticker.

The unit test in tests/unit/test_search_optimization.py covers the index class;
this one drives the actual route, because that is where the 500 was observed.
"""
import asyncio

import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.schemas.search import SearchResultItem
from src.services.suggestion_index import SuggestionIndex


@pytest.fixture
def index_with_none_keyword():
    """A populated index holding one ETF indexed with None name keywords."""
    index = SuggestionIndex()
    asyncio.get_event_loop_policy().new_event_loop().run_until_complete(_seed(index))
    yield index
    asyncio.get_event_loop_policy().new_event_loop().run_until_complete(index.clear())


async def _seed(index: SuggestionIndex):
    await index.clear()
    await index.add_item(
        SearchResultItem(
            id="stock-00685L",
            type="stock",
            title="00685L",
            subtitle="群益臺灣加權正2",
            link="/stock/00685L",
            metadata={"price": None, "change_percent": None},
        ),
        # What routers/search.py builds for a TW stock with no English name.
        keywords=["00685L", None, "群益臺灣加權正2"],
    )
    index.mark_initialized()


@pytest.mark.parametrize("q", ["00685L", "00685l", "0068", "00"])
def test_suggest_returns_200_for_a_stock_indexed_with_none_keywords(
    index_with_none_keyword, q
):
    client = TestClient(app)

    response = client.get("/api/search/suggest", params={"q": q})

    assert response.status_code == 200, response.text
    titles = [s["title"] for s in response.json()["stocks"]]
    assert "00685L" in titles
