import pytest
from src.services.suggestion_index import SuggestionIndex
from src.schemas.search import SearchResultItem

@pytest.mark.asyncio
async def test_suggestion_index_fuzzy_matching():
    index = SuggestionIndex()
    await index.clear()
    
    # Add items
    tsmc = SearchResultItem(
        id="2330", 
        type="stock", 
        title="2330", 
        subtitle="台積電 (TSMC)", 
        link="/stock/2330",
        metadata={"mentions": 100}
    )
    nvda = SearchResultItem(
        id="NVDA", 
        type="stock", 
        title="NVDA", 
        subtitle="NVIDIA Corp", 
        link="/stock/NVDA",
        metadata={"mentions": 50} 
    )
    
    await index.add_item(tsmc, keywords=["2330", "台積電", "TSMC", "Taiwan Semiconductor"])
    await index.add_item(nvda, keywords=["NVDA", "NVIDIA"])
    
    # Test 1: Exact Ticker Match
    results = index.suggest("2330")
    assert len(results) > 0
    assert results[0].id == "2330"
    
    # Test 2: Name Token Prefix (English) - "semi" -> "Semiconductor"
    results = index.suggest("semi")
    assert len(results) > 0
    assert results[0].id == "2330"

    # Test 3: Name Token Prefix (Chinese) - "台積" -> "台積電"
    results = index.suggest("台積")
    assert len(results) > 0
    assert results[0].id == "2330"
    
    # Test 4: Case Insensitivity - "nvidia" -> "NVIDIA"
    results = index.suggest("nvidia")
    assert len(results) > 0
    assert results[0].id == "NVDA"
    
    # Test 5: Substring matching via tokenization
    # "conductor" -> "Semiconductor"? No, unless we split by camelCase or something which standard regex doesn't
    # But "Taiwan" -> "Taiwan Semiconductor" should work
    results = index.suggest("taiwan")
    assert len(results) > 0
    assert results[0].id == "2330"

@pytest.mark.asyncio
async def test_suggestion_index_scoring():
    index = SuggestionIndex()
    await index.clear()
    
    # Two items matching "App"
    # 1. "Applied Materials" (AMAT)
    # 2. "Apple" (AAPL)
    
    amat = SearchResultItem(id="AMAT", type="stock", title="AMAT", subtitle="Applied Materials", link="/stock/AMAT")
    aapl = SearchResultItem(id="AAPL", type="stock", title="AAPL", subtitle="Apple Inc.", link="/stock/AAPL")
    
    await index.add_item(amat, keywords=["AMAT", "Applied Materials"])
    await index.add_item(aapl, keywords=["AAPL", "Apple"])
    
    # Query "App"
    # "Apple" starts with "App" (Prefix match)
    # "Applied" starts with "App" (Prefix match)
    # Both are similar.
    # But "Apple" is shorter than "Applied Materials", so arguably better match?
    # Our logic sorts by score then title length.
    
    results = index.suggest("App")
    assert len(results) >= 2
    # Expect Apple first simply because it's a shorter token? 
    # Or purely arbitrary if score is same.
    # Let's verify sort logic: results.sort(key=lambda x: (x[0], -len(x[1].title)), reverse=True)
    # title for AMAT is "AMAT", AAPL is "AAPL". Same length.
    # subtitle? We don't sort by subtitle length.
    
    # Let's verify Exact Match scoring
    # Query "Apple"
    results = index.suggest("Apple")
    assert results[0].id == "AAPL"


@pytest.mark.asyncio
async def test_suggestion_index_tw_cjk_and_numeric_ticker():
    """TW stocks must be reachable by single-char CJK prefix and numeric ticker.

    Regression for the launch bug where 台積電 / 台 / 2330 returned empty stocks
    because the index was US-English-only.
    """
    index = SuggestionIndex()
    await index.clear()

    tsmc = SearchResultItem(
        id="stock-2330",
        type="stock",
        title="2330",
        subtitle="台積電",
        link="/stock/2330",
        market="TW",
    )
    await index.add_item(tsmc, keywords=["2330", "台積電", "Taiwan Semiconductor Manufacturing"])

    # Single CJK char prefix
    results = index.suggest("台")
    assert any(r.id == "stock-2330" for r in results)

    # Two-char CJK prefix
    results = index.suggest("台積")
    assert any(r.id == "stock-2330" for r in results)

    # Full CJK name
    results = index.suggest("台積電")
    assert any(r.id == "stock-2330" for r in results)

    # Numeric ticker (full and prefix)
    assert any(r.id == "stock-2330" for r in index.suggest("2330"))
    assert any(r.id == "stock-2330" for r in index.suggest("23"))


@pytest.mark.asyncio
async def test_suggestion_index_add_keywords_enriches_existing_item():
    """add_keywords() makes an already-indexed (US/English) item reachable by zh-TW
    name without creating a duplicate — the enrichment path used for US tickers like
    TSM that also have a Chinese name."""
    index = SuggestionIndex()
    await index.clear()

    tsm = SearchResultItem(
        id="stock-TSM",
        type="stock",
        title="TSM",
        subtitle="Taiwan Semiconductor Manufacturing",
        link="/stock/TSM",
        market="US",
    )
    await index.add_item(tsm, keywords=["TSM", "Taiwan Semiconductor Manufacturing"])

    # Not reachable by Chinese name yet.
    assert not any(r.id == "stock-TSM" for r in index.suggest("台積"))

    # Enrich with zh-TW name + alias.
    await index.add_keywords("stock-TSM", ["台積電", "TSMC"])

    assert any(r.id == "stock-TSM" for r in index.suggest("台積"))
    assert any(r.id == "stock-TSM" for r in index.suggest("tsmc"))
    # English path still works and there is exactly one TSM item (no duplicate).
    tsm_hits = [r for r in index.suggest("TSM") if r.id == "stock-TSM"]
    assert len(tsm_hits) == 1

    # Unknown item id is a safe no-op.
    await index.add_keywords("stock-DOES-NOT-EXIST", ["whatever"])
    assert not any(r.id == "stock-DOES-NOT-EXIST" for r in index.suggest("whatever"))
    
