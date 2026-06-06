"""Smoke tests for the shared library."""


def test_wiki_builder_importable():
    from shared.wiki_builder import (
        InMemoryWikiRepository,
        WikiPage,
        get_repository,
        ingest_episode,
        ingest_supply_chain,
    )

    assert callable(ingest_episode)
    assert callable(ingest_supply_chain)
    assert callable(get_repository)
    assert callable(InMemoryWikiRepository)
    assert callable(WikiPage)


def test_slugify():
    from shared.wiki_builder.slugify import episode_slug, slugify, ticker_slug

    assert slugify("Hello World") == "hello-world"
    assert ticker_slug("AAPL") == "aapl"
    assert episode_slug("Test Pod", 42, "Title") == "test-pod_ep42"


def test_render_entity_page_returns_record():
    from shared.wiki_builder import WikiPage, render_entity_page

    page = render_entity_page(
        entity_id="tsla", name="Tesla", entity_type="company", tickers=["TSLA"]
    )
    assert isinstance(page, WikiPage)
    assert page.kind == "entity" and page.title == "Tesla"
    assert "# Tesla" in page.body


def test_ingest_episode_writes_to_repository():
    from shared.wiki_builder import InMemoryWikiRepository, ingest_episode

    repo = InMemoryWikiRepository()
    page = ingest_episode(
        podcast_name="Test Podcast",
        episode_number=1,
        title="Test Episode",
        date="2025-01-01",
        tickers=["AAPL"],
        tags=["tech"],
        summary_text="Summary here.",
        repository=repo,
    )
    assert page.kind == "episode"
    assert repo.get_page("episode", page.slug) is not None
    assert repo.get_page("entity", "aapl") is not None
    assert repo.get_page("topic", "tech") is not None


def test_build_index_markdown():
    from shared.wiki_builder import InMemoryWikiRepository, build_index_markdown, ingest_episode

    repo = InMemoryWikiRepository()
    ingest_episode(
        podcast_name="Test", episode_number=1, title="Ep", date="2025-01-01",
        tickers=[], tags=[], summary_text="X", repository=repo,
    )
    index = build_index_markdown(repo.list_pages())
    assert "1 episodes" in index


def test_config_importable():
    from shared.config import get_env, load_yaml_config

    assert callable(load_yaml_config)
    assert callable(get_env)


def test_secrets_importable():
    from shared.secrets import bootstrap, reset

    assert callable(bootstrap)
    assert callable(reset)


def test_gcs_importable():
    from shared.gcs import create_gcs_client, get_bucket

    assert callable(create_gcs_client)
    assert callable(get_bucket)
