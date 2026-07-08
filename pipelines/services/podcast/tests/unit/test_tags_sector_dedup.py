"""Tag↔sector dedup at output assembly (P2 systemic fix).

Vocabulary pruning removed the definite collisions, but borderline tags kept in
the vocabulary (Substrate, OSAT, SemiconductorIndex, SupplyChain — the exact set
EP677's regen still emitted) become redundant when the matching sector actually
fired on the episode. ``dedup_tags_against_sectors`` drops them at the two
assembly points (run_pipeline + regen _assemble). The universe lookup is mocked
so the test doesn't depend on the live taxonomy.
"""

from __future__ import annotations

import src.podcast.content_builder.nodes.tags_tickers as tt

_UNIVERSE = {
    "max_tickers": 10,
    "exposures": [
        {
            "exposure_id": "sector_pcb_substrate",
            "display_name": "PCB 載板",
            "aliases": ["PCB 載板", "ABF", "IC 載板", "載板", "substrate"],
            "members": [],
        },
        {
            "exposure_id": "sector_ospat",
            "display_name": "封測代工",
            "aliases": ["封測代工", "封測", "封裝測試", "OSAT"],
            "members": [],
        },
        {
            "exposure_id": "sector_semiconductor",
            "display_name": "半導體",
            "aliases": ["半導體", "晶片", "晶圓", "semiconductor"],
            "members": [],
        },
        {
            "exposure_id": "sector_hbm",
            "display_name": "HBM 供應鏈",
            "aliases": ["HBM 高頻寬記憶體", "HBM", "高頻寬記憶體"],
            "members": [],
        },
    ],
}


def _fired(*ids):
    by_id = {e["exposure_id"]: e for e in _UNIVERSE["exposures"]}
    return [{"exposure_id": i, "display_name": by_id[i]["display_name"]} for i in ids]


def test_colliding_tags_dropped_when_sector_fired(monkeypatch, caplog):
    monkeypatch.setattr("shared.sectors.load_universe", lambda **kw: _UNIVERSE)
    tags = ["substrate", "osat", "semiconductorindex", "supplychain", "inflation", "twstocks"]
    fired = _fired("sector_pcb_substrate", "sector_ospat", "sector_semiconductor", "sector_hbm")

    with caplog.at_level("INFO"):
        kept = tt.dedup_tags_against_sectors(tags, fired)

    # substrate: slug == sector alias; osat: slug == alias (case-insensitive);
    # semiconductorindex: display 半導體指數 contains fired alias 半導體;
    # supplychain: display 供應鏈 contained in fired display HBM 供應鏈.
    assert kept == ["inflation", "twstocks"]
    assert "dropped 4 tag(s)" in caplog.text


def test_tags_kept_when_sector_not_fired(monkeypatch):
    monkeypatch.setattr("shared.sectors.load_universe", lambda **kw: _UNIVERSE)
    tags = ["substrate", "inflation"]
    # Only the semiconductor sector fired — substrate's sector did not.
    kept = tt.dedup_tags_against_sectors(tags, _fired("sector_hbm"))
    assert kept == ["substrate", "inflation"]


def test_no_sectors_is_a_noop():
    assert tt.dedup_tags_against_sectors(["substrate"], []) == ["substrate"]
    assert tt.dedup_tags_against_sectors([], [{"exposure_id": "x"}]) == []
