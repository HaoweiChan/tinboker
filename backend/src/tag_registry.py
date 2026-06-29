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

import logging
import re
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


def normalize_tag_slug(slug: str) -> str:
    """Canonical lookup key for a tag slug — MUST match the pipeline + frontend impls.

    Lowercases and strips every non-alphanumeric char so ``SupplyChain`` (vocabulary),
    ``supply_chain`` (legacy DB slug), and ``supplychain`` (lowercased episode tag) all
    reconcile to ``supplychain``. Mirror of
    ``pipelines/.../content_builder/tag_vocabulary.py::normalize_tag_slug`` and
    ``frontend/src/hooks/useTagLabels.ts::normalizeTagSlug``.
    """
    return re.sub(r"[^a-z0-9]", "", (slug or "").lower())


def normalize_exposure_id(exposure_id: str | None) -> str:
    """Canonical exposure id — themes and sectors share one ``sector_`` namespace.

    Legacy curated themes were keyed ``theme_<id>``; they are one concept ("a sector")
    to the user, so both collapse to ``sector_<id>``. Apply when grouping episode
    ``sector_exposures`` so pre-migration data (still ``theme_<id>``) folds into the
    same board entry as the unified universe. Mirror of
    ``pipelines/.../shared/sectors.py::normalize_exposure_id`` and the frontend
    ``SectorIcon.tsx::normalizeExposureId``.
    """
    s = str(exposure_id or "")
    return "sector_" + s[len("theme_"):] if s.startswith("theme_") else s


def canonical_label(slug: str) -> str:
    """zh-TW display for a tag slug from the canonical vocabulary, else the slug itself.

    Used to label VIRTUAL admin rows (Firestore tags not yet in the registry).
    """
    return _CANONICAL_DISPLAY.get(normalize_tag_slug(slug), slug)


def canonical_tag_slugs() -> frozenset[str]:
    """NORMALIZED slugs of the canonical tag vocabulary — the source of truth for which
    tags are 'real'.

    The LLM writer is only prompt-constrained to this vocabulary, so the Firestore
    ``tags`` collection accumulates thousands of off-vocabulary slugs (hallucinated
    proper nouns, ETF/fund names, ticker symbols). Trending + admin intersect against
    this set so only real topics surface. Add a tag via tag_vocabulary.json.
    """
    return frozenset(_CANONICAL_DISPLAY.keys())


def _load_canonical_display() -> dict[str, str]:
    """normalized-slug → zh-TW display, from the committed seed data."""
    from src.data.tag_vocabulary_seed import TAG_VOCABULARY_SEED
    return {normalize_tag_slug(slug): zh for slug, zh in TAG_VOCABULARY_SEED.items()}


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
    # Store + compare on the NORMALIZED slug so case/separator variants (AI vs ai,
    # ai_chip vs aichip) can never create duplicate rows.
    existing = {normalize_tag_slug(r[0]) for r in db.query(TagRegistry.slug).all()}
    seen: set[str] = set()
    new_slugs: list[str] = []
    for s in slugs:
        n = normalize_tag_slug(s)
        if n and n not in existing and n not in seen:
            seen.add(n)
            new_slugs.append(n)
    if not new_slugs:
        return 0
    for slug in new_slugs:  # already normalized
        # Seed the curated zh-TW label when the slug is in the canonical vocabulary,
        # so auto-discovered tags render in Chinese immediately instead of as their
        # raw English slug (and so the DB row can never mask the canonical label).
        display_zh = _CANONICAL_DISPLAY.get(slug, slug)
        db.add(TagRegistry(slug=slug, display_zh=display_zh, tier=TIER_HIDDEN))
    db.commit()
    logger.info("Auto-registered %d new tags as hidden", len(new_slugs))
    return len(new_slugs)


def consolidate_tag_registry(db: Session) -> int:
    """Merge duplicate kind='tag' rows that share a normalized slug onto ONE canonical
    row (slug = normalized), carrying any 'hidden' curation and the best zh-TW label.

    Self-heals case/separator duplicates (ai/AI, ai_chip/aichip) and drops CJK-only
    slugs that normalize to an empty key. Runs on backend startup; idempotent — a no-op
    once the registry is canonical. Mirrors the sector self-heal in sync_sectors.
    """
    rows = db.query(TagRegistry).filter(TagRegistry.kind == KIND_TAG).all()
    groups: dict[str, list[TagRegistry]] = {}
    for r in rows:
        groups.setdefault(normalize_tag_slug(r.slug), []).append(r)

    removed = 0
    for norm, grp in groups.items():
        if not norm:  # un-normalizable (CJK-only) slug — never a valid tag key
            for r in grp:
                db.delete(r)
                removed += 1
            continue
        if len(grp) == 1 and grp[0].slug == norm:
            continue  # already canonical
        survivor = next((r for r in grp if r.slug == norm), grp[0])
        any_hidden = any(r.tier == TIER_HIDDEN for r in grp)
        better_label = next((r.display_zh for r in grp if r.display_zh and r.display_zh != r.slug), None)
        for r in grp:
            if r is not survivor:
                db.delete(r)
                removed += 1
        db.flush()  # release duplicate slugs (unique index) before renaming the survivor
        survivor.slug = norm
        if any_hidden:
            survivor.tier = TIER_HIDDEN
        if better_label:
            survivor.display_zh = better_label
    db.commit()
    if removed:
        logger.info("Consolidated tag registry: removed %d duplicate/junk rows", removed)
    return removed


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
            existing.exposure_type = sector.get("exposure_type")
            existing.members = sector.get("members")
            existing.aliases = sector.get("aliases")
        else:
            db.add(TagRegistry(
                slug=eid,  # exposure_id is globally unique (sector_*/theme_* prefixed)
                display_zh=display,
                tier=TIER_TRENDING,
                kind=KIND_SECTOR,
                exposure_id=eid,
                icon_id=icon_id,
                color_hex=color_hex,
                exposure_type=sector.get("exposure_type"),
                members=sector.get("members"),
                aliases=sector.get("aliases"),
            ))
            new_count += 1

    # Self-heal the theme_ -> sector_ unification: drop superseded ``theme_<id>`` sector
    # rows once their ``sector_<id>`` equivalent exists, carrying any admin 'hidden'
    # curation onto the survivor. Idempotent — a no-op once the rename has settled.
    synced_ids = {str(s.get("exposure_id") or "") for s in sectors}
    db.flush()  # make rows added above queryable for the survivor lookup
    removed = 0
    for row in [r for r in by_exposure.values() if str(r.exposure_id or "").startswith("theme_")]:
        target = normalize_exposure_id(row.exposure_id)
        if target not in synced_ids:
            continue  # the exposure is gone from the universe entirely; leave it
        if row.tier == TIER_HIDDEN:
            survivor = (
                db.query(TagRegistry)
                .filter(TagRegistry.kind == KIND_SECTOR, TagRegistry.exposure_id == target)
                .first()
            )
            if survivor is not None and survivor.tier != TIER_HIDDEN:
                survivor.tier = TIER_HIDDEN
        db.delete(row)
        removed += 1

    db.commit()
    logger.info(
        "Synced sectors: %d new, %d refreshed, %d legacy theme_ rows removed",
        new_count, len(sectors) - new_count, removed,
    )
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


def hidden_offvocab_slugs(db: Session) -> set[str]:
    """NORMALIZED slugs of admin-hidden tags that are NOT in the canonical vocabulary.

    Off-vocabulary junk an episode may still carry (e.g. an LLM-emitted ``TaiwanStocks``
    duplicating the curated 台股/``TWStocks``) that the admin has hidden. The episode hero
    filters its tag chips against this set so a hidden junk tag stops surfacing there.
    In-vocab tags are excluded on purpose — a real topic stays on episode pages even when
    an auto-discover run parked it at tier='hidden'; its TRENDING visibility is curated
    separately.
    """
    return hidden_tag_slugs(db) - canonical_tag_slugs()


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
    trending subset. A DB row contributes its real TIER; for the DISPLAY label the
    canonical vocabulary is authoritative (in-vocab tags have no admin rename UI, and
    an auto-registered row must never freeze a label across a later vocab edit). Off-
    vocab tags — not in the vocabulary — take their label from the DB row.

    Entries are keyed by the NORMALIZED slug so the catalogue and the DB never
    emit two rows that the frontend would collapse to the same lookup key (e.g.
    canonical ``SupplyChain`` vs. DB ``supply_chain`` → both ``supplychain``).
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
        # Canonical (vocabulary) label is authoritative for in-vocab tags; the DB row only
        # contributes its tier (there is no admin rename UI for canonical tags). This also
        # un-freezes the label for tags auto-registered before a vocab edit — e.g. an old
        # "IPO"→"首次公開發行" row now renders the updated "IPO" with no data backfill.
        # Off-vocab tags keep their DB display_zh (the only place their label can come from).
        display_zh = canonical_zh if canonical_zh else r.display_zh
        by_norm[norm] = {"slug": r.slug, "display_zh": display_zh, "tier": r.tier}
    return [by_norm[k] for k in sorted(by_norm)]
