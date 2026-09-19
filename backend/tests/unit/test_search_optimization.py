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
    


@pytest.mark.asyncio
async def test_suggest_survives_none_keywords():
    """A TW ETF with no English name indexes as [ticker, None, zh] and used to 500.

    routers/search.py builds keywords as [ticker, en, zh, *aliases]; either name can be
    None. _calculate_score then called kw.lower() on it, so every suggest query whose
    prefix matched that stock answered 500 in prod (2026-09-18: "981", "00646", "00685L").
    """
    index = SuggestionIndex()
    await index.clear()

    etf = SearchResultItem(
        id="stock-00685L",
        type="stock",
        title="00685L",
        subtitle="群益臺灣加權正2",
        link="/stock/00685L",
        metadata={"price": None, "change_percent": None},
    )
    await index.add_item(etf, keywords=["00685L", None, "群益臺灣加權正2", None])

    for prefix in ("00685L", "00685l", "0068", "00"):
        results = index.suggest(prefix)
        assert any(r.id == "stock-00685L" for r in results), prefix


# ── Typing a TW code without its leading zeros (981A → 00981A) ────────────────

def test_bare_tw_code_variants():
    from src.routers.search import _bare_tw_code

    assert _bare_tw_code("00981A") == "981A"   # 主動統一台股增長
    assert _bare_tw_code("0050") == "50"
    assert _bare_tw_code("2330") is None       # nothing to strip
    assert _bare_tw_code("AAPL") is None       # US
    assert _bare_tw_code("005930") is None     # KR, not ours to index as TW


def test_suggest_finds_a_padded_tw_code_typed_bare():
    """The real listing answers "981a"; before this the only hit was a junk stub
    literally stored under the ticker "981A"."""
    import asyncio
    from src.services.suggestion_index import SuggestionIndex
    from src.schemas.search import SearchResultItem
    from src.routers.search import _bare_tw_code

    async def run():
        index = SuggestionIndex()
        await index.clear()
        item = SearchResultItem(id="stock-00981A", type="stock", title="00981A",
                                subtitle="主動統一台股增長", link="/stock/00981A", market="TW")
        await index.add_item(item, keywords=["00981A", "主動統一台股增長", _bare_tw_code("00981A")])
        return [i.title for i in index.suggest("981a")], [i.title for i in index.suggest("00981a")]

    bare, padded = asyncio.run(run())
    assert bare == ["00981A"]
    assert padded == ["00981A"]


# ── 981A is 00981A: the bare code resolves to the listing that exists ─────────

def test_canonical_tw_ticker_resolves_the_bare_code(tmp_path, monkeypatch):
    import src.database.postgres as pg
    from src.config import settings

    prev = (pg.engine, pg.SessionLocal, settings.use_postgres, settings.database_path)
    settings.use_postgres = False
    settings.database_path = str(tmp_path / "canon.db")
    pg.engine = None
    pg.SessionLocal = None
    pg.init_engine()
    from src.database import models  # noqa: F401
    from src.database.models import StockTranslation
    pg.create_all_tables()
    try:
        for session in pg.get_session():
            session.add(StockTranslation(ticker="00981A", market="TW",
                                         name_zh_tw="主動統一台股增長", translation_status="auto"))
            session.add(StockTranslation(ticker="2330", market="TW", name_zh_tw="台積電",
                                         translation_status="approved"))
            session.commit()
            break

        from src.routers.stock import _canonical_tw_ticker
        assert _canonical_tw_ticker("981A") == "00981A"   # the spoken form
        assert _canonical_tw_ticker("2330") == "2330"     # already a listing
        assert _canonical_tw_ticker("9999") == "9999"     # nothing to resolve to
        assert _canonical_tw_ticker("AAPL") == "AAPL"     # not TW
    finally:
        pg.engine, pg.SessionLocal, settings.use_postgres, settings.database_path = prev


# ── Rebuilding the index without restarting the process ──────────────────────

def test_rebuild_index_drops_a_deleted_row_and_needs_the_internal_key(monkeypatch):
    """A row deleted from the DB must be gone from typeahead after a rebuild — that is
    the whole point: production kept suggesting the junk 981A stub after it was deleted,
    and only a container restart cleared it."""
    import asyncio
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from src.config import settings
    from src.routers import search as search_router
    from src.schemas.search import SearchResultItem
    from src.services.suggestion_index import SuggestionIndex

    index = SuggestionIndex()

    async def _seed_stale():
        await index.clear()
        await index.add_item(
            SearchResultItem(id="stock-981A", type="stock", title="981A",
                             subtitle="(Probable bond ETF variant)", link="/stock/981A", market="TW"),
            keywords=["981A"],
        )
    asyncio.run(_seed_stale())
    assert [i.title for i in index.suggest("981a")] == ["981A"]

    # The real build reads every source; stand in for it with the row that survived.
    async def fake_build():
        await index.add_item(
            SearchResultItem(id="stock-00981A", type="stock", title="00981A",
                             subtitle="主動統一台股增長", link="/stock/00981A", market="TW"),
            keywords=["00981A", "981A", "主動統一台股增長"],
        )
        index.mark_initialized()
    monkeypatch.setattr(search_router, "build_search_index", fake_build)

    prev_key = settings.internal_api_key
    settings.internal_api_key = "test-secret-key"
    app = FastAPI()
    app.include_router(search_router.router)
    client = TestClient(app)
    try:
        assert client.post("/api/search/rebuild-index").status_code == 401
        assert client.post("/api/search/rebuild-index",
                           headers={"X-Internal-Key": "nope"}).status_code == 401

        resp = client.post("/api/search/rebuild-index", headers={"X-Internal-Key": "test-secret-key"})
        assert resp.status_code == 200, resp.text
        assert resp.json()["items"] == 1  # cleared first: the stale row is gone, not merged
        assert [i.title for i in index.suggest("981a")] == ["00981A"]
    finally:
        settings.internal_api_key = prev_key
        asyncio.run(index.clear())


# ── CJK names are findable by the part a reader remembers, not only by their first char ──

def _cjk_index():
    """A small index with the real names that exposed the bug."""
    import asyncio
    from src.schemas.search import SearchResultItem
    from src.services.suggestion_index import SuggestionIndex

    index = SuggestionIndex()

    async def build():
        await index.clear()
        for iid, title, sub, kws in [
            ("podcast-兆華與股惑仔", "兆華與股惑仔", "446 episodes", ["兆華與股惑仔"]),
            ("podcast-財經一路發", "財經一路發", "podcast", ["財經一路發"]),
            ("stock-2330", "2330", "台積電", ["2330", "台積電", "Taiwan Semiconductor"]),
            ("stock-0050", "0050", "元大台灣50", ["0050", "元大台灣50"]),
            ("stock-TSM", "TSM", "台積電 ADR", ["TSM", "Taiwan Semiconductor Manufacturing"]),
        ]:
            await index.add_item(
                SearchResultItem(id=iid, type="podcast" if iid.startswith("podcast") else "stock",
                                 title=title, subtitle=sub, link="/x"),
                keywords=kws,
            )
        index.mark_initialized()

    asyncio.run(build())
    return index


def test_cjk_substring_finds_the_name():
    index = _cjk_index()
    try:
        assert [i.title for i in index.suggest("股惑仔")] == ["兆華與股惑仔"]
        assert [i.title for i in index.suggest("惑仔")] == ["兆華與股惑仔"]
        assert [i.title for i in index.suggest("兆華")] == ["兆華與股惑仔"]   # prefix still works
        assert [i.title for i in index.suggest("一路發")] == ["財經一路發"]
        assert "2330" in [i.title for i in index.suggest("積電")]
        assert "0050" in [i.title for i in index.suggest("台灣50")]
    finally:
        import asyncio; asyncio.run(index.clear())


def test_prefix_still_outranks_a_mid_name_match():
    """台積 must not demote 台積電 below something that only contains it."""
    import asyncio
    from src.schemas.search import SearchResultItem

    index = _cjk_index()
    try:
        async def add_noise():
            await index.add_item(
                SearchResultItem(id="stock-9999", type="stock", title="9999",
                                 subtitle="供應台積電設備", link="/x"),
                keywords=["9999", "供應台積電設備"],
            )
        asyncio.run(add_noise())
        titles = [i.title for i in index.suggest("台積")]
        assert titles[0] in ("2330", "TSM"), titles   # the real 台積電 rows lead
        assert "9999" in titles                        # the mid-name match is still findable
        assert titles.index("9999") > 0
    finally:
        asyncio.run(index.clear())


def test_latin_matching_is_unchanged():
    index = _cjk_index()
    try:
        assert "TSM" in [i.title for i in index.suggest("taiwan")]
        assert [i.title for i in index.suggest("2330")] == ["2330"]
        assert index.suggest("xyz") == []
    finally:
        import asyncio; asyncio.run(index.clear())
