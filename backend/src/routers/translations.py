"""
Public API endpoints for stock translations.
No authentication required.
"""

import logging
from typing import Optional
from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session
from src.database.postgres import get_session
from src.database.models import StockTranslation
from src.services.translation_service import TranslationService
from src.schemas.translation import (
    TranslationPublicResponse,
    TranslationCreate,
    TranslationSearchItem,
    TranslationSearchResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/stocks/translations",
    tags=["translations"]
)


def _has_cjk(text: Optional[str]) -> bool:
    """True if the text contains a CJK character (i.e. a real Chinese name).

    Distinguishes a genuine zh-TW name from an English/Latin value parked in the
    name_zh_tw column (e.g. "Arm", "Roku") so US English-preferred stocks resolve to
    their English label instead of a meaningless "Chinese" name.
    """
    if not text:
        return False
    # CJK Unified Ideographs (+ Ext A) and CJK Compatibility Ideographs.
    return any(
        "㐀" <= ch <= "鿿" or "豈" <= ch <= "﫿"
        for ch in text
    )


def _to_search_item(t: StockTranslation) -> TranslationSearchItem:
    has_zh = _has_cjk(t.name_zh_tw)
    return TranslationSearchItem(
        ticker=t.ticker,
        market=t.market,
        name_en=t.name_en,
        name_zh_tw=t.name_zh_tw,
        brand_color=t.brand_color,
        translation_status=t.translation_status,
        has_zh_name=has_zh,
        display_name=(t.name_zh_tw if has_zh else (t.name_en or t.ticker)),
    )


@router.get("/search", response_model=TranslationSearchResponse)
async def search_translations(
    response: Response,
    q: str = Query(..., min_length=1, description="Search by ticker, English name, or zh-TW name"),
    market: Optional[str] = Query(None, description="Optional market filter (US, TW, JP)"),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_session),
):
    """Read-only fuzzy search over translations (ticker / name_en / name_zh_tw).

    Powers the stock-translations MCP server. Never writes — unlike GET /{ticker},
    it does not auto-create stub rows.
    """
    response.headers["Cache-Control"] = "public, max-age=300"
    service = TranslationService(db)
    items, total = service.list_translations(market=market, search=q, page=1, limit=limit)
    return TranslationSearchResponse(
        query=q, total=total, items=[_to_search_item(t) for t in items]
    )


@router.get("/batch", response_model=TranslationSearchResponse)
async def batch_translations(
    response: Response,
    tickers: str = Query(..., description="Comma-separated tickers, e.g. AAPL,NVDA,2330"),
    market: Optional[str] = Query(None, description="Optional market filter (US, TW, JP)"),
    db: Session = Depends(get_session),
):
    """Resolve a list of tickers to localized labels in one call (read-only).

    Built for localizing a symbol-only list like an episode's related_tickers.
    """
    response.headers["Cache-Control"] = "public, max-age=300"
    ticker_list = [t for t in tickers.split(",")][:100]
    service = TranslationService(db)
    rows = service.get_by_tickers(ticker_list, market)
    return TranslationSearchResponse(
        query=None, total=len(rows), items=[_to_search_item(t) for t in rows]
    )


@router.get("/{ticker}", response_model=TranslationPublicResponse)
async def get_translation(
    ticker: str,
    response: Response,
    market: str = Query(..., description="Market code (US, TW, JP)"),
    name_en: Optional[str] = Query(None, description="English name hint for auto-creation"),
    auto_create: bool = Query(True, description="Auto-create pending entry if not found"),
    db: Session = Depends(get_session)
):
    """
    Get translation for a stock ticker.
    If not found and auto_create=True, creates a pending entry for admin review.
    """
    response.headers["Cache-Control"] = "no-store"
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
