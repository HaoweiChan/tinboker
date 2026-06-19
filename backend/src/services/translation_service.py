"""
Service for managing stock translations.
"""

import logging
from typing import Optional, List, Tuple
from sqlalchemy import func, cast, Text
from sqlalchemy.orm import Session
from src.database.models import StockTranslation
from src.schemas.translation import (
    TranslationCreate,
    TranslationUpdate,
    BulkImportItem,
)

logger = logging.getLogger(__name__)


def _normalize_aliases(aliases: Optional[List[str]]) -> Optional[List[str]]:
    """Strip/dedupe alias strings, preserving order. None stays None; [] clears the list."""
    if aliases is None:
        return None
    cleaned: List[str] = []
    for a in aliases:
        s = (a or "").strip()
        if s and s not in cleaned:
            cleaned.append(s)
    return cleaned


# Rows whose committed/auto "approved" zh name actually belongs to a DIFFERENT
# company (the English name is correct and disambiguates). Each tuple is
# (ticker, market, wrong_name_zh, correct_name_zh). The correction is
# self-deactivating — it only fires while the row still holds the wrong value —
# so it never fights a later human edit through the admin translations editor.
_KNOWN_NAME_CORRECTIONS: List[Tuple[str, str, str, str]] = [
    ("6285", "TW", "合勤控", "啟碁"),      # WNC = Wistron NeWeb; 合勤控 is 3704 (Zyxel)
    ("6147", "TW", "精材", "頎邦"),        # Chipbond; 精材 is 3374 (XinTec)
    ("3661", "TW", "譜瑞-KY", "世芯-KY"),  # Alchip; 譜瑞-KY is 4966 (Parade)
    ("3023", "TW", "新漢", "信邦"),        # SINBON Electronics; 新漢 is 8234 (NEXCOM)
    ("2745", "TW", "上銀", "五福"),        # Wu Fu Travel; 上銀 is 2049 (Hiwin)
    ("6472", "TW", "閎暉", "保瑞"),        # Bora Pharmaceuticals; 閎暉 is 3311
    ("3357", "TW", "再生-KY", "臺慶科"),   # Taiwan Ceramic; 再生-KY is 1337
    ("5351", "TW", "鉅祥", "鈺創"),        # Etron Technology; 鉅祥 is 2476
]


class TranslationService:
    """Service class for stock translation CRUD operations."""

    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, translation_id: int) -> Optional[StockTranslation]:
        """Get translation by ID."""
        return self.db.query(StockTranslation).filter(
            StockTranslation.id == translation_id
        ).first()

    def get_by_ticker_market(
        self, ticker: str, market: str
    ) -> Optional[StockTranslation]:
        """Get translation by ticker and market."""
        return self.db.query(StockTranslation).filter(
            StockTranslation.ticker == ticker.upper(),
            StockTranslation.market == market.upper()
        ).first()

    def apply_known_name_corrections(self) -> int:
        """Fix rows whose approved zh name belongs to a different company.

        Self-deactivating: a row is only updated while it still holds the exact
        known-wrong value, so re-running is a no-op and a later human edit is
        never overwritten. Returns the number of rows corrected.
        """
        fixed = 0
        for ticker, market, wrong_zh, correct_zh in _KNOWN_NAME_CORRECTIONS:
            row = self.get_by_ticker_market(ticker, market)
            if row is not None and row.name_zh_tw == wrong_zh:
                row.name_zh_tw = correct_zh
                row.last_updated_by = "known_correction"
                self.db.commit()
                logger.info("Corrected %s %s zh name %s -> %s", ticker, market, wrong_zh, correct_zh)
                fixed += 1
        return fixed

    def list_translations(
        self,
        market: Optional[str] = None,
        status: Optional[str] = None,
        search: Optional[str] = None,
        page: int = 1,
        limit: int = 50
    ) -> Tuple[List[StockTranslation], int]:
        """
        List translations with optional filters.
        Returns tuple of (items, total_count).
        """
        query = self.db.query(StockTranslation)
        # Apply filters
        if market:
            query = query.filter(StockTranslation.market == market.upper())
        if status:
            query = query.filter(StockTranslation.translation_status == status)
        if search:
            search_pattern = f"%{search}%"
            query = query.filter(
                (StockTranslation.ticker.ilike(search_pattern)) |
                (StockTranslation.name_en.ilike(search_pattern)) |
                (StockTranslation.name_zh_tw.ilike(search_pattern)) |
                (cast(StockTranslation.aliases, Text).ilike(search_pattern))
            )
        # Get total count
        total = query.count()
        # Apply pagination
        offset = (page - 1) * limit
        items = query.order_by(StockTranslation.ticker).offset(offset).limit(limit).all()
        return items, total

    def get_by_tickers(
        self, tickers: List[str], market: Optional[str] = None
    ) -> List[StockTranslation]:
        """Resolve many tickers at once (symbol-only, mixed markets OK).

        Used by the public batch endpoint to localize a list like `related_tickers`.
        A ticker present in more than one market yields multiple rows.
        """
        norm = sorted({t.strip().upper() for t in tickers if t and t.strip()})
        if not norm:
            return []
        query = self.db.query(StockTranslation).filter(StockTranslation.ticker.in_(norm))
        if market:
            query = query.filter(StockTranslation.market == market.upper())
        return query.order_by(StockTranslation.ticker).all()

    def ensure_pending_stubs(self, symbols: List[str]) -> int:
        """Insert PENDING stub rows for symbols not yet in the table (any market).

        Used by on-ingest discovery so newly-mentioned tickers surface in the admin
        queue (`status=pending`) and become work items for the backfill agent.
        Idempotent. Stores the bare symbol (exchange suffix stripped) with an inferred
        market. Returns the number of rows inserted.

        Market inference is a best-effort default for a TW-focused app:
        - digits, optionally with a single class letter (e.g. 00738U, 00632R) → TW
          (TW stock/ETF/futures codes; the bare `.isdigit()` check alone mislabeled these)
        - otherwise alphabetic → US
        Foreign 6-digit codes (KR/CN/HK) are ambiguous by format and fall to the TW
        default; the backfill agent corrects the market when it resolves the name.
        """
        # Collect distinct bare symbols with an inferred market.
        cleaned: dict[str, str] = {}
        for s in symbols:
            if not s or not s.strip():
                continue
            bare = s.strip().upper().split(".")[0]
            if not bare:
                continue
            # Treat "digits + optional trailing class letter" as a TW numeric code.
            core = bare[:-1] if (len(bare) > 1 and bare[-1].isalpha() and bare[:-1].isdigit()) else bare
            cleaned.setdefault(bare, "TW" if core.isdigit() else "US")
        if not cleaned:
            return 0

        existing = {r.ticker for r in self.get_by_tickers(list(cleaned.keys()))}
        inserted = 0
        for ticker, market in cleaned.items():
            if ticker in existing:
                continue
            try:
                self.create(
                    TranslationCreate(
                        ticker=ticker,
                        market=market,
                        name_en=None,
                        name_zh_tw=None,
                        translation_status="pending",
                    ),
                    updated_by="ingest_discovery",
                )
                inserted += 1
            except Exception as e:
                logger.warning("ensure_pending_stubs: skip %s/%s: %s", ticker, market, e)
                self.db.rollback()
        return inserted

    def create(
        self,
        data: TranslationCreate,
        updated_by: Optional[str] = None
    ) -> StockTranslation:
        """Create a new translation."""
        translation = StockTranslation(
            ticker=data.ticker.upper(),
            market=data.market.upper(),
            name_en=data.name_en,
            name_zh_tw=data.name_zh_tw,
            brand_color=getattr(data, 'brand_color', None),
            aliases=_normalize_aliases(getattr(data, 'aliases', None)),
            name_preference=(getattr(data, 'name_preference', None) or "auto"),
            translation_status=data.translation_status,
            last_updated_by=updated_by
        )
        self.db.add(translation)
        self.db.commit()
        self.db.refresh(translation)
        logger.info(f"Created translation: {translation.ticker}/{translation.market}")
        return translation

    def update(
        self,
        translation_id: int,
        data: TranslationUpdate,
        updated_by: Optional[str] = None
    ) -> Optional[StockTranslation]:
        """Update an existing translation."""
        translation = self.get_by_id(translation_id)
        if not translation:
            return None
        update_data = data.model_dump(exclude_unset=True)
        if "aliases" in update_data:
            update_data["aliases"] = _normalize_aliases(update_data["aliases"])
        for field, value in update_data.items():
            setattr(translation, field, value)
        translation.last_updated_by = updated_by
        self.db.commit()
        self.db.refresh(translation)
        logger.info(f"Updated translation: {translation.ticker}/{translation.market}")
        return translation

    def delete(self, translation_id: int) -> bool:
        """Delete a translation."""
        translation = self.get_by_id(translation_id)
        if not translation:
            return False
        self.db.delete(translation)
        self.db.commit()
        logger.info(f"Deleted translation ID: {translation_id}")
        return True

    def create_or_update(
        self,
        ticker: str,
        market: str,
        name_en: Optional[str] = None,
        name_zh_tw: Optional[str] = None,
        status: str = "auto",
        updated_by: Optional[str] = None,
        brand_color: Optional[str] = None,
        aliases: Optional[List[str]] = None,
        name_preference: Optional[str] = None,
    ) -> Tuple[StockTranslation, bool]:
        """
        Create or update a translation. Only provided (non-None) fields are applied,
        so callers never clobber existing values they didn't intend to touch.
        Returns tuple of (translation, is_new).
        """
        existing = self.get_by_ticker_market(ticker, market)
        if existing:
            if name_en is not None:
                existing.name_en = name_en
            if name_zh_tw is not None:
                existing.name_zh_tw = name_zh_tw
            if brand_color is not None:
                existing.brand_color = brand_color
            if aliases is not None:
                existing.aliases = _normalize_aliases(aliases)
            if name_preference is not None:
                existing.name_preference = name_preference
            existing.translation_status = status
            existing.last_updated_by = updated_by
            self.db.commit()
            self.db.refresh(existing)
            return existing, False
        else:
            data = TranslationCreate(
                ticker=ticker,
                market=market,
                name_en=name_en,
                name_zh_tw=name_zh_tw,
                translation_status=status,
                brand_color=brand_color,
                aliases=aliases,
                name_preference=name_preference,
            )
            return self.create(data, updated_by), True

    def bulk_import(
        self,
        items: List[BulkImportItem],
        updated_by: Optional[str] = None
    ) -> Tuple[int, int, List[str]]:
        """
        Bulk import translations.
        Returns tuple of (imported_count, updated_count, errors).
        """
        imported = 0
        updated = 0
        errors = []
        for item in items:
            try:
                _, is_new = self.create_or_update(
                    ticker=item.ticker,
                    market=item.market,
                    name_en=item.name_en,
                    name_zh_tw=item.name_zh_tw,
                    status=item.translation_status,
                    updated_by=updated_by,
                    brand_color=item.brand_color,
                    aliases=item.aliases,
                    name_preference=item.name_preference,
                )
                if is_new:
                    imported += 1
                else:
                    updated += 1
            except Exception as e:
                errors.append(f"{item.ticker}/{item.market}: {str(e)}")
                logger.error(f"Bulk import error for {item.ticker}: {e}")
        return imported, updated, errors

    def get_rows_with_aliases(self, limit: int = 5000) -> List[StockTranslation]:
        """All rows that carry at least one curated alias (for the agents' alias-index pull)."""
        rows = (
            self.db.query(StockTranslation)
            .filter(StockTranslation.aliases.isnot(None))
            .order_by(StockTranslation.ticker)
            .limit(limit)
            .all()
        )
        # JSON column may hold an empty list; keep only rows with real aliases.
        return [r for r in rows if r.aliases]

    def get_translatable_rows(self, limit: int = 20000) -> List[StockTranslation]:
        """All rows that carry a usable name (zh-TW or English), for the suggestion index.

        Powers TW-stock autocomplete: the Massive universe is US-only and English, so
        Chinese names / numeric TW tickers (e.g. 2330 → 台積電) live only here. Excludes
        bare PENDING stubs that have neither name (nothing to index for them).
        """
        return (
            self.db.query(StockTranslation)
            .filter(
                (StockTranslation.name_zh_tw.isnot(None) & (StockTranslation.name_zh_tw != "")) |
                (StockTranslation.name_en.isnot(None) & (StockTranslation.name_en != ""))
            )
            .order_by(StockTranslation.ticker)
            .limit(limit)
            .all()
        )

    def get_missing_translations(
        self,
        market: Optional[str] = None,
        limit: int = 100
    ) -> List[StockTranslation]:
        """Get translations without ZH-TW name."""
        query = self.db.query(StockTranslation).filter(
            (StockTranslation.name_zh_tw.is_(None)) |
            (StockTranslation.name_zh_tw == "")
        )
        if market:
            query = query.filter(StockTranslation.market == market.upper())
        return query.order_by(StockTranslation.ticker).limit(limit).all()

    def backfill_translations(
        self,
        entries: list[tuple],
    ) -> int:
        """
        Seed stock translations from a list of (ticker, market, name_en, name_zh_tw, status).
        - Inserts rows that don't exist yet.
        - Fills in name_en/name_zh_tw for existing stub rows (name_en is NULL and status
          is not "approved"), without downgrading approved rows.
        - Does not write brand_color; the stock_translations table is the source of truth
          for colors and is maintained through the admin/bulk endpoints.
        Returns count of rows inserted or updated.
        """
        affected = 0
        for ticker, market, name_en, name_zh_tw, status in entries:
            existing = self.get_by_ticker_market(ticker, market)
            if existing is None:
                data = TranslationCreate(
                    ticker=ticker,
                    market=market,
                    name_en=name_en,
                    name_zh_tw=name_zh_tw,
                    translation_status=status,
                )
                self.create(data, "startup_backfill")
                affected += 1
            elif existing.name_en is None and existing.translation_status != "approved":
                # Populate empty auto-created stubs without touching approved rows
                existing.name_en = name_en
                existing.name_zh_tw = name_zh_tw
                existing.translation_status = status
                existing.last_updated_by = "startup_backfill"
                self.db.commit()
                affected += 1
        return affected

    def get_stats(self) -> dict:
        """Get translation statistics."""
        total = self.db.query(func.count(StockTranslation.id)).scalar()
        by_market = self.db.query(
            StockTranslation.market,
            func.count(StockTranslation.id)
        ).group_by(StockTranslation.market).all()
        by_status = self.db.query(
            StockTranslation.translation_status,
            func.count(StockTranslation.id)
        ).group_by(StockTranslation.translation_status).all()
        translated = self.db.query(func.count(StockTranslation.id)).filter(
            StockTranslation.name_zh_tw.isnot(None),
            StockTranslation.name_zh_tw != ""
        ).scalar()
        return {
            "total": total,
            "translated": translated,
            "by_market": {m: c for m, c in by_market},
            "by_status": {s: c for s, c in by_status}
        }
