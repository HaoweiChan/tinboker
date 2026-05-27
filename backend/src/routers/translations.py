"""
Public API endpoints for stock translations.
No authentication required.
"""

import logging
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from src.database.postgres import get_session
from src.services.translation_service import TranslationService
from src.schemas.translation import TranslationPublicResponse, TranslationCreate

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/stocks/translations",
    tags=["translations"]
)


@router.get("/{ticker}", response_model=TranslationPublicResponse)
async def get_translation(
    ticker: str,
    market: str = Query(..., description="Market code (US, TW, JP)"),
    name_en: Optional[str] = Query(None, description="English name hint for auto-creation"),
    auto_create: bool = Query(True, description="Auto-create pending entry if not found"),
    db: Session = Depends(get_session)
):
    """
    Get translation for a stock ticker.
    If not found and auto_create=True, creates a pending entry for admin review.
    """
    service = TranslationService(db)
    translation = service.get_by_ticker_market(ticker.upper(), market.upper())
    if translation:
        return TranslationPublicResponse(
            ticker=translation.ticker,
            market=translation.market,
            name_en=translation.name_en,
            name_zh_tw=translation.name_zh_tw,
            brand_color=translation.brand_color,
        )
    # Not found - auto-create pending entry if enabled
    if auto_create:
        try:
            create_data = TranslationCreate(
                ticker=ticker.upper(),
                market=market.upper(),
                name_en=name_en,
                name_zh_tw=None,
                translation_status="pending"
            )
            translation = service.create(create_data, updated_by="auto")
            logger.info(f"Auto-created pending translation: {ticker}/{market}")
            return TranslationPublicResponse(
                ticker=translation.ticker,
                market=translation.market,
                name_en=translation.name_en,
                name_zh_tw=translation.name_zh_tw
            )
        except Exception as e:
            logger.warning(f"Failed to auto-create translation {ticker}/{market}: {e}")
    # Return empty response if no translation and auto-create failed/disabled
    return TranslationPublicResponse(
        ticker=ticker.upper(),
        market=market.upper(),
        name_en=name_en,
        name_zh_tw=None
    )
