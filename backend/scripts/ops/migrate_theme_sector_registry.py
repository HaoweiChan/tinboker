#!/usr/bin/env python3
"""Migrate legacy ``theme_<id>`` sector rows in tag_registry to the unified ``sector_<id>``.

Sectors and curated themes now share ONE ``sector_`` exposure namespace (see
shared.sectors.normalize_exposure_id). The pipeline universe + episode data are
migrated by the sector backfill; this script fixes the platform Postgres
``tag_registry`` so the admin Sectors tab shows each exposure once, under ``sector_``.

For every ``kind='sector'`` row whose slug/exposure_id starts with ``theme_``:
  • if no ``sector_<id>`` row exists yet  → RENAME (slug + exposure_id), preserving
    the row's tier (admin hide/show curation) and visuals.
  • if a ``sector_<id>`` row already exists (the new sync created it) → MERGE: carry a
    'hidden' tier from the legacy row onto the survivor (so an admin hide isn't lost),
    then DELETE the legacy ``theme_`` row.

Idempotent. Dry-run by default — pass --commit to write.

Usage:
    python scripts/ops/migrate_theme_sector_registry.py            # preview
    python scripts/ops/migrate_theme_sector_registry.py --commit   # apply
"""

import argparse
import logging
import sys
from pathlib import Path

# scripts/ops/ -> backend/
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.database.postgres import get_session, init_engine
from src.database import models  # noqa: F401 - register models
from src.database.models import TagRegistry

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

_THEME = "theme_"
_SECTOR = "sector_"
TIER_HIDDEN = "hidden"


def _target_slug(slug: str) -> str:
    return _SECTOR + slug[len(_THEME):]


def migrate(commit: bool) -> int:
    db = next(get_session())
    try:
        legacy = (
            db.query(TagRegistry)
            .filter(TagRegistry.kind == "sector", TagRegistry.slug.like("theme_%"))
            .all()
        )
        if not legacy:
            logger.info("No legacy theme_ sector rows. Nothing to do.")
            return 0

        renamed = merged = 0
        for row in legacy:
            target = _target_slug(row.slug)
            survivor = (
                db.query(TagRegistry)
                .filter(TagRegistry.kind == "sector", TagRegistry.slug == target)
                .first()
            )
            if survivor is None:
                logger.info("RENAME  %s -> %s  (tier=%s)", row.slug, target, row.tier)
                if commit:
                    row.slug = target
                    row.exposure_id = target
                renamed += 1
            else:
                carry = row.tier == TIER_HIDDEN and survivor.tier != TIER_HIDDEN
                logger.info(
                    "MERGE   %s -> %s  (delete legacy%s)",
                    row.slug, target, "; carry hidden tier" if carry else "",
                )
                if commit:
                    if carry:
                        survivor.tier = TIER_HIDDEN
                    db.delete(row)
                merged += 1

        if commit:
            db.commit()
            logger.info("COMMITTED: %d renamed, %d merged/deleted.", renamed, merged)
        else:
            logger.info("DRY-RUN: %d would rename, %d would merge/delete. Pass --commit to apply.", renamed, merged)
        return renamed + merged
    finally:
        db.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--commit", action="store_true", help="apply changes (default: dry-run)")
    args = ap.parse_args()
    init_engine()
    migrate(commit=args.commit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
