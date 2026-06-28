#!/usr/bin/env python3
"""Firestore migration script to normalize theme/sector metadata.

This script performs the following operations:
1. For every document in the 'episodes' collection:
   - Replaces 'theme_xxx' with 'sector_xxx' in sector_exposures and sector_exposure_ids.
   - Renames exposure_type 'sector' to 'industry' in sector_exposures.
   - Deletes sector_id and theme_id fields from elements within the sector_exposures array.
   - Deletes root-level fields 'sector_ids' and 'theme_ids'.
2. For the 'tags' collection (inverted index):
   - Merges legacy 'theme_xxx' (and normalized 'themeaiserver' etc.) tags' 'episodes' subcollections
     into their new normalized 'sector_xxx' (e.g. 'sectoraiserver') tags.
   - Deletes the legacy parent tag documents.

Run in dry-run mode first:
    uv run --package tinboker-podcast python services/podcast/scripts/migrate_theme_and_sector_metadata.py

Commit changes:
    uv run --package tinboker-podcast python services/podcast/scripts/migrate_theme_and_sector_metadata.py --commit
"""

import argparse
import json
import sys
from pathlib import Path

_SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_SERVICE_ROOT))

from google.cloud import firestore  # noqa: E402
from src.podcast.content_builder.tag_vocabulary import normalize_tag_slug  # noqa: E402

_PROJECT = "gen-lang-client-0901363254"
_DB = "graphfolio-db"


def _move_episodes(db, tags, src_id: str, dst_id: str) -> int:
    """Copy ``tags/{src}/episodes/*`` into ``tags/{dst}/episodes`` and delete the source."""
    dst_eps = tags.document(dst_id).collection("episodes")
    src_eps = tags.document(src_id).collection("episodes")
    moved = 0
    batch = db.batch()
    n = 0
    for ep in src_eps.stream():
        batch.set(dst_eps.document(ep.id), ep.to_dict() or {}, merge=True)
        batch.delete(ep.reference)
        n += 2
        moved += 1
        if n >= 400:
            batch.commit()
            batch = db.batch()
            n = 0
    if n:
        batch.commit()
    return moved


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--commit", action="store_true", help="apply changes to Firestore (default: dry-run)")
    args = ap.parse_args()

    # Load curated themes to get theme IDs for tag migration
    shared_data = Path(__file__).resolve().parents[3] / "libs" / "shared" / "src" / "shared" / "data"
    curated_themes_path = shared_data / "curated_themes.json"
    if not curated_themes_path.exists():
        print(f"Error: Curated themes not found at {curated_themes_path}")
        return 1

    with open(curated_themes_path, "r", encoding="utf-8") as f:
        themes_data = json.load(f)
    theme_ids = [t["theme_id"] for t in themes_data.get("themes", [])]
    print(f"Loaded {len(theme_ids)} curated theme IDs from universe data.")

    # Load universe exposures to build visuals map
    universe_path = shared_data / "sector_and_theme_universe.json"
    if not universe_path.exists():
        print(f"Error: Universe JSON not found at {universe_path}")
        return 1
    with open(universe_path, "r", encoding="utf-8") as f:
        universe_data = json.load(f)
    universe_map = {}
    for exp in universe_data.get("exposures", []):
        eid = exp.get("exposure_id")
        if eid:
            universe_map[eid] = {
                "display_name": exp.get("display_name"),
                "exposure_type": exp.get("exposure_type"),
                "icon_id": exp.get("icon_id"),
                "color_hex": exp.get("color_hex"),
            }
    print(f"Loaded {len(universe_map)} exposures mapping from universe JSON.")

    db = firestore.Client(project=_PROJECT, database=_DB)

    # 1. Migrate episodes collection
    print("Scanning episodes collection...")
    episodes_ref = db.collection("episodes")
    modified_episodes = 0
    batch = db.batch()
    n = 0

    for doc in episodes_ref.stream():
        doc_dict = doc.to_dict() or {}
        needs_update = False
        update_payload = {}

        # Check for root fields sector_ids and theme_ids to delete
        if "sector_ids" in doc_dict:
            update_payload["sector_ids"] = firestore.DELETE_FIELD
            needs_update = True
        if "theme_ids" in doc_dict:
            update_payload["theme_ids"] = firestore.DELETE_FIELD
            needs_update = True

        # Process sector_exposure_ids
        exposure_ids = doc_dict.get("sector_exposure_ids") or []
        new_exposure_ids = []
        for eid in exposure_ids:
            # Normalize theme_ -> sector_ prefix
            normalized_eid = "sector_" + eid[len("theme_"):] if eid.startswith("theme_") else eid
            # Filter out cryptocurrency
            if normalized_eid in ("sector_cryptocurrency", "theme_cryptocurrency"):
                needs_update = True
                continue
            if normalized_eid != eid:
                new_exposure_ids.append(normalized_eid)
                needs_update = True
            else:
                new_exposure_ids.append(eid)

        if needs_update or new_exposure_ids != exposure_ids:
            update_payload["sector_exposure_ids"] = new_exposure_ids
            needs_update = True

        # Process sector_exposures list of objects
        exposures = doc_dict.get("sector_exposures") or []
        new_exposures = []
        for exp in exposures:
            exp_needs_update = False
            new_exp = dict(exp)

            # Update exposure_id prefix
            eid = exp.get("exposure_id") or ""
            if eid.startswith("theme_"):
                eid = "sector_" + eid[len("theme_"):]
                new_exp["exposure_id"] = eid
                exp_needs_update = True

            # Filter out cryptocurrency
            if eid in ("sector_cryptocurrency", "theme_cryptocurrency"):
                needs_update = True
                continue

            # Update exposure_type: sector -> industry
            etype = exp.get("exposure_type") or ""
            if etype == "sector":
                new_exp["exposure_type"] = "industry"
                exp_needs_update = True

            # Align metadata (display_name, exposure_type, icon_id, color_hex) from universe mapping
            meta = universe_map.get(eid)
            if meta:
                if new_exp.get("display_name") != meta.get("display_name"):
                    new_exp["display_name"] = meta.get("display_name")
                    exp_needs_update = True
                if new_exp.get("exposure_type") != meta.get("exposure_type"):
                    new_exp["exposure_type"] = meta.get("exposure_type")
                    exp_needs_update = True
                if new_exp.get("icon_id") != meta.get("icon_id"):
                    new_exp["icon_id"] = meta.get("icon_id")
                    exp_needs_update = True
                if new_exp.get("color_hex") != meta.get("color_hex"):
                    new_exp["color_hex"] = meta.get("color_hex")
                    exp_needs_update = True

            # Delete inner sector_id / theme_id
            if "sector_id" in new_exp:
                new_exp.pop("sector_id")
                exp_needs_update = True
            if "theme_id" in new_exp:
                new_exp.pop("theme_id")
                exp_needs_update = True

            new_exposures.append(new_exp)
            if exp_needs_update:
                needs_update = True

        if needs_update or new_exposures != exposures:
            update_payload["sector_exposures"] = new_exposures
            needs_update = True

        if needs_update:
            modified_episodes += 1
            if args.commit:
                batch.update(doc.reference, update_payload)
                n += 1
                if n >= 400:
                    batch.commit()
                    batch = db.batch()
                    n = 0
            else:
                # Dry run print of first few modifications
                if modified_episodes <= 3:
                    print(f"[DRY-RUN] Will update episode {doc.id}: {update_payload}")

    if args.commit and n > 0:
        batch.commit()

    print(f"Episodes scan completed. Total episodes to modify: {modified_episodes}")

    # 2. Migrate tags collection
    print("\nScanning tags collection...")
    tags_ref = db.collection("tags")
    existing_tags = {d.id for d in tags_ref.list_documents()}

    moved_tags_count = 0
    moved_episodes_count = 0

    # Build the map of legacy raw and normalized tag IDs to new destination tag IDs
    migration_map = {}
    for tid in theme_ids:
        # Legacy options
        legacy_raw = f"theme_{tid}"
        legacy_norm = normalize_tag_slug(legacy_raw)

        # Target options
        target_raw = f"sector_{tid}"
        target_norm = normalize_tag_slug(target_raw)

        if legacy_raw in existing_tags:
            migration_map[legacy_raw] = target_norm
        if legacy_norm in existing_tags:
            migration_map[legacy_norm] = target_norm

    for src, dst in migration_map.items():
        if src == dst:
            continue
        moved_tags_count += 1
        if args.commit:
            # Ensure target parent doc exists
            tags_ref.document(dst).set({}, merge=True)
            moved_eps = _move_episodes(db, tags_ref, src, dst)
            tags_ref.document(src).delete()
            moved_episodes_count += moved_eps
            print(f"Migrated tag '{src}' -> '{dst}' ({moved_eps} episodes moved)")
        else:
            print(f"[DRY-RUN] Will migrate tag '{src}' -> '{dst}'")

    # Delete cryptocurrency tags from tags collection if present
    deleted_crypto_count = 0
    for crypto_tag in ("cryptocurrency", "sector_cryptocurrency", "theme_cryptocurrency"):
        norm_crypto = normalize_tag_slug(crypto_tag)
        for t in sorted({crypto_tag, norm_crypto}):
            if t in existing_tags:
                deleted_crypto_count += 1
                if args.commit:
                    eps_ref = db.collection("tags").document(t).collection("episodes")
                    for ep_doc in eps_ref.stream():
                        ep_doc.reference.delete()
                    db.collection("tags").document(t).delete()
                    print(f"Deleted tag '{t}' from Firestore tags collection.")
                else:
                    print(f"[DRY-RUN] Will delete tag '{t}' from Firestore tags collection.")

    print(f"\nTags migration completed.")
    print(f"Tags to migrate: {moved_tags_count}")
    if args.commit:
        print(f"Total episodes referenced across migrated tags: {moved_episodes_count}")

    if not args.commit:
        print("\n*** DRY-RUN ONLY. No database changes were made. Pass --commit to apply. ***")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
