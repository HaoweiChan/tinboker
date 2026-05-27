"""
Service for managing stock translations.
"""

import logging
from typing import Optional, List, Tuple
from sqlalchemy import func
from sqlalchemy.orm import Session
from src.database.models import StockTranslation
from src.schemas.translation import (
    TranslationCreate,
    TranslationUpdate,
    BulkImportItem,
)

logger = logging.getLogger(__name__)


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
                (StockTranslation.name_zh_tw.ilike(search_pattern))
            )
        # Get total count
        total = query.count()
        # Apply pagination
        offset = (page - 1) * limit
        items = query.order_by(StockTranslation.ticker).offset(offset).limit(limit).all()
        return items, total

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
        updated_by: Optional[str] = None
    ) -> Tuple[StockTranslation, bool]:
        """
        Create or update a translation.
        Returns tuple of (translation, is_new).
        """
        existing = self.get_by_ticker_market(ticker, market)
        if existing:
            # Update existing
            if name_en is not None:
                existing.name_en = name_en
            if name_zh_tw is not None:
                existing.name_zh_tw = name_zh_tw
            existing.translation_status = status
            existing.last_updated_by = updated_by
            self.db.commit()
            self.db.refresh(existing)
            return existing, False
        else:
            # Create new
            data = TranslationCreate(
                ticker=ticker,
                market=market,
                name_en=name_en,
                name_zh_tw=name_zh_tw,
                translation_status=status
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
