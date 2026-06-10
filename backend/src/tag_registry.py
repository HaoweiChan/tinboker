"""Centralized tag registry — DB-backed with in-code seed data.

On first boot (empty table), the seed data below is inserted so the system
works out of the box. After that, all management is via the admin UI
(``/admin/tags``) which writes to the ``tag_registry`` Postgres table.

Quality tiers
─────────────
  trending   → shown in the topics-cloud page + trending API
  valid      → taggable on episodes, linkable via /topics/:tag, but NOT in trending
  suppressed → hidden everywhere (junk tags)
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Optional

from sqlalchemy.orm import Session

from src.database.models import TagRegistry

logger = logging.getLogger(__name__)


class TagTier(str, Enum):
    TRENDING = "trending"
    VALID = "valid"
    SUPPRESSED = "suppressed"


# ── Seed data (inserted once when table is empty) ───────────────────
_SEED: list[tuple[str, str, str]] = [
    ("advanced_packaging", "先進封裝", "trending"),
    ("ai", "AI", "trending"),
    ("ai_chip", "AI 晶片", "trending"),
    ("bitcoin", "比特幣", "trending"),
    ("capital_expenditure", "資本支出", "trending"),
    ("centralbanks", "央行", "trending"),
    ("cryptocurrency", "加密貨幣", "trending"),
    ("datacenters", "資料中心", "trending"),
    ("demographics", "人口趨勢", "trending"),
    ("digitalassets", "數位資產", "trending"),
    ("earningsreport", "財報", "trending"),
    ("electric_vehicles", "電動車", "trending"),
    ("electricvehicles", "電動車", "trending"),
    ("etf", "ETF", "valid"),
    ("ev", "電動車", "trending"),
    ("federalreserve", "聯準會", "trending"),
    ("financialregulation", "金融監管", "trending"),
    ("fiscalpolicy", "財政政策", "trending"),
    ("fixedincome", "固定收益", "trending"),
    ("interestrates", "利率", "trending"),
    ("interestratepolicy", "利率政策", "trending"),
    ("japanmarket", "日本市場", "trending"),
    ("labormarket", "就業市場", "trending"),
    ("low_earth_orbit_satellite", "低軌衛星", "trending"),
    ("marketnarratives", "市場敘事", "trending"),
    ("media_industry", "媒體產業", "trending"),
    ("mergers_and_acquisitions", "併購", "trending"),
    ("monetarypolicy", "貨幣政策", "trending"),
    ("powersupply", "電力供應", "trending"),
    ("privatemarkets", "私募市場", "trending"),
    ("semiconductor", "半導體", "trending"),
    ("streaming_services", "串流服務", "trending"),
    ("supply_chain", "供應鏈", "trending"),
    ("taiwaneconomy", "台灣經濟", "valid"),
    ("trade_war", "貿易戰", "trending"),
    ("us_stocks", "美股", "trending"),
    ("useconomy", "美國經濟", "trending"),
    ("usstockmarket", "美股市場", "trending"),
    ("ustreasuries", "美債", "trending"),
    ("valuation", "估值", "valid"),
]


def seed_if_empty(db: Session) -> None:
    """Insert seed tags when the table has no rows (first boot)."""
    if db.query(TagRegistry).first() is not None:
        return
    logger.info("tag_registry table is empty — seeding %d tags", len(_SEED))
    for slug, display_zh, tier in _SEED:
        db.add(TagRegistry(slug=slug, display_zh=display_zh, tier=tier))
    db.commit()


# ── Public query helpers ─────────────────────────────────────────────

def trending_slugs(db: Session) -> list[str]:
    """Slugs shown in the topics cloud (trending tier only)."""
    rows = db.query(TagRegistry.slug).filter(TagRegistry.tier == "trending").all()
    return [r[0] for r in rows]


def all_displayable_slugs(db: Session) -> list[str]:
    """Slugs that are valid for display (trending + valid, not suppressed)."""
    rows = (
        db.query(TagRegistry.slug)
        .filter(TagRegistry.tier.in_(["trending", "valid"]))
        .all()
    )
    return [r[0] for r in rows]


def display_map(db: Session, tier: Optional[str] = None) -> dict[str, str]:
    """slug → zh-TW display name, optionally filtered by tier."""
    q = db.query(TagRegistry.slug, TagRegistry.display_zh)
    if tier:
        q = q.filter(TagRegistry.tier == tier)
    else:
        q = q.filter(TagRegistry.tier.in_(["trending", "valid"]))
    return {r[0]: r[1] for r in q.all()}


def registry_snapshot(db: Session) -> list[dict]:
    """Serializable snapshot for the /api/tags/registry endpoint."""
    rows = (
        db.query(TagRegistry)
        .filter(TagRegistry.tier.in_(["trending", "valid"]))
        .order_by(TagRegistry.slug)
        .all()
    )
    return [
        {"slug": r.slug, "display_zh": r.display_zh, "tier": r.tier}
        for r in rows
    ]
