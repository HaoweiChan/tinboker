"""Tests for the markdown views over wiki records."""

import yaml
from shared.wiki_builder import (
    InMemoryWikiRepository,
    WikiPage,
    build_index_markdown,
    ingest_episode,
    page_to_markdown,
    render_entity_page,
    render_episode_page,
    render_topic_page,
)


def test_page_to_markdown_round_trips_frontmatter():
    page = WikiPage(
        kind="episode",
        slug="p_ep1",
        title="Ep 1",
        frontmatter={"podcast": "P", "episode_number": 1, "tickers": ["TSM", "2330"]},
        body="# Ep 1\n\nbody text\n",
    )
    md = page_to_markdown(page)
    assert md.startswith("---\n")
    front_block = md.split("---", 2)[1]
    front = yaml.safe_load(front_block)
    assert front["type"] == "episode"
    assert front["podcast"] == "P"
    assert front["episode_number"] == 1
    assert front["tickers"] == ["TSM", "2330"]
    assert "# Ep 1" in md and "body text" in md


def test_render_functions_return_pages():
    ep = render_episode_page(
        podcast_name="Pod", episode_number=2, title="T", date="2026-01-01",
        tickers=["AAPL"], tags=["tech"], summary_text="sum",
        events_markdown="- x", ticker_recommendations=None, source_urls={"mp3": "gs://x"},
    )
    assert ep.kind == "episode" and ep.slug == "pod_ep2"
    assert ep.frontmatter["source_urls"] == {"mp3": "gs://x"}
    assert "[[entities/aapl]]" in ep.body and "[[topics/tech]]" in ep.body

    ent = render_entity_page(entity_id="aapl", name="AAPL", entity_type="company", tickers=["AAPL"])
    assert ent.kind == "entity" and "type: entity" in page_to_markdown(ent)

    top = render_topic_page(topic_id="tech", name="Tech")
    assert top.kind == "topic" and top.frontmatter == {"id": "tech", "name": "Tech"}


def test_build_index_markdown():
    repo = InMemoryWikiRepository()
    ingest_episode(
        podcast_name="Pod", episode_number=1, title="Ep1", date="2026-01-02",
        tickers=["TSM"], tags=["ai"], summary_text="s", repository=repo,
    )
    idx = build_index_markdown(repo.list_pages())
    assert "1 episodes" in idx
    assert "[[episodes/pod_ep1|Ep1]]" in idx
    assert "## Entities" in idx and "## Topics" in idx
