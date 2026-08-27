"""Serve-time tag↔sector dedup in the episode transformer.

The pipeline dedupes the stored tags array at write time, but ``to_episode``
re-derives tags from inline ``#tag:`` prose links and unions them back in — and
every historical episode predates the write-time dedup. This mirrors the
pipeline-side rule (pipelines/.../nodes/tags_tickers.py::dedup_tags_against_sectors)
with the same test vectors: the four offenders actually observed on EP677's
served payload (Substrate, OSAT, SemiconductorIndex, SupplyChain).
"""

import pytest

from src.services.episode_transformer import (
    EpisodeTransformer,
    filter_tags_against_sectors,
)

# EP677-shaped fired sectors, as stored on the episode doc (display names are the
# LIVE registry values — note HBM 供應鏈 differs from the seed's display, which is
# exactly the rename case the doc-side display matching covers).
_EP677_FIRED = [
    {"exposure_id": "sector_pcb_substrate", "display_name": "PCB 載板"},
    {"exposure_id": "sector_ospat", "display_name": "封測代工"},
    {"exposure_id": "sector_semiconductor", "display_name": "半導體"},
    {"exposure_id": "sector_hbm", "display_name": "HBM 供應鏈"},
]


def test_all_four_ep677_offenders_are_filtered():
    tags = ["Substrate", "OSAT", "SemiconductorIndex", "SupplyChain", "Inflation", "TWStocks"]
    kept = filter_tags_against_sectors(tags, _EP677_FIRED)
    # Substrate: seed alias "substrate"; OSAT: seed alias "OSAT";
    # SemiconductorIndex: 半導體指數 contains fired 半導體;
    # SupplyChain: 供應鏈 contained in fired live display "HBM 供應鏈".
    assert kept == ["Inflation", "TWStocks"]


def test_tag_survives_when_its_sector_did_not_fire():
    kept = filter_tags_against_sectors(
        ["Substrate", "Inflation"],
        [{"exposure_id": "sector_hbm", "display_name": "HBM 供應鏈"}],
    )
    assert kept == ["Substrate", "Inflation"]


def test_noop_without_sectors_or_tags():
    assert filter_tags_against_sectors(["Substrate"], []) == ["Substrate"]
    assert filter_tags_against_sectors([], _EP677_FIRED) == []


def test_legacy_theme_prefixed_exposure_ids_still_match():
    kept = filter_tags_against_sectors(
        ["OSAT"], [{"exposure_id": "theme_ospat", "display_name": "封測代工"}]
    )
    assert kept == []


@pytest.mark.asyncio
async def test_to_episode_filters_prose_reintroduced_tags():
    """EP677 shape: stored tags already deduped, prose #tag: links re-introduce
    Substrate/OSAT — the served tags must exclude them; unrelated tags survive.
    The inline links themselves stay untouched in summary_content."""
    transformer = EpisodeTransformer(gcs_service=object())
    summary = "看好[基板](#tag:Substrate)與[封測](#tag:OSAT)，另關注[通膨](#tag:Inflation)。"
    raw = {
        "id": "Gooaye_501477cb2ee181fb",
        "podcast_name": "股癌 Gooaye",
        "created_time": 1,
        "summary_content": summary,
        "tags": ["Inflation", "TWStocks"],  # already deduped at write time
        "sector_exposures": _EP677_FIRED,
    }
    episode = await transformer.to_episode(raw, enrich_content=False)
    assert set(episode.tags) == {"Inflation", "TWStocks"}
    assert episode.summary_content == summary  # prose links never stripped


@pytest.mark.asyncio
async def test_to_episode_dedupes_prose_tag_casing():
    """EP691/EP687 shape: stored tags are lowercased, prose links are PascalCase.

    The union used to be case-sensitive, so the served payload carried both
    spellings (EP687 served 26 tags, 13 of them case dupes). The stored spelling
    wins; a tag that only exists in prose still surfaces.
    """
    transformer = EpisodeTransformer(gcs_service=object())
    episode = await transformer.to_episode(
        {
            "id": "Gooaye_95c6dff51109061e",
            "podcast_name": "Gooaye 股癌",
            "created_time": 1,
            "summary_content": "[生成式AI](#tag:GenerativeAI)、[EPS](#tag:EPS)",
            "tags": ["generativeai"],
        },
        enrich_content=False,
    )
    assert sorted(episode.tags) == ["EPS", "generativeai"]
