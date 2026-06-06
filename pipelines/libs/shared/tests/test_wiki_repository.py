"""Contract tests for the in-memory WikiRepository + ingest helpers."""

from shared.wiki_builder import (
    InMemoryWikiRepository,
    NullWikiRepository,
    WikiPage,
    get_repository,
    ingest_episode,
    ingest_supply_chain,
)


def test_upsert_get_delete():
    repo = InMemoryWikiRepository()
    page = repo.upsert_page(WikiPage(kind="topic", slug="ai", title="AI", body="# AI\n"))
    assert page.created_at is not None and page.updated_at is not None
    got = repo.get_page("topic", "ai")
    assert got is not None and got.title == "AI"
    # upsert again preserves created_at
    again = repo.upsert_page(WikiPage(kind="topic", slug="ai", title="AI!", body="# AI!\n"))
    assert again.created_at == page.created_at
    assert repo.get_page("topic", "ai").title == "AI!"
    assert repo.delete_page("topic", "ai") is True
    assert repo.delete_page("topic", "ai") is False
    assert repo.get_page("topic", "ai") is None


def test_list_pages_and_frontmatter_filter():
    repo = InMemoryWikiRepository()
    repo.upsert_page(WikiPage(kind="episode", slug="e1", frontmatter={"tickers": ["TSM", "NVDA"]}))
    repo.upsert_page(WikiPage(kind="episode", slug="e2", frontmatter={"tickers": ["AAPL"]}))
    repo.upsert_page(WikiPage(kind="entity", slug="tsm", frontmatter={"entity_type": "company"}))
    assert {p.slug for p in repo.list_pages(kind="episode")} == {"e1", "e2"}
    assert {p.slug for p in repo.list_pages()} == {"e1", "e2", "tsm"}
    assert [p.slug for p in repo.list_pages(frontmatter_filter={"tickers": "TSM"})] == ["e1"]
    by_type = repo.list_pages(frontmatter_filter={"entity_type": "company"})
    assert [p.slug for p in by_type] == ["tsm"]
    # pagination
    assert len(repo.list_pages(limit=1)) == 1
    assert repo.list_pages(limit=1, offset=10) == []


def test_links_derived_from_body_and_frontmatter():
    repo = InMemoryWikiRepository()
    repo.upsert_page(
        WikiPage(
            kind="episode",
            slug="ep1",
            frontmatter={"tickers": ["TSM"], "tags": ["ai-bubble"]},
            body="# X\n\n## Related\n\n- [[entities/nvda]] — chips\n- [[topics/semiconductor]]\n",
        )
    )
    links = repo.list_links(src=("episode", "ep1"))
    out = {(link.dst_kind, link.dst_slug): link.context for link in links}
    assert out == {
        ("entity", "nvda"): "chips",
        ("topic", "semiconductor"): "",
        ("entity", "tsm"): "",
        ("topic", "ai-bubble"): "",
    }
    assert [(link.src_kind, link.src_slug) for link in repo.list_links(dst=("entity", "nvda"))] == [
        ("episode", "ep1")
    ]
    # re-upsert with different body -> links rebuilt
    repo.upsert_page(WikiPage(kind="episode", slug="ep1", body="# X\n"))
    assert repo.list_links(src=("episode", "ep1")) == []
    # deleting a page drops its links
    repo.upsert_page(WikiPage(kind="episode", slug="ep2", body="- [[entities/tsm]]\n"))
    repo.delete_page("episode", "ep2")
    assert repo.list_links(src=("episode", "ep2")) == []


def test_ingest_episode_creates_entity_and_topic_pages():
    repo = InMemoryWikiRepository()
    page = ingest_episode(
        podcast_name="Test Pod",
        episode_number=7,
        title="Ep 7",
        date="2026-01-01",
        tickers=["AAPL", "2330"],
        tags=["tech", "AI Bubble"],
        summary_text="Summary.",
        ticker_recommendations={
            "ticker_recommendations": [
                {
                    "ticker": "AAPL",
                    "sentiment": "bullish",
                    "sentiment_score": 8,
                    "bluf_thesis": "good",
                }
            ]
        },
        repository=repo,
    )
    assert page.kind == "episode" and page.slug == "test-pod_ep7"
    assert {(p.kind, p.slug) for p in repo.list_pages()} == {
        ("episode", "test-pod_ep7"),
        ("entity", "aapl"),
        ("entity", "2330"),
        ("topic", "tech"),
        ("topic", "ai-bubble"),
    }
    aapl = repo.get_page("entity", "aapl")
    assert "[[episodes/test-pod_ep7]]" in aapl.body
    assert "## Ticker History" in aapl.body and "good" in aapl.body

    # ingesting a second episode mentioning AAPL again -> one extra mention, no dupes
    ingest_episode(
        podcast_name="Other", episode_number=1, title="O1", date="2026-01-02",
        tickers=["AAPL"], tags=["tech"], summary_text="S2", repository=repo,
    )
    aapl = repo.get_page("entity", "aapl")
    assert aapl.body.count("[[episodes/") == 2
    # idempotent: re-ingesting the SAME episode does not duplicate the mention
    ingest_episode(
        podcast_name="Other", episode_number=1, title="O1", date="2026-01-02",
        tickers=["AAPL"], tags=["tech"], summary_text="S2", repository=repo,
    )
    assert repo.get_page("entity", "aapl").body.count("[[episodes/") == 2


def test_ingest_episode_uses_ticker_registry():
    repo = InMemoryWikiRepository()
    ingest_episode(
        podcast_name="Gooaye", episode_number=571, title="EP571", date="2026-05-12",
        tickers=["2330.TW", "NVDA", "SPY", "ZZZZ"], tags=["半導體"], summary_text="s",
        repository=repo,
    )
    # aliases canonicalized; episode frontmatter uses canonical symbols
    ep = repo.get_page("episode", "gooaye_ep571")
    assert ep.frontmatter["tickers"] == ["2330", "NVDA", "SPY", "ZZZZ"]
    # known tickers -> real name + market + sector + type
    tsmc = repo.get_page("entity", "2330")
    assert tsmc is not None and tsmc.title == "台積電"
    assert tsmc.frontmatter["name"] == "台積電"
    assert tsmc.frontmatter["market"] == "TW" and tsmc.frontmatter["sector"] == "半導體"
    assert repo.get_page("entity", "spy").frontmatter["entity_type"] == "etf"
    # unknown ticker -> falls back to the raw symbol, no market/sector
    zzzz = repo.get_page("entity", "zzzz")
    assert zzzz.frontmatter["name"] == "ZZZZ"
    assert "market" not in zzzz.frontmatter and "sector" not in zzzz.frontmatter
    # the alias did not create a separate "2330-tw" page
    assert repo.get_page("entity", "2330-tw") is None


def test_ingest_supply_chain():
    repo = InMemoryWikiRepository()
    n = ingest_supply_chain(
        entities=[
            {"id": "tsmc", "type": "company", "props": {"name": "TSMC"}},
            {"id": "nvidia", "type": "company", "props": {"name": "NVIDIA"}},
        ],
        edges=[{"src": "tsmc", "dst": "nvidia", "rel": "SUPPLIES", "props": {"status": "active"}}],
        repository=repo,
    )
    assert n >= 1
    sc = repo.get_page("supply_chain", "tsmc")
    assert sc is not None and "[[entities/nvidia]]" in sc.body
    assert repo.get_page("entity", "tsmc") is not None
    assert repo.get_page("entity", "nvidia") is not None


def test_get_repository_factory(monkeypatch):
    monkeypatch.delenv("WIKI_DATABASE_URL", raising=False)
    assert isinstance(get_repository(), NullWikiRepository)
    # explicit empty string -> still Null
    assert isinstance(get_repository(""), NullWikiRepository)


def test_null_repository_is_noop():
    repo = NullWikiRepository()
    assert repo.upsert_page(WikiPage(kind="topic", slug="x")).slug == "x"
    assert repo.get_page("topic", "x") is None
    assert repo.list_pages() == []
    assert repo.list_links() == []
    assert repo.delete_page("topic", "x") is False
    assert repo.health()["status"] == "degraded"
    # ingest_episode against a Null repo must not raise
    ingest_episode(
        podcast_name="P", episode_number=1, title="T", date="2026-01-01",
        tickers=["X"], tags=["y"], summary_text="s", repository=repo,
    )
