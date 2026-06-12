"""Auto-resolve ticker display names from the market-data APIs we already integrate.

Complements on-ingest discovery (``translation_discovery``): once a PENDING stub
exists for a newly-mentioned ticker, this fills in its name from the same sources
the app uses for prices — **FinMind** for TW (the Traditional-Chinese ``stock_name``
from the cached ``TaiwanStockInfo`` table, an in-memory lookup with no per-ticker API
cost) and **Massive** for US (the English company name, a reference-data call).

Guarantees:
- **Best-effort.** Never raises into the caller; a failed lookup leaves the stub
  ``pending`` for the agent/admin to resolve.
- **Fills, never clobbers.** Only touches non-``approved`` rows that lack the
  market-appropriate name; writes ``status='auto'`` so a human approval still wins and
  the agent can still refine (zh-TW for US names, brand colors, aliases).
- **Cheap on repeat.** A row that already has a name is skipped *before* any API call,
  so re-running over the same symbols (e.g. after a restart clears the discovery cache)
  costs one DB read and no network.
"""

from __future__ import annotations

import logging
from typing import Iterable, Optional

logger = logging.getLogger(__name__)


def _needs_name(row) -> bool:
    """True for a non-approved stub missing its market-appropriate display name."""
    if row.translation_status == "approved":
        return False
    if row.market == "TW":
        return not (row.name_zh_tw or "").strip()
    if row.market == "US":
        return not (row.name_en or "").strip()
    # Other markets (JP/KR/HK/…) aren't covered by FinMind/Massive name lookup — leave
    # them to the backfill agent.
    return False


def _resolve_name(dc, ticker: str, market: str) -> tuple[Optional[str], Optional[str]]:
    """(name_en, name_zh_tw) for one ticker from market data; (None, None) if unknown.

    FinMind's ``TaiwanStockInfo.stock_name`` is Traditional Chinese; Massive's
    ``ticker_details.name`` is English. ``get_ticker_details`` echoes the bare symbol as
    ``name`` when it can't resolve, so we treat ``name == ticker`` as a miss.
    """
    try:
        if market == "TW":
            details = dc.finmind_service.get_ticker_details(ticker)
            name = (details or {}).get("name")
            return (None, name) if name and name != ticker else (None, None)
        if market == "US":
            details = dc.massive_service.get_ticker_details(ticker)
            name = (details or {}).get("name")
            return (name, None) if name and name != ticker else (None, None)
    except Exception as e:  # market API hiccup — best-effort, leave the stub pending
        logger.debug("autofill: resolve %s/%s failed: %s", ticker, market, e)
    return (None, None)


def autofill_names_for_rows(session, rows: Iterable, dc=None) -> int:
    """Fill names for the given translation rows from market data. Returns count filled.

    ``dc`` is a ``DataCollectionService`` (injectable for tests); constructed lazily so
    a missing API key never breaks the caller.
    """
    from src.services.translation_service import TranslationService

    targets = [r for r in rows if _needs_name(r)]
    if not targets:
        return 0

    if dc is None:
        try:
            from src.services.data_collection_service import DataCollectionService

            dc = DataCollectionService()
        except Exception as e:
            logger.warning("autofill: market services unavailable: %s", e)
            return 0

    service = TranslationService(session)
    filled = 0
    for r in targets:
        name_en, name_zh_tw = _resolve_name(dc, r.ticker, r.market)
        if not (name_en or name_zh_tw):
            continue
        try:
            service.create_or_update(
                ticker=r.ticker,
                market=r.market,
                name_en=name_en,
                name_zh_tw=name_zh_tw,
                status="auto",
                updated_by="market_autofill",
            )
            filled += 1
        except Exception as e:
            logger.warning("autofill: write %s/%s failed: %s", r.ticker, r.market, e)
            session.rollback()
    if filled:
        logger.info("autofill: resolved %d ticker name(s) from market data", filled)
    return filled


def autofill_names_sync(symbols: Iterable[str]) -> int:
    """Resolve names for any existing stub rows matching ``symbols``. Returns count filled.

    Opens its own short-lived session (safe to call from a background task).
    """
    from src.database.postgres import get_session
    from src.services.translation_service import TranslationService

    norm = sorted({str(s).strip().upper().split(".")[0] for s in symbols if s and str(s).strip()})
    if not norm:
        return 0
    for session in get_session():
        rows = TranslationService(session).get_by_tickers(norm)
        return autofill_names_for_rows(session, rows)
    return 0
