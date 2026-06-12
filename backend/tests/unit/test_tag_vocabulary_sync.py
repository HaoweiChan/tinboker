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

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
CANONICAL = REPO_ROOT / "pipelines/services/podcast/src/podcast/content_builder/tag_vocabulary.json"
MIRROR = REPO_ROOT / "backend/src/data/tag_vocabulary.json"


def _strip_meta(d: dict) -> dict:
    """Drop the mirror's ``_comment`` provenance key (JSON has no comments)."""
    return {k: v for k, v in d.items() if not k.startswith("_")}


def test_mirror_matches_canonical():
    """Backend mirror == pipeline canonical (the single-source-of-truth assertion)."""
    if not CANONICAL.exists():
        pytest.skip("pipelines/ tree not present (backend-only checkout)")
    canonical = json.loads(CANONICAL.read_text(encoding="utf-8"))
    mirror = _strip_meta(json.loads(MIRROR.read_text(encoding="utf-8")))
    assert mirror == canonical, (
        "backend/src/data/tag_vocabulary.json is out of sync with the pipeline canonical. "
        "Run: python scripts/sync_tag_vocabulary.py"
    )


def test_registry_loads_full_catalogue():
    """The backend registry exposes every canonical label, keyed by normalized slug."""
    from src.tag_registry import _CANONICAL_DISPLAY, normalize_tag_slug

    mirror = _strip_meta(json.loads(MIRROR.read_text(encoding="utf-8")))
    expected = {normalize_tag_slug(slug): zh for slug, zh in mirror.items()}
    assert _CANONICAL_DISPLAY == expected


def test_normalize_has_no_conflicting_collisions():
    """No two source slugs normalize to the same key with DIFFERENT labels.

    Guarantees the end-to-end ``normalize_tag_slug`` collapse (PascalCase /
    snake_case / lowercased all → one key) is lossless, so the frontend can key its
    label map by the normalized slug safely.
    """
    from src.tag_registry import _SEED, normalize_tag_slug

    mirror = _strip_meta(json.loads(MIRROR.read_text(encoding="utf-8")))
    by_norm: dict[str, str] = {}
    # DB seed first, canonical wins on overlap (mirrors registry_snapshot precedence).
    for slug, zh, _tier in _SEED:
        by_norm.setdefault(normalize_tag_slug(slug), zh)
    conflicts = {}
    for slug, zh in mirror.items():
        norm = normalize_tag_slug(slug)
        if norm in by_norm and by_norm[norm] != zh:
            conflicts[norm] = (by_norm[norm], zh)
    assert not conflicts, f"normalized-slug collisions with different labels: {conflicts}"
