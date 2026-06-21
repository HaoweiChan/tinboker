"""Centralized tag registry — DB-backed with in-code seed data.

On first boot (empty table), the seed data below is inserted so the system
works out of the box. After that, all management is via the admin UI
(``/admin/tags``) which writes to the ``tag_registry`` Postgres table.

Tiers
─────
  trending → shown in the topics-cloud page + trending API
  hidden   → not shown in trending (auto-discovered tags default here)
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from src.database.models import TagRegistry

logger = logging.getLogger(__name__)

TIER_TRENDING = "trending"
TIER_HIDDEN = "hidden"
VALID_TIERS = {TIER_TRENDING, TIER_HIDDEN}

KIND_TAG = "tag"
KIND_SECTOR = "sector"
VALID_KINDS = {KIND_TAG, KIND_SECTOR}


# ── Seed data (inserted once when table is empty) ───────────────────
_SEED: list[tuple[str, str, str]] = [
    ("advanced_packaging", "先進封裝", TIER_TRENDING),
    ("ai", "AI", TIER_TRENDING),
    ("ai_chip", "AI 晶片", TIER_TRENDING),
    ("bitcoin", "比特幣", TIER_TRENDING),
    ("capital_expenditure", "資本支出", TIER_TRENDING),
    ("centralbanks", "央行", TIER_TRENDING),
    ("cryptocurrency", "加密貨幣", TIER_TRENDING),
    ("datacenters", "資料中心", TIER_TRENDING),
    ("demographics", "人口趨勢", TIER_TRENDING),
    ("digitalassets", "數位資產", TIER_TRENDING),
    ("earningsreport", "財報", TIER_TRENDING),
    ("electric_vehicles", "電動車", TIER_TRENDING),
    ("electricvehicles", "電動車", TIER_TRENDING),
    ("etf", "ETF", TIER_HIDDEN),
    ("ev", "電動車", TIER_TRENDING),
    ("federalreserve", "聯準會", TIER_TRENDING),
    ("financialregulation", "金融監管", TIER_TRENDING),
    ("fiscalpolicy", "財政政策", TIER_TRENDING),
    ("fixedincome", "固定收益", TIER_TRENDING),
    ("interestrates", "利率", TIER_TRENDING),
    ("interestratepolicy", "利率政策", TIER_TRENDING),
    ("japanmarket", "日本市場", TIER_TRENDING),
    ("labormarket", "就業市場", TIER_TRENDING),
    ("low_earth_orbit_satellite", "低軌衛星", TIER_TRENDING),
    ("marketnarratives", "市場敘事", TIER_TRENDING),
    ("media_industry", "媒體產業", TIER_TRENDING),
    ("mergers_and_acquisitions", "併購", TIER_TRENDING),
    ("monetarypolicy", "貨幣政策", TIER_TRENDING),
    ("powersupply", "電力供應", TIER_TRENDING),
    ("privatemarkets", "私募市場", TIER_TRENDING),
    ("semiconductor", "半導體", TIER_TRENDING),
    ("streaming_services", "串流服務", TIER_TRENDING),
    ("supply_chain", "供應鏈", TIER_TRENDING),
    ("taiwaneconomy", "台灣經濟", TIER_HIDDEN),
    ("trade_war", "貿易戰", TIER_TRENDING),
    ("us_stocks", "美股", TIER_TRENDING),
    ("useconomy", "美國經濟", TIER_TRENDING),
    ("usstockmarket", "美股市場", TIER_TRENDING),
    ("ustreasuries", "美債", TIER_TRENDING),
    ("valuation", "估值", TIER_HIDDEN),
]


# ── Canonical extraction vocabulary (label catalogue) ────────────────
# The slug→zh-TW label catalogue has a SINGLE source of truth: the pipeline's
# tag_vocabulary.json. The backend can't import the pipeline package (separate
# Docker image / build context), so a GENERATED mirror is committed at
# ``src/data/tag_vocabulary.json`` and refreshed by ``scripts/sync_tag_vocabulary.py``.
# A drift test in both CI suites fails if the mirror falls out of sync with the
# canonical, so a newly-added pipeline tag can never again render in English on the
# website (the bug PRs #161/#162 fixed by hand). See
# ``docs/tag-vocabulary-source-of-truth.md``.
#
# Episode tags are stored PascalCase and looked up via ``normalize_tag_slug``
# (lowercase + strip separators). This map only supplies DISPLAY labels — the
# trending GATE still comes from the DB (`trending_slugs`).
_MIRROR_PATH = Path(__file__).with_name("data") / "tag_vocabulary.json"


def normalize_tag_slug(slug: str) -> str:
    """Canonical lookup key for a tag slug — MUST match the pipeline + frontend impls.

    Lowercases and strips every non-alphanumeric char so ``SupplyChain`` (vocabulary),
    ``supply_chain`` (legacy DB slug), and ``supplychain`` (lowercased episode tag) all
    reconcile to ``supplychain``. Mirror of
    ``pipelines/.../content_builder/tag_vocabulary.py::normalize_tag_slug`` and
    ``frontend/src/hooks/useTagLabels.ts::normalizeTagSlug``.
    """
    return re.sub(r"[^a-z0-9]", "", (slug or "").lower())


def _load_canonical_display() -> dict[str, str]:
    """normalized-slug → zh-TW display, from the committed pipeline mirror."""
    raw = json.loads(_MIRROR_PATH.read_text(encoding="utf-8"))
    # The mirror carries a ``_comment`` provenance key (JSON has no comments); drop it.
    return {normalize_tag_slug(slug): zh for slug, zh in raw.items() if not slug.startswith("_")}


_CANONICAL_DISPLAY: dict[str, str] = _load_canonical_display()


def seed_if_empty(db: Session) -> None:
    """Insert seed tags when the table has no rows (first boot)."""
    if db.query(TagRegistry).first() is not None:
        return
    logger.info("tag_registry table is empty — seeding %d tags", len(_SEED))
    for slug, display_zh, tier in _SEED:
        db.add(TagRegistry(slug=slug, display_zh=display_zh, tier=tier))
    db.commit()


def auto_register(db: Session, slugs: list[str], min_episodes: int = 3) -> int:
    """Register unknown slugs as hidden. Returns count of newly inserted tags.

    Called with Firestore tag slugs that have at least *min_episodes* episodes.
    Slugs already in the registry are silently skipped.
    """
    existing = {r[0] for r in db.query(TagRegistry.slug).all()}
    new_slugs = [s for s in slugs if s not in existing]
    if not new_slugs:
        return 0
    for slug in new_slugs:
        # Seed the curated zh-TW label when the slug is in the canonical vocabulary,
        # so auto-discovered tags render in Chinese immediately instead of as their
        # raw English slug (and so the DB row can never mask the canonical label).
        display_zh = _CANONICAL_DISPLAY.get(normalize_tag_slug(slug), slug)
        db.add(TagRegistry(slug=slug, display_zh=display_zh, tier=TIER_HIDDEN))
    db.commit()
    logger.info("Auto-registered %d new tags as hidden", len(new_slugs))
    return len(new_slugs)


def sync_sectors(db: Session, sectors: list[dict]) -> int:
    """Upsert sector/theme exposures into the unified registry. Returns count of NEW rows.

    The pipeline universe owns sector identity, members, aliases and visuals; this only
    maintains the registry INDEX so admins can curate sector visibility alongside tags.
    Caller supplies the sector list (e.g. ``PodcastService.list_sectors()`` output) so
    this stays a pure sync DB helper, mirroring ``auto_register``.

    New sectors default to ``trending`` (VISIBLE) so a first sync never empties the live
    board — admins HIDE the ones they don't want. Existing rows refresh their display
    name / visuals from the universe but keep their curated ``tier`` untouched.
    """
    by_exposure = {
        r.exposure_id: r
        for r in db.query(TagRegistry).filter(TagRegistry.kind == KIND_SECTOR).all()
    }
    new_count = 0
    for sector in sectors:
        eid = str(sector.get("exposure_id") or "").strip()
        if not eid:
            continue
        display = str(sector.get("display_name") or eid)
        icon_id = sector.get("icon_id")
        color_hex = sector.get("color_hex")
        existing = by_exposure.get(eid)
        if existing is not None:
            existing.display_zh = display
            existing.icon_id = icon_id
            existing.color_hex = color_hex
        else:
            db.add(TagRegistry(
                slug=eid,  # exposure_id is globally unique (sector_*/theme_* prefixed)
                display_zh=display,
                tier=TIER_TRENDING,
                kind=KIND_SECTOR,
                exposure_id=eid,
                icon_id=icon_id,
                color_hex=color_hex,
            ))
            new_count += 1
    db.commit()
    logger.info("Synced sectors: %d new, %d refreshed", new_count, len(sectors) - new_count)
    return new_count


def hidden_tag_slugs(db: Session) -> set[str]:
    """NORMALIZED slugs of admin-hidden tags — excluded from the trending board.

    Trending is auto-surfaced by volume (any tag with enough recent episodes), so the
    registry tier acts as a HIDE-override only: a tag-kind row at tier='hidden' is
    suppressed. Returned normalized so it matches Firestore tag slugs of any spelling.
    """
    rows = (
        db.query(TagRegistry.slug)
        .filter(TagRegistry.kind == KIND_TAG, TagRegistry.tier == TIER_HIDDEN)
        .all()
    )
    return {normalize_tag_slug(r[0]) for r in rows if r[0]}


def hidden_sector_exposure_ids(db: Session) -> set[str]:
    """Exposure IDs of sectors the admin has HIDDEN — excluded from the public board.

    Default-visible semantics: a sector with no registry row (never synced) stays
    visible, so the board never silently empties between universe updates and syncs.
    """
    rows = (
        db.query(TagRegistry.exposure_id)
        .filter(TagRegistry.kind == KIND_SECTOR, TagRegistry.tier == TIER_HIDDEN)
        .all()
    )
    return {r[0] for r in rows if r[0]}


# ── Public query helpers ─────────────────────────────────────────────

def trending_slugs(db: Session) -> list[str]:
    """Slugs shown in the topics cloud (trending tier only, tag kind only)."""
    rows = (
        db.query(TagRegistry.slug)
        .filter(TagRegistry.tier == TIER_TRENDING, TagRegistry.kind == KIND_TAG)
        .all()
    )
    return [r[0] for r in rows]


def display_map(db: Session, tier: Optional[str] = None) -> dict[str, str]:
    """slug → zh-TW display name, optionally filtered by tier."""
    q = db.query(TagRegistry.slug, TagRegistry.display_zh)
    if tier:
        q = q.filter(TagRegistry.tier == tier)
    return {r[0]: r[1] for r in q.all()}


def registry_snapshot(db: Session) -> list[dict]:
    """Serializable snapshot for the /api/tags/registry endpoint.

    The frontend uses this purely as a slug → zh-TW label lookup (the trending
    RANKING comes from ``trending_slugs`` / the trending API, not from here). So
    return the FULL label catalogue — the canonical extraction vocabulary plus
    every DB row (all tiers) — so any agent-emitted tag renders in zh-TW across
    the site (episode hero, topic pages, episode cards), not just the curated
    trending subset. DB rows win over the canonical baseline (admin curation
    overrides) and carry their real tier.

    Entries are keyed by the NORMALIZED slug so the catalogue and the DB never
    emit two rows that the frontend would collapse to the same lookup key (e.g.
    canonical ``SupplyChain`` vs. DB ``supply_chain`` → both ``supplychain``).
    A DB row whose ``display_zh`` is just its own slug is an auto-registered
    English placeholder; it must NOT mask a curated canonical label.
    """
    by_norm: dict[str, dict] = {
        norm_slug: {"slug": norm_slug, "display_zh": zh, "tier": TIER_HIDDEN}
        for norm_slug, zh in _CANONICAL_DISPLAY.items()
    }
    for r in db.query(TagRegistry).all():
        # Tag-label catalogue only — sector rows are indexed in the same table but
        # must not pollute the tag display map. (Filtered in Python, not the query,
        # so a slug-only / mocked session without .filter() still works.)
        if getattr(r, "kind", KIND_TAG) == KIND_SECTOR:
            continue
        norm = normalize_tag_slug(r.slug)
        canonical_zh = _CANONICAL_DISPLAY.get(norm)
        is_placeholder = normalize_tag_slug(r.display_zh) == norm
        display_zh = canonical_zh if (is_placeholder and canonical_zh) else r.display_zh
        by_norm[norm] = {"slug": r.slug, "display_zh": display_zh, "tier": r.tier}
    return [by_norm[k] for k in sorted(by_norm)]
