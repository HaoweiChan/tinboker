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
CANONICAL = REPO_ROOT / "pipelines/libs/shared/src/shared/tag_vocabulary_seed_backup.py"
MIRROR = REPO_ROOT / "backend/src/data/tag_vocabulary_seed.py"


def test_mirror_matches_canonical():
    if not MIRROR.exists():
        pytest.skip("backend/ tree not present (pipelines-only checkout)")
    # Import values dynamically to compare
    import sys
    sys.path.insert(0, str(REPO_ROOT / "backend/src"))
    from data.tag_vocabulary_seed import TAG_VOCABULARY_SEED as mirror
    from shared.tag_vocabulary_seed_backup import TAG_VOCABULARY_SEED as canonical
    assert mirror == canonical, (
        "backend/src/data/tag_vocabulary_seed.py is out of sync with the pipeline backup. "
        "Run: python scripts/sync_tag_vocabulary.py"
    )


def test_tag_display_loads_from_json():
    """``TAG_DISPLAY`` matches the canonical seed backup."""
    from shared.tag_vocabulary_seed_backup import TAG_VOCABULARY_SEED
    from src.podcast.content_builder.tag_vocabulary import TAG_DISPLAY, display_for

    assert TAG_DISPLAY == TAG_VOCABULARY_SEED
    # normalize: PascalCase / snake_case / lowercased all resolve to the same label.
    assert display_for("SupplyChain") == display_for("supply_chain") == display_for("supplychain")
