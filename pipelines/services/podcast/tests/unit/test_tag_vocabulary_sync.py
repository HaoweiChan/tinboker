"""Drift guard: the backend tag-vocabulary mirror must match the pipeline canonical.

Mirror of ``backend/tests/unit/test_tag_vocabulary_sync.py`` — lives here too so the
guard fires on the realistic drift path: a maintainer edits the pipeline vocabulary
(touching ``pipelines/**``, which triggers Pipelines CI) and forgets to re-sync the
backend mirror. Run ``python scripts/sync_tag_vocabulary.py`` to fix a failure.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[5]
CANONICAL = REPO_ROOT / "pipelines/services/podcast/src/podcast/content_builder/tag_vocabulary.json"
MIRROR = REPO_ROOT / "backend/src/data/tag_vocabulary.json"


def _strip_meta(d: dict) -> dict:
    return {k: v for k, v in d.items() if not k.startswith("_")}


def test_mirror_matches_canonical():
    if not MIRROR.exists():
        pytest.skip("backend/ tree not present (pipelines-only checkout)")
    canonical = json.loads(CANONICAL.read_text(encoding="utf-8"))
    mirror = _strip_meta(json.loads(MIRROR.read_text(encoding="utf-8")))
    assert mirror == canonical, (
        "backend/src/data/tag_vocabulary.json is out of sync with the pipeline canonical. "
        "Run: python scripts/sync_tag_vocabulary.py"
    )


def test_tag_display_loads_from_json():
    """``TAG_DISPLAY`` is sourced from the JSON, not a hardcoded dict."""
    from podcast.content_builder.tag_vocabulary import TAG_DISPLAY, display_for

    canonical = json.loads(CANONICAL.read_text(encoding="utf-8"))
    assert TAG_DISPLAY == canonical
    # normalize: PascalCase / snake_case / lowercased all resolve to the same label.
    assert display_for("SupplyChain") == display_for("supply_chain") == display_for("supplychain")
