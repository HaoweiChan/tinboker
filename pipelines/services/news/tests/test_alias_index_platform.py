"""build_alias_index merges operator-curated aliases pulled from the platform."""

from __future__ import annotations

from news import alias_index as ai
from shared.wiki_builder import InMemoryWikiRepository


def test_build_alias_index_merges_platform_aliases(monkeypatch):
    # A synthetic ticker not in the registry, so the hit can only come from the platform pull.
    monkeypatch.setattr(
        ai,
        "fetch_translation_aliases",
        lambda *a, **k: [
            {
                "ticker": "TESTX",
                "market": "US",
                "name_en": "Test X Corp",
                "name_zh_tw": "測試X",
                "aliases": ["TestXAlias", "TX Co"],
            }
        ],
    )
    index = ai.build_alias_index(InMemoryWikiRepository())

    hit = index.lookup("TestXAlias")
    assert hit is not None and hit.symbol == "TESTX"
    assert index.lookup("TX Co") is hit  # second alias → same entity
    assert index.lookup("Test X Corp") is hit  # name also indexed
    assert index.lookup("測試X") is hit  # zh name indexed


def test_build_alias_index_no_platform_when_disabled(monkeypatch):
    # Disabled pull (returns None) must not crash; index still builds from the registry.
    monkeypatch.setattr(ai, "fetch_translation_aliases", lambda *a, **k: None)
    index = ai.build_alias_index(InMemoryWikiRepository())
    assert index is not None
    assert index.lookup("TestXAlias") is None
