"""On-ingest ticker discovery + name autofill.

When episodes are fetched, ensure every `related_ticker` has at least a PENDING
stub row in `stock_translations`, so newly-mentioned tickers surface in the admin
queue (`status=pending`) and become work items for the backfill agent. Immediately
after, try to fill each stub's name from market data (FinMind for TW, Massive for
US — see `translation_autofill`), so most tickers get a usable zh-TW/English label
without waiting on the agent.

Design:
- **Non-blocking & best-effort.** Scheduled as a background task; never blocks or
  fails the originating request.
- **Throttled by a process cache.** `_ensured` remembers symbols already handled, so
  steady-state cost is a set lookup — the DB/market APIs are only touched when a
  genuinely new ticker first appears.
- **Read-freeze safe.** Reuses episodes already fetched by the caller; opens its own
  short-lived DB session for the write (the request session is closed by then).
"""

import asyncio
import logging
from typing import Iterable

logger = logging.getLogger(__name__)

# Process-level caches. Reset on restart; the underlying insert is idempotent anyway.
_ensured: set[str] = set()
_inflight: set[str] = set()


def _extract(episodes: Iterable) -> set[str]:
    out: set[str] = set()
    for ep in episodes:
        rel = getattr(ep, "related_tickers", None)
        if rel is None and isinstance(ep, dict):
            rel = ep.get("related_tickers")
        for s in rel or []:
            if s and str(s).strip():
                out.add(str(s).strip().upper())
    return out


def _ensure_sync(symbols: list[str]) -> tuple[int, int]:
    """Insert pending stubs, then autofill names from market data. Returns (inserted, filled)."""
    from src.database.postgres import get_session
    from src.services.translation_autofill import autofill_names_for_rows
    from src.services.translation_service import TranslationService

    inserted = 0
    filled = 0
    for session in get_session():
        svc = TranslationService(session)
        inserted = svc.ensure_pending_stubs(symbols)
        # Re-read (now incl. the just-inserted stubs) and fill names in the same session.
        bare = [s.strip().upper().split(".")[0] for s in symbols if s and s.strip()]
        filled = autofill_names_for_rows(session, svc.get_by_tickers(bare))
        break
    return inserted, filled


def schedule_ticker_discovery(episodes: Iterable) -> None:
    """Queue a non-blocking task to ensure PENDING stubs for any new tickers.

    Safe to call from a request handler — returns immediately and swallows errors.
    """
    try:
        symbols = _extract(episodes)
    except Exception:
        return

    todo = symbols - _ensured - _inflight
    if not todo:
        return
    _inflight.update(todo)

    async def _run() -> None:
        try:
            # SQLAlchemy is sync — run off the event loop.
            inserted, filled = await asyncio.to_thread(_ensure_sync, sorted(todo))
            _ensured.update(todo)
            if inserted or filled:
                logger.info(
                    "ticker discovery: inserted %d pending stub(s), autofilled %d name(s)",
                    inserted, filled,
                )
        except Exception as e:
            logger.warning("ticker discovery failed: %s", e)
        finally:
            _inflight.difference_update(todo)

    try:
        asyncio.create_task(_run())
    except RuntimeError:
        # No running event loop (not expected inside an async handler) — drop.
        _inflight.difference_update(todo)
