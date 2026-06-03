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
        market (numeric → TW, else US). Returns the number of rows inserted.
        """
        # Collect distinct bare symbols with an inferred market.
        cleaned: dict[str, str] = {}
        for s in symbols:
            if not s or not s.strip():
                continue
            bare = s.strip().upper().split(".")[0]
            if not bare:
                continue
            cleaned.setdefault(bare, "TW" if bare.isdigit() else "US")
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
    ) -> Tuple[StockTranslation, bool]:
        """
        Create or update a translation.
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
                    updated_by=updated_by
                )
                if is_new:
                    imported += 1
                else:
                    updated += 1
            except Exception as e:
                errors.append(f"{item.ticker}/{item.market}: {str(e)}")
                logger.error(f"Bulk import error for {item.ticker}: {e}")
        return imported, updated, errors

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
        colors: dict[str, str],
    ) -> int:
        """
        Seed stock translations from a list of (ticker, market, name_en, name_zh_tw, status).
        - Inserts rows that don't exist yet.
        - Fills in name_en/name_zh_tw/brand_color for existing stub rows (name_en is NULL
          and status is not "approved"), without downgrading approved rows.
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
                    brand_color=colors.get(ticker),
                )
                self.create(data, "startup_backfill")
                affected += 1
            elif existing.name_en is None and existing.translation_status != "approved":
                # Populate empty auto-created stubs without touching approved rows
                existing.name_en = name_en
                existing.name_zh_tw = name_zh_tw
                existing.translation_status = status
                if existing.brand_color is None:
                    existing.brand_color = colors.get(ticker)
                existing.last_updated_by = "startup_backfill"
                self.db.commit()
                affected += 1
        return affected

    def backfill_brand_colors(self, colors: dict[str, str]) -> int:
        """Set brand_color for rows where it is currently NULL. Returns count updated."""
        rows = (
            self.db.query(StockTranslation)
            .filter(StockTranslation.brand_color.is_(None))
            .all()
        )
        updated = 0
        for row in rows:
            color = colors.get(row.ticker)
            if color:
                row.brand_color = color
                updated += 1
        if updated:
            self.db.commit()
        return updated

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
