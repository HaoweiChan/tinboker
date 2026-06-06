"""Tests for shared.wiki_builder.episode_view (feed item + detail shaping, body parsing)."""

from shared.wiki_builder import InMemoryWikiRepository, episode_view, ingest_episode
from shared.wiki_builder.episode_view import summary_text


def _names(repo):
    return {p.slug: dict(p.frontmatter) for p in repo.list_pages(kind="entity")}


def test_feed_item_and_detail():
    repo = InMemoryWikiRepository()
    ep = ingest_episode(
        podcast_name="股癌", episode_number=1, title="EP1 大事", date="2026-05-12",
        tickers=["2330.TW", "NVDA"], tags=["半導體"],
        summary_text="這集講台積電。\n\n第二段。",
        events_markdown="- 2026-05-10: 法說會",
        ticker_recommendations={
            "ticker_recommendations": [
                {"ticker": "2330.TW", "sentiment": "bullish", "sentiment_score": 8,
                 "time_horizon": "中期", "bluf_thesis": "良率好"},
                {"ticker": "NVDA", "sentiment": "bull", "sentiment_score": 9,
                 "time_horizon": "長期", "bluf_thesis": "GPU 需求"},
            ]
        },
        source_urls={"mp3": "gs://b/a.mp3", "transcript": "gs://b/a.json"},
        repository=repo,
    )
    page = repo.get_page("episode", ep.slug)
    names = _names(repo)

    item = episode_view.feed_item(page, names)
    assert item["slug"] == ep.slug and item["podcast"] == "股癌" and item["episode_number"] == 1
    assert item["title"] == "EP1 大事" and item["date"] == "2026-05-12"
    assert "台積電" in item["summary_excerpt"]
    syms = {t["sym"]: t for t in item["tickers"]}
    tsmc = syms["2330"]
    assert tsmc["name"] == "台積電" and tsmc["market"] == "TW" and tsmc["sentiment"] == "bull"
    assert syms["NVDA"]["name"] == "輝達" and syms["NVDA"]["sentiment"] == "bull"
    assert item["tags"] == ["半導體"] and item["source_urls"]["mp3"] == "gs://b/a.mp3"

    detail = episode_view.episode_detail(page, names, {})
    assert detail["summary"].startswith("這集講台積電") and "第二段" in detail["summary"]
    assert detail["events_markdown"] == "- 2026-05-10: 法說會"
    recs = {r["sym"]: r for r in detail["ticker_recommendations"]}
    assert recs["2330"]["sentiment"] == "bull" and recs["2330"]["thesis"] == "良率好"
    assert recs["2330"]["sentiment_score"] == "8" and recs["2330"]["time_horizon"] == "中期"
    # thesis/score attached onto the ticker rows too
    theses = {t["sym"]: t.get("thesis") for t in detail["tickers"]}
    assert theses == {"2330": "良率好", "NVDA": "GPU 需求"}
    # related links parsed from the rendered body
    assert {"slug": "2330", "name": "台積電"} in detail["related"]["entities"]
    assert {"slug": "半導體", "name": "半導體"} in detail["related"]["topics"]
    # slice-D placeholders
    assert detail["bullets"] == [] and detail["chapters"] == [] and detail["clips"] == []


def test_parse_ticker_recommendations_empty():
    assert episode_view.parse_ticker_recommendations("# T\n\nno rec table here\n") == []


def test_summary_text_stops_at_first_section():
    body = "# Title\n\nfirst line\nsecond line\n\n## Events Timeline\n\n- x\n"
    assert summary_text(body) == "first line\nsecond line"
    assert summary_text("no heading at all") == ""
