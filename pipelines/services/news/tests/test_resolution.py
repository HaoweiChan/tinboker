"""Unit tests for steps 4-6: alias index, dict_prepass, llm_enrich, resolve."""

from __future__ import annotations

import pytest
from news.alias_index import build_alias_index
from news.pipeline.article import Article, Paragraph
from news.pipeline.steps.dict_prepass import dict_prepass
from news.pipeline.steps.llm_enrich import llm_enrich
from news.pipeline.steps.resolve import resolve
from shared.wiki_builder import InMemoryWikiRepository, render_entity_page


# --- alias index ---------------------------------------------------------
def test_alias_index_collapses_zh_en_symbol_to_one_slug():
    idx = build_alias_index(InMemoryWikiRepository())
    by_zh = idx.lookup("台積電")
    by_en = idx.lookup("TSMC")
    by_sym = idx.lookup("2330")
    assert by_zh is not None and by_en is not None and by_sym is not None
    assert by_zh.slug == by_en.slug == by_sym.slug


def test_alias_index_includes_entity_page_aliases():
    repo = InMemoryWikiRepository()
    repo.upsert_page(
        render_entity_page(
            entity_id="acme",
            name="Acme Corp",
            entity_type="company",
            tickers=[],
            aliases=["Acme", "ACME Holdings"],
        )
    )
    idx = build_alias_index(repo)
    hit = idx.lookup("ACME Holdings")
    assert hit is not None and hit.slug == "acme"


# --- dict_prepass --------------------------------------------------------
def test_dict_prepass_matches_registry_entities():
    idx = build_alias_index(InMemoryWikiRepository())
    art = Article(url="u", title="TSMC update", source="S")
    art.paragraphs = [
        Paragraph(0, "h0", "TSMC reported strong demand and 輝達 chip orders rose sharply.")
    ]
    dict_prepass(art, idx)
    assert idx.lookup("TSMC").slug in art.candidate_entities
    assert idx.lookup("輝達").slug in art.candidate_entities


# --- llm_enrich ----------------------------------------------------------
def test_llm_enrich_enforces_event_type_vocab_and_citation():
    idx = build_alias_index(InMemoryWikiRepository())
    art = Article(url="https://ex.com/a", title="T", source="S", published="2026-05-20")
    art.paragraphs = [Paragraph(0, "hash0", "TSMC announced a merger with a smaller rival.")]

    def fake_llm(system: str, user: str) -> dict:
        return {
            "summary": "TSMC merger news.",
            "tags": ["semiconductors"],
            "entities": [],
            "claims": [
                {
                    "subject": "TSMC",
                    "predicate": "agreed to merge",
                    "object": "with a rival",
                    "event_type": "Merger & Acquisition",
                    "sentiment": "neut",
                    "confidence": 0.7,
                    "paragraph_index": 0,
                    "quote": "TSMC announced a merger with a smaller rival.",
                }
            ],
        }

    llm_enrich(art, idx, llm=fake_llm)
    assert len(art.claims) == 1
    claim = art.claims[0]
    assert claim["event_type"] == "m_and_a"  # controlled vocab enforced
    assert claim["paragraph_hash"] == "hash0"  # citation attached from paragraph_index
    assert claim["source_url"] == "https://ex.com/a"
    assert claim["claim_date"] == "2026-05-20"


# --- resolve -------------------------------------------------------------
def test_resolve_collapses_zh_and_en_mentions_to_one_entity():
    idx = build_alias_index(InMemoryWikiRepository())
    art = Article(url="u", title="t", source="S")
    art.claims = [
        {"subject": "台積電", "predicate": "raised guidance", "object": "to $44B"},
        {"subject": "TSMC", "predicate": "expanded", "object": "Arizona fab"},
    ]
    resolve(art, idx, llm=lambda s, u: {"resolutions": []})
    assert len({c["subject"] for c in art.claims}) == 1
    assert len(art.entities) == 1


def test_resolve_l3_creates_a_new_entity_for_residuals():
    idx = build_alias_index(InMemoryWikiRepository())
    art = Article(url="u", title="t", source="S")
    art.claims = [{"subject": "Globex Inc", "predicate": "launched", "object": "a product"}]

    def fake_disambig(system: str, user: str) -> dict:
        return {
            "resolutions": [
                {"mention": "Globex Inc", "slug": "NEW", "name": "Globex Inc", "type": "company"}
            ]
        }

    resolve(art, idx, llm=fake_disambig)
    assert len(art.claims) == 1
    assert "globex-inc" in {e["slug"] for e in art.entities}


def test_resolve_l3_records_new_alias_for_known_entity():
    idx = build_alias_index(InMemoryWikiRepository())
    tsmc_slug = idx.lookup("TSMC").slug
    art = Article(url="u", title="t", source="S")
    art.claims = [{"subject": "Taiwan Semi", "predicate": "p", "object": "o"}]

    resolve(
        art,
        idx,
        llm=lambda s, u: {"resolutions": [{"mention": "Taiwan Semi", "slug": tsmc_slug}]},
    )
    assert art.claims[0]["subject"] == tsmc_slug
    entity = next(e for e in art.entities if e["slug"] == tsmc_slug)
    assert "Taiwan Semi" in entity.get("aliases", [])


def test_resolve_drops_claims_with_unresolvable_subject():
    idx = build_alias_index(InMemoryWikiRepository())
    art = Article(url="u", title="t", source="S")
    art.claims = [{"subject": "Some Vague Thing", "predicate": "p", "object": "o"}]
    resolve(art, idx, llm=lambda s, u: {"resolutions": [{"mention": "Some Vague Thing", "slug": "SKIP"}]})
    assert art.claims == []


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
