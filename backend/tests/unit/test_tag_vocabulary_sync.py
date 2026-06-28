"""Drift guard: the backend tag-vocabulary mirror must match the pipeline canonical.

The slug→zh-TW label catalogue has ONE source of truth — the pipeline's
``tag_vocabulary.json`` — mirrored into the backend by ``scripts/sync_tag_vocabulary.py``.
These tests fail if the mirror drifts, which is exactly the bug PRs #161/#162 fixed by
hand (new pipeline tags rendering in English on the website because the backend copy
went stale). Run ``python scripts/sync_tag_vocabulary.py`` to fix a failure.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
CANONICAL = REPO_ROOT / "pipelines/libs/shared/src/shared/tag_vocabulary_seed_backup.py"
MIRROR = REPO_ROOT / "backend/src/data/tag_vocabulary_seed.py"


def test_mirror_matches_canonical():
    """Backend mirror == pipeline canonical (the single-source-of-truth assertion)."""
    if not CANONICAL.exists():
        pytest.skip("pipelines/ tree not present (backend-only checkout)")
    # Import values dynamically to compare
    import sys
    sys.path.insert(0, str(CANONICAL.parent))
    from tag_vocabulary_seed_backup import TAG_VOCABULARY_SEED as canonical
    from src.data.tag_vocabulary_seed import TAG_VOCABULARY_SEED as mirror
    assert mirror == canonical, (
        "backend/src/data/tag_vocabulary_seed.py is out of sync with the pipeline backup. "
        "Run: python scripts/sync_tag_vocabulary.py"
    )


def test_registry_loads_full_catalogue():
    """The backend registry exposes every canonical label, keyed by normalized slug."""
    from src.tag_registry import _CANONICAL_DISPLAY, normalize_tag_slug
    from src.data.tag_vocabulary_seed import TAG_VOCABULARY_SEED

    expected = {normalize_tag_slug(slug): zh for slug, zh in TAG_VOCABULARY_SEED.items()}
    assert _CANONICAL_DISPLAY == expected


class _FakeDb:
    """Minimal stand-in for the SQLAlchemy session ``registry_snapshot`` uses."""

    def __init__(self, rows):
        self._rows = rows

    def query(self, *_a, **_k):
        rows = self._rows
        return SimpleNamespace(all=lambda: rows)


def test_registry_snapshot_translates_episode_tag_slugs():
    """The production bug: PascalCase episode tags rendered in English.

    Every tag from the screenshotted episodes resolves to its curated zh-TW label
    via the canonical catalogue, regardless of the DB seed's slug spelling.
    """
    from src.tag_registry import normalize_tag_slug, registry_snapshot

    snap = {normalize_tag_slug(e["slug"]): e["display_zh"] for e in registry_snapshot(_FakeDb([]))}
    expected = {
        "DataCenter": "資料中心", "Finance": "金融", "TWStocks": "台股",
        "Memory": "記憶體", "Inflation": "通膨", "FedRate": "聯準會利率",
        "Macroeconomy": "總體經濟",
    }
    for slug, zh in expected.items():
        assert snap.get(normalize_tag_slug(slug)) == zh, f"{slug} did not resolve to {zh}"


def test_registry_snapshot_placeholder_does_not_mask_canonical():
    """An auto-registered English placeholder must not override the canonical label."""
    from src.tag_registry import normalize_tag_slug, registry_snapshot

    rows = [SimpleNamespace(slug="DataCenter", display_zh="DataCenter", tier="hidden")]
    snap = {normalize_tag_slug(e["slug"]): e for e in registry_snapshot(_FakeDb(rows))}
    assert snap[normalize_tag_slug("DataCenter")]["display_zh"] == "資料中心"


def test_registry_snapshot_dedupes_canonical_and_db_by_normalized_slug():
    """Canonical ``SupplyChain`` and DB ``supply_chain`` collapse to one entry."""
    from src.tag_registry import normalize_tag_slug, registry_snapshot

    rows = [SimpleNamespace(slug="supply_chain", display_zh="供應鏈", tier="trending")]
    snap = registry_snapshot(_FakeDb(rows))
    norm = normalize_tag_slug("SupplyChain")
    matches = [e for e in snap if normalize_tag_slug(e["slug"]) == norm]
    assert len(matches) == 1
    assert matches[0]["display_zh"] == "供應鏈"
    assert matches[0]["tier"] == "trending"  # DB tier wins


def test_registry_snapshot_canonical_label_wins_over_stale_db_label():
    """A vocab edit (IPO→IPO) must override a row auto-registered with the old label."""
    from src.tag_registry import normalize_tag_slug, registry_snapshot

    rows = [SimpleNamespace(slug="IPO", display_zh="首次公開發行", tier="trending")]
    snap = {normalize_tag_slug(e["slug"]): e for e in registry_snapshot(_FakeDb(rows))}
    assert snap[normalize_tag_slug("IPO")]["display_zh"] == "IPO"


class _FilterDb:
    """Stand-in for the session ``hidden_tag_slugs`` uses (``.query().filter().all()``)."""

    def __init__(self, slugs):
        self._slugs = slugs

    def query(self, *_a, **_k):
        rows = [(s,) for s in self._slugs]
        return SimpleNamespace(filter=lambda *a, **k: SimpleNamespace(all=lambda: rows))


def test_hidden_offvocab_slugs_excludes_canonical():
    """Off-vocab hidden junk is returned; in-vocab tags stay on episode pages."""
    from src.tag_registry import hidden_offvocab_slugs, normalize_tag_slug

    out = hidden_offvocab_slugs(_FilterDb(["TaiwanStocks", "Memory"]))
    assert normalize_tag_slug("TaiwanStocks") in out  # off-vocab junk → filtered
    assert normalize_tag_slug("Memory") not in out    # canonical topic → kept


def test_normalize_has_no_conflicting_collisions():
    """No two source slugs normalize to the same key with DIFFERENT labels.

    Guarantees the end-to-end ``normalize_tag_slug`` collapse (PascalCase /
    snake_case / lowercased all → one key) is lossless, so the frontend can key its
    label map by the normalized slug safely.
    """
    from src.tag_registry import _SEED, normalize_tag_slug
    from src.data.tag_vocabulary_seed import TAG_VOCABULARY_SEED

    by_norm: dict[str, str] = {}
    # DB seed first, canonical wins on overlap (mirrors registry_snapshot precedence).
    for slug, zh, _tier in _SEED:
        by_norm.setdefault(normalize_tag_slug(slug), zh)
    conflicts = {}
    for slug, zh in TAG_VOCABULARY_SEED.items():
        norm = normalize_tag_slug(slug)
        if norm in by_norm and by_norm[norm] != zh:
            conflicts[norm] = (by_norm[norm], zh)
    assert not conflicts, f"normalized-slug collisions with different labels: {conflicts}"
