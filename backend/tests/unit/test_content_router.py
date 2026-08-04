"""GCS decommission: /api/content serves the copied graphfolio-articles tree from disk."""
import pytest
from fastapi import HTTPException

from src.routers import content

BASE = "https://media.example.test/media"


@pytest.fixture
def articles(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDIA_STORAGE_ROOT", str(tmp_path))
    monkeypatch.setenv("MEDIA_PUBLIC_BASE", BASE)
    root = tmp_path / "graphfolio-articles"
    (root / "blog" / "md").mkdir(parents=True)
    (root / "blog" / "svg").mkdir(parents=True)
    (root / "articles" / "tsm").mkdir(parents=True)
    (root / "blog" / "md" / "amd_supply_chain.md").write_text("# AMD")
    (root / "blog" / "svg" / "amd_supply_chain.svg").write_text("<svg/>")
    (root / "articles" / "tsm" / "tsm_supply_chain_article.md").write_text("# TSM")
    (root / "articles" / "tsm" / "tsm_supply_chain.svg").write_text("<svg/>")
    return root


def test_index_lists_tickers_across_both_layouts(articles):
    assert content.list_content() == {"tickers": ["AMD", "TSM"]}


def test_index_empty_when_tree_absent(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDIA_STORAGE_ROOT", str(tmp_path / "nope"))
    assert content.list_content() == {"tickers": []}


def test_get_ticker_returns_stable_media_urls(articles):
    got = content.get_ticker_content("AMD")
    assert got == {
        "ticker": "AMD",
        "svg_url": f"{BASE}/graphfolio-articles/blog/svg/amd_supply_chain.svg",
        "article_url": f"{BASE}/graphfolio-articles/blog/md/amd_supply_chain.md",
        "ttl_seconds": 0,
    }


def test_get_ticker_finds_article_suffix_layout(articles):
    got = content.get_ticker_content("tsm")
    assert got["article_url"].endswith("/articles/tsm/tsm_supply_chain_article.md")
    assert got["ticker"] == "TSM"


@pytest.mark.parametrize("bad", ["NOPE", "md", "../etc", "a*", "x/y", ""])
def test_missing_or_invalid_ticker_404s(articles, bad):
    with pytest.raises(HTTPException) as e:
        content.get_ticker_content(bad)
    assert e.value.status_code == 404
