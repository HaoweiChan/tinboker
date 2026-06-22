"""
Service for managing stock translations.
"""

import logging
import re
from typing import Optional, List, Tuple
from sqlalchemy import func, cast, Text
from sqlalchemy.orm import Session

from src.database.models import StockTranslation
from src.schemas.translation import (
    TranslationCreate,
    TranslationUpdate,
    BulkImportItem,
)

# ---------------------------------------------------------------------------
# Ticker format validation used by ensure_pending_stubs.
#
# Mirrors the regex logic in pipelines/libs/shared/src/shared/tickers.py so
# the backend independently rejects junk before it ever hits the DB.  The
# backend cannot import the pipelines shared lib, so the rules are replicated
# here.  Keep the two in sync when either changes.
# ---------------------------------------------------------------------------
# TW: 3-6 digits with optional trailing class letter (00878B, 00632R).
# Leading-zero guard: rejects "000000" — no real TW listing has 4+ leading zeros.
_STUB_TW_RE = re.compile(r"^(?!0{4,})\d{3,6}[A-Z]?$")
# US: 1-5 ASCII letters with optional .CLASS suffix (BRK.A, BRK.B).
_STUB_US_RE = re.compile(r"^[A-Z]{1,5}(?:\.[A-Z]{1,2})?$")
# Symbols that pass the regex but are NOT listed on TW or US exchanges.
_STUB_NON_TICKERS: frozenset[str] = frozenset({
    # private-company hallucinations
    "ANTHR", "ANTHROPIC", "OPENAI", "OAI", "SPACEX", "SPCX",
    "BYTEDANCE", "DEEPSEEK", "XAI", "GRK", "GROK", "STRIPE", "SHEIN",
    # Yangtze Memory — Chinese state-owned, not listed on TW/US
    "YMTC",
    # BNP Paribas — Euronext only, not TW/US
    "BNP",
    # payment brand, not a listed ticker
    "LINEPAY",
    # country / region abbreviations
    "US", "TW", "CN", "KR", "JP", "EU", "HK", "IN",
    "INDIA", "CHINA", "JAPAN", "KOREA",
    # index / benchmark codes
    "HSCEI", "OEX", "CRBRS", "TSE",
})


def _is_stub_candidate(bare: str) -> bool:
    """True if ``bare`` looks like a real TW or US exchange listing.

    Used by :meth:`TranslationService.ensure_pending_stubs` to reject junk
    strings (country names, index codes, private companies) before they are
    written to the DB as pending stubs.
    """
    return (
        bare not in _STUB_NON_TICKERS
        and bool(_STUB_TW_RE.match(bare) or _STUB_US_RE.match(bare))
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
    ("3363", "TW", "凌群", "上詮"),        # Browave; 凌群 is 2453 (Syscom)
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

    def reclassify_markets(self) -> int:
        """Fix the ``market`` of discovery-created rows that disagree with the ticker shape.

        Recomputes :func:`src.utils.market.infer_market` and updates ``market`` when it
        differs — e.g. a 6-digit Korean code like 000660 that on-ingest discovery once
        defaulted to TW moves to KR.

        Scoped to rows ``last_updated_by == 'ingest_discovery'`` ONLY. Authoritative seed
        rows (exchange crawl / FinMind / curated lists) set ``market`` from the source of
        truth and must NOT be second-guessed by the shape heuristic — TW has legitimate
        6-digit codes (TDRs, some ETFs/REITs) that ``infer_market`` would wrongly call KR.
        ``approved`` rows are excluded too, so a human market fix is never overwritten.

        Self-deactivating and idempotent: once a row matches its inferred market the
        update no longer fires, so re-running on every boot is a no-op. Guards the
        ``uq_ticker_market`` constraint by skipping a move that would collide with an
        existing (ticker, target-market) row. Returns the number of rows updated.
        """
        from src.utils.market import infer_market

        fixed = 0
        rows = (
            self.db.query(StockTranslation)
            .filter(
                StockTranslation.translation_status != "approved",
                StockTranslation.last_updated_by == "ingest_discovery",
            )
            .all()
        )
        for row in rows:
            target = infer_market(row.ticker)
            if target == row.market:
                continue
            target_row = self.get_by_ticker_market(row.ticker, target)
            if target_row is not None and target_row.id != row.id:
                # An authoritative row already occupies (ticker, target). If this
                # discovery stub is nameless, it's a superseded duplicate (e.g. the old
                # 000660/TW stub once the 000660/KR seed lands) — delete it. Otherwise
                # leave it for an admin to merge by hand.
                if not (row.name_en or "").strip() and not (row.name_zh_tw or "").strip():
                    try:
                        self.db.delete(row)
                        self.db.commit()
                        logger.info(
                            "reclassify_markets: deleted stale nameless stub %s/%s "
                            "(superseded by %s/%s)", row.ticker, row.market, row.ticker, target,
                        )
                        fixed += 1
                    except Exception as e:
                        logger.warning("reclassify_markets: delete %s failed: %s", row.ticker, e)
                        self.db.rollback()
                else:
                    logger.warning(
                        "reclassify_markets: %s %s->%s skipped (named target row exists)",
                        row.ticker, row.market, target,
                    )
                continue
            old = row.market
            row.market = target
            row.last_updated_by = "market_reclassify"
            try:
                self.db.commit()
                logger.info("reclassify_markets: %s %s -> %s", row.ticker, old, target)
                fixed += 1
            except Exception as e:
                logger.warning("reclassify_markets: commit %s failed: %s", row.ticker, e)
                self.db.rollback()
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

        Market inference delegates to :func:`src.utils.market.infer_market` so the
        backend, the pipeline, and the frontend agree on one rule:
        - 3-5 digit codes (with optional class letter, 00878B/00632R) → TW
        - 6-digit codes (005930 Samsung, 000660 SK Hynix) → KR
        - otherwise alphabetic → US
        KR/HK stubs aren't auto-named by FinMind/Massive (out of their coverage); the
        authoritative seed (foreign_stocks / FinMind) supplies their names instead.
        """
        from src.utils.market import infer_market

        # Collect distinct bare symbols with an inferred market.
        cleaned: dict[str, str] = {}
        for s in symbols:
            if not s or not s.strip():
                continue
            bare = s.strip().upper().split(".")[0]
            if not bare:
                continue
            # Reject junk strings (country names, index codes, private companies)
            # before they reach the DB.  Real listings must pass _is_stub_candidate.
            if not _is_stub_candidate(bare):
                logger.debug("ensure_pending_stubs: skipping non-ticker %r", bare)
                continue
            cleaned.setdefault(bare, infer_market(bare))
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
        if update_data.get("market"):
            target_market = update_data["market"].upper()
            update_data["market"] = target_market
            # Guard the uq_ticker_market constraint: refuse a move that collides with
            # another existing (ticker, market) row.
            if target_market != translation.market:
                clash = self.get_by_ticker_market(translation.ticker, target_market)
                if clash is not None and clash.id != translation.id:
                    raise ValueError(
                        f"{translation.ticker}/{target_market} already exists"
                    )
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
        Seed stock translations from a list of
        (ticker, market, name_en, name_zh_tw, status[, aliases]) tuples.
        - Inserts rows that don't exist yet (with aliases if the 6th element is present).
        - Fills in name_en/name_zh_tw for existing stub rows (name_en is NULL and status
          is not "approved"), without downgrading approved rows; seeds aliases onto a row
          that has none yet (never clobbers curated aliases).
        - Does not write brand_color; the stock_translations table is the source of truth
          for colors and is maintained through the admin/bulk endpoints.
        Returns count of rows inserted or updated.
        """
        affected = 0
        for entry in entries:
            ticker, market, name_en, name_zh_tw, status = entry[:5]
            aliases = entry[5] if len(entry) > 5 else None
            existing = self.get_by_ticker_market(ticker, market)
            if existing is None:
                data = TranslationCreate(
                    ticker=ticker,
                    market=market,
                    name_en=name_en,
                    name_zh_tw=name_zh_tw,
                    translation_status=status,
                    aliases=aliases,
                )
                self.create(data, "startup_backfill")
                affected += 1
            elif existing.name_en is None and existing.translation_status != "approved":
                # Populate empty auto-created stubs without touching approved rows
                existing.name_en = name_en
                existing.name_zh_tw = name_zh_tw
                existing.translation_status = status
                # Seed aliases only when the row carries none yet (don't clobber curation).
                if aliases and not existing.aliases:
                    existing.aliases = _normalize_aliases(aliases)
                existing.last_updated_by = "startup_backfill"
                self.db.commit()
                affected += 1
            elif aliases and not existing.aliases:
                # Row already has a name but no aliases — seed them without other changes.
                existing.aliases = _normalize_aliases(aliases)
                existing.last_updated_by = "startup_backfill"
                self.db.commit()
                affected += 1
        return affected

    def seed_tw_from_finmind(self, finmind_service=None) -> int:
        """Seed TW translations from the full FinMind TaiwanStockInfo registry.

        Pulls the cached TaiwanStockInfo table (one in-process call, not per-ticker) and,
        for each listing, inserts a new ``auto`` TW row or fills an existing name-less
        stub's zh name. Makes the table authoritative for TW market+name *before* any
        episode mentions a ticker, shrinking on-ingest discovery to a linker.

        Clobber-safe and cheap on repeat: a row that already carries a ``name_zh_tw`` (or
        is ``approved``) is skipped without a write, so re-running on every boot only
        commits genuinely-new or still-empty rows.

        ``finmind_service`` is injectable for tests; constructed lazily otherwise so a
        missing API key degrades to a no-op instead of breaking the caller.
        Returns the number of rows created or filled.
        """
        if finmind_service is None:
            try:
                from src.services.finmind_service import FinMindAPIService

                finmind_service = FinMindAPIService()
            except Exception as e:
                logger.warning("seed_tw_from_finmind: FinMind unavailable: %s", e)
                return 0

        try:
            listings = finmind_service.list_all_tw_stocks()
        except Exception as e:
            logger.warning("seed_tw_from_finmind: listing fetch failed: %s", e)
            return 0

        affected = 0
        for ticker, name_zh_tw, _industry in listings:
            ticker = (ticker or "").strip().upper()
            name_zh_tw = (name_zh_tw or "").strip()
            if not ticker or not name_zh_tw:
                continue
            existing = self.get_by_ticker_market(ticker, "TW")
            try:
                if existing is None:
                    self.create(
                        TranslationCreate(
                            ticker=ticker,
                            market="TW",
                            name_zh_tw=name_zh_tw,
                            translation_status="auto",
                        ),
                        updated_by="finmind_seed",
                    )
                    affected += 1
                elif (
                    not (existing.name_zh_tw or "").strip()
                    and existing.translation_status != "approved"
                ):
                    # Fill a name-less stub without touching approved rows or curated names.
                    existing.name_zh_tw = name_zh_tw
                    existing.translation_status = "auto"
                    existing.last_updated_by = "finmind_seed"
                    self.db.commit()
                    affected += 1
                # else: row already has a zh name (or is approved) — leave it.
            except Exception as e:
                logger.debug("seed_tw_from_finmind: skip %s: %s", ticker, e)
                self.db.rollback()
        if affected:
            logger.info("seed_tw_from_finmind: seeded/filled %d TW listing(s)", affected)
        return affected

    def seed_aliases(self, entries: list[tuple]) -> int:
        """Seed curated aliases onto existing rows from (ticker, market, aliases) tuples.

        Clobber-safe: only writes when the matching row exists and carries no aliases yet,
        so an admin-curated alias list (e.g. SPCX -> "SpaceX") is never overwritten and
        re-running on every boot is a no-op once seeded. Returns the number of rows seeded.
        """
        affected = 0
        for ticker, market, aliases in entries:
            row = self.get_by_ticker_market(ticker, market)
            if row is None or row.aliases:
                continue
            cleaned = _normalize_aliases(aliases)
            if not cleaned:
                continue
            row.aliases = cleaned
            row.last_updated_by = "alias_seed"
            try:
                self.db.commit()
                affected += 1
            except Exception as e:
                logger.warning("seed_aliases: commit %s/%s failed: %s", ticker, market, e)
                self.db.rollback()
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
