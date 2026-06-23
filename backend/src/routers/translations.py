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
    pref = getattr(t, "name_preference", None) or "auto"
    # Show the zh-TW name when it's a real CJK name AND the row isn't forced to English.
    show_zh = _has_cjk(t.name_zh_tw) and pref != "en"
    return TranslationSearchItem(
        ticker=t.ticker,
        market=t.market,
        name_en=t.name_en,
        name_zh_tw=t.name_zh_tw,
        brand_color=t.brand_color,
        aliases=t.aliases,
        translation_status=t.translation_status,
        name_preference=pref,
        has_zh_name=show_zh,
        display_name=(t.name_zh_tw if show_zh else (t.name_en or t.ticker)),
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
    # ponytail: cap at 500 (was 100) — the homepage feed requests every related_ticker
    # across ~60 episodes (158+ and growing). At 100, the alphabetically-last symbols
    # (all US tickers, since numeric TW/KR codes sort first) got truncated and rendered
    # name-less. 500 is a safe IN-clause bound; raise if a single page ever exceeds it.
    ticker_list = [t for t in tickers.split(",")][:500]
    service = TranslationService(db)
    rows = service.get_by_tickers(ticker_list, market)
    return TranslationSearchResponse(
        query=None, total=len(rows), items=[_to_search_item(t) for t in rows]
    )


@router.get("/aliases", response_model=TranslationSearchResponse)
async def list_alias_rows(
    response: Response,
    limit: int = Query(5000, ge=1, le=20000),
    db: Session = Depends(get_session),
):
    """All translations that carry curated aliases (read-only).

    Built for the tinboker-agents news alias index to pull operator-curated aliases.
    Registered before /{ticker} so "aliases" isn't captured as a ticker path param.
    """
    response.headers["Cache-Control"] = "public, max-age=300"
    service = TranslationService(db)
    rows = service.get_rows_with_aliases(limit=limit)
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
            aliases=translation.aliases,
            name_preference=getattr(translation, "name_preference", None) or "auto",
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
