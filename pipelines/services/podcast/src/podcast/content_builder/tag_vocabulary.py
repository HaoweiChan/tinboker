"""Canonical tag vocabulary: ASCII slug (the clustering join key) → zh-TW display.

**Single source of truth — as actually loaded at runtime.** The slug→zh-TW
catalogue lives in ``pipelines/libs/shared/src/shared/tag_vocabulary_seed_backup.py``
(``TAG_VOCABULARY_SEED``), imported below. (The docstring here used to point at a
sibling ``tag_vocabulary.json`` data file and a ``scripts/sync_tag_vocabulary.py``
JSON-mirroring script — that JSON file does not exist on this branch; ignore any
reference to it. The real drift guard is
``pipelines/services/podcast/tests/unit/test_tag_vocabulary_sync.py`` /
``backend/tests/unit/test_tag_vocabulary_sync.py``, which fail if
``tag_vocabulary_seed_backup.py`` and its backend mirror
``backend/src/data/tag_vocabulary_seed.py`` disagree — edit BOTH files together.)

**Extraction-side vocabulary.** Injected into the writer prompt so the LLM maps
concepts to KNOWN slugs instead of inventing per-episode phrasings. Extraction
lowercases slugs (``#tag:SupplyChain`` → ``supplychain``); lookups go through
``normalize_tag_slug`` so case AND separators (``Supply_Chain``/``SupplyChain``/
``supplychain``) all reconcile to one key.

**Adding a tag:** edit ``tag_vocabulary_seed_backup.py`` AND
``backend/src/data/tag_vocabulary_seed.py`` together (same dict, kept manually in
sync — the drift test above fails CI if they diverge), so the website never again
renders a new tag in English because someone forgot to sync the backend.

The **display-side gate** (which extracted tags appear in trending vs. hidden)
lives in ``backend/src/tag_registry.py`` (the DB-backed ``tag_registry`` table,
managed via the admin UI at ``/admin/tags``). That is a separate concern from this
label catalogue.

A slug not listed here still works (it just has no curated zh-TW display yet) —
prefer adding it to the JSON over inventing variants. Free-text Chinese tags
fragment clustering (美股 vs 美國股市 vs 美股大盤, 半導體 vs 晶片, …); a controlled
slug vocabulary avoids that.
"""

from __future__ import annotations

import re

from shared.tag_vocabulary_seed_backup import TAG_VOCABULARY_SEED as TAG_DISPLAY


def normalize_tag_slug(slug: str) -> str:
    """Canonical lookup key for a tag slug.

    Lowercases and strips every non-alphanumeric char so the three conventions in
    the system reconcile to one key:
        ``SupplyChain`` (vocabulary) / ``supply_chain`` (legacy DB slug) /
        ``supplychain`` (lowercased episode tag)  → ``supplychain``.

    The SAME function must be applied at extraction, registry lookup, and the
    frontend (see ``frontend/src/hooks/useTagLabels.ts``). Keep the three
    implementations in sync.
    """
    s = re.sub(r"[^a-z0-9]", "", (slug or "").lower())
    # Merge known duplicates/aliases to avoid redundancies
    aliases = {
        "datacenters": "datacenter",
        "earningsreport": "earnings",
        "electricvehicles": "ev",
        "electric_vehicles": "ev",
        "lowearthorbitsatellite": "leosatellite",
        "mergersandacquisitions": "mergersacquisitions",
    }
    return aliases.get(s, s)


# Normalized-slug -> display, for case/separator-insensitive lookup against extracted tags.
_DISPLAY_BY_NORM = {normalize_tag_slug(slug): zh for slug, zh in TAG_DISPLAY.items()}
_CANONICAL_BY_NORM = {normalize_tag_slug(slug): normalize_tag_slug(slug) for slug in TAG_DISPLAY}


def canonical_tag_slug(slug: str) -> str | None:
    """Canonical stored episode tag for a slug, or ``None`` when not in the vocabulary.

    Episode docs store normalized ASCII tags (for stable joins/indexes), while display
    labels come from this vocabulary through the platform registry. Returning ``None``
    for unknown slugs makes the prompt vocabulary enforceable instead of advisory:
    a tag cannot be persisted until it has a curated zh-TW label here.
    """
    return _CANONICAL_BY_NORM.get(normalize_tag_slug(slug))


def display_for(slug: str) -> str:
    """zh-TW display for a (possibly lowercased) tag slug; the slug itself if unknown."""
    return _DISPLAY_BY_NORM.get(normalize_tag_slug(slug), slug)


def vocabulary_prompt_block() -> str:
    """Render the vocabulary as ``Slug = 顯示名`` lines for the writer prompt."""
    return "\n".join(f"  - {slug} = {zh}" for slug, zh in TAG_DISPLAY.items())
