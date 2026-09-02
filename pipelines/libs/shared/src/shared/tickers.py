"""Ticker registry — canonical symbols + display metadata (zh name, market, sector).

The registry data lives in ``shared/data/tickers.json``. This module loads it once and exposes:

- :func:`canonical_symbol` — normalize any seen form (e.g. ``"2330.TW"``, ``"2330 tw"``) to the
  canonical symbol (``"2330"``); unknown symbols return ``raw.strip().upper()`` unchanged.
- :func:`lookup_ticker` — return :class:`TickerInfo` for a symbol/alias, or ``None`` if not in the
  registry.
- :func:`prime_tickers` — pull the platform's curated zh-TW names for a specific symbol list
  (the ``/translations/batch`` table) and merge them into the index before rendering.

Consumer: ``shared.wiki_builder.ingest_episode`` (to set real names + market on entity pages).
Extend ``tickers.json`` freely.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache

from shared.platform_client import fetch_translation_aliases, fetch_translations_batch


@dataclass(frozen=True)
class TickerInfo:
    symbol: str          # canonical symbol (e.g. "2330", "NVDA")
    name: str            # display name (Traditional Chinese where available)
    name_en: str
    market: str          # "TW" | "US" | "KR" | "EU" | ...
    sector: str
    type: str            # "company" | "etf" | "index" | ...
    aliases: tuple[str, ...] = ()  # curated alias seed (zh/en variants, old symbols)


def _norm(raw: str) -> str:
    """Loose normalization used for index lookups."""
    s = (raw or "").strip().upper().replace(" ", "")
    # drop a market suffix like ".TW" / ".KS" / ".HK" / ":TW"
    for sep in (".", ":"):
        if sep in s:
            head, tail = s.rsplit(sep, 1)
            if tail.isalpha() and 1 <= len(tail) <= 3:
                s = head
                break
    return s


# Symbols already asked of /translations/batch this process — one round trip per
# symbol, and a miss stays a miss (no retry storm on an episode full of junk codes).
_PRIMED: set[str] = set()


def _register(out: dict[str, TickerInfo], info: TickerInfo, *, override: bool) -> None:
    """Index ``info`` under its symbol, aliases and normalized forms."""
    keys = {info.symbol, _norm(info.symbol), *info.aliases, *(_norm(a) for a in info.aliases)}
    for k in keys:
        if not k:
            continue
        if override:
            out[k] = info
        else:
            out.setdefault(k, info)


def _info_from_translation(item: dict) -> TickerInfo | None:
    """Build a :class:`TickerInfo` from one ``/api/stocks/translations`` row."""
    symbol = (item.get("ticker") or "").strip().upper()
    if not symbol:
        return None
    aliases = item.get("aliases") or []
    return TickerInfo(
        symbol=symbol,
        name=item.get("name_zh_tw") or item.get("name_en") or symbol,
        name_en=item.get("name_en") or item.get("name_zh_tw") or symbol,
        market=item.get("market", ""),
        sector="",
        type="company",
        aliases=tuple(aliases),
    )


@lru_cache(maxsize=1)
def _index() -> dict[str, TickerInfo]:
    """Flat lookup index: every canonical symbol, alias, and normalized form -> TickerInfo.

    The local seed is the floor and the platform rows are the overlay. Merging rather
    than choosing matters: ``/translations/aliases`` only returns rows that carry a
    curated alias — a few dozen — so treating a successful-but-thin response as the
    whole registry left every TW listing unresolved, and cards rendered a bare "3037"
    where the name belonged.
    """
    out: dict[str, TickerInfo] = {}

    # 1. Local seed backup — broad, offline, possibly stale.
    from shared.tickers_seed_backup import TICKERS_SEED
    for symbol, meta in TICKERS_SEED.items():
        aliases = meta.get("aliases", []) or []
        _register(out, TickerInfo(
            symbol=symbol,
            name=meta.get("name", symbol),
            name_en=meta.get("name_en", symbol),
            market=meta.get("market", ""),
            sector=meta.get("sector", ""),
            type=meta.get("type", "company"),
            aliases=tuple(aliases),
        ), override=False)

    # 2. Platform rows win where they exist — that table is the operator-curated one.
    for item in fetch_translation_aliases() or []:
        info = _info_from_translation(item)
        if info:
            _register(out, info, override=True)
    return out


def prime_tickers(symbols: Iterable[str]) -> None:
    """Merge the platform's translations for ``symbols`` into the lookup index.

    ``/translations/aliases`` carries only alias-bearing rows, so a symbol we are
    about to render (a card, a wiki page) may resolve to nothing but itself. This
    asks the translations table for exactly the symbols in hand and folds the answer
    into the shared index, so ``lookup_ticker`` returns the operator-curated zh-TW
    name instead of the seed's (or the raw code).

    Best-effort: a missing base URL or an unreachable platform leaves the index as-is.
    """
    wanted = {s.strip().upper() for s in symbols if str(s).strip()}
    if not wanted:
        return
    idx = _index()
    missing = sorted(w for w in wanted if w not in _PRIMED)
    if not missing:
        return
    _PRIMED.update(missing)
    # Group first: a symbol usually comes back once, and that row is authoritative.
    # Only a genuine collision needs a tie-break — and the tie-break must not fire on
    # single rows, or it starts overruling the table with a guess. 000660 (SK Hynix)
    # is the case that proves it: Korean listings are numeric like Taiwanese ones, so
    # "numeric ⇒ TW" mislabels every KR row it touches.
    by_symbol: dict[str, list[TickerInfo]] = {}
    for item in fetch_translations_batch(missing) or []:
        info = _info_from_translation(item)
        if info:
            by_symbol.setdefault(info.symbol, []).append(info)

    for symbol, rows in by_symbol.items():
        if len(rows) > 1:
            # The table carries the same code in two markets — real dual listings, but
            # also stubs that `GET /translations/{t}?market=` auto-creates on a wrong
            # guess (000660 and 005930 are Korean and each has a phantom TW row).
            # The registry we already hold is the better arbiter than any shape rule:
            # numeric means Taiwan *or* Korea, so guessing from digits mislabels KR.
            known = idx.get(symbol)
            preferred = (known.market or "").upper() if known else ""
            if not preferred:
                preferred = "TW" if symbol.rstrip("ABC").isdigit() else "US"
            rows = [r for r in rows if (r.market or "").upper() == preferred] or rows
        _register(idx, rows[0], override=True)


def lookup_ticker(raw: str) -> TickerInfo | None:
    """Return registry metadata for a ticker symbol or alias, else ``None``."""
    if not raw:
        return None
    idx = _index()
    return idx.get(raw.strip()) or idx.get(raw.strip().upper()) or idx.get(_norm(raw))


def canonical_symbol(raw: str) -> str:
    """Canonical symbol for a seen form; unknowns return the trimmed/upper-cased input."""
    info = lookup_ticker(raw)
    return info.symbol if info else (raw or "").strip().upper()


# A real listing is a Taiwan / Korea number (3-6 digits, optional trailing class letter
# for ETFs like 00878B; Korean codes such as 005930 / 000660 share this numeric shape)
# or a US-style symbol (2-5 letters, optional .CLASS). Everything else — CJK category
# names ("被動元件"), phrases ("EDGE COMPUTING相關類股"), and over-length words ("OPENAI",
# "ANTHROPIC") — is the LLM mislabelling a sector or private company.
#
# The letter floor is 2, not 1: a lone capital ("N") is almost always a transcription
# fragment / list marker, never an equity, and renders a priceless junk pill on the UI.
# A genuine single-letter listing (F, T, V) must be added to the registry, which is
# consulted before this format fallback — registry membership is the escape hatch.
# _TW_RE: leading-zero guard (``(?!0{4,})``) rejects codes like "000000" (no TW
# listing has four or more leading zeros) while keeping real ETF codes like
# 00878 / 006208.
_TW_RE = re.compile(r"^(?!0{4,})\d{3,6}[A-Z]?$")
_US_RE = re.compile(r"^[A-Z]{2,5}(?:\.[A-Z]{1,2})?$")

# Embedded whitespace or brackets ⇒ a name+ticker string ("台積電 (TSMC)") or a
# multi-word asset-class label ("US HY BOND ETF"), never a bare exchange symbol.
_BAD_CHARS_RE = re.compile(r"[\s()\[\]{}]")

# Registry ``type`` values that denote a *tradeable* security with price data on
# our feeds. The registry also carries indices and private companies (the wiki
# builder needs their display metadata) — those are valid entities but NOT
# scoreboard-eligible tickers, so they must fail symbol validation.
_TRADEABLE_TYPES = frozenset({"company", "etf", "adr", "reit"})

# Market indices / benchmarks the LLM emits as if they were tickers. They render
# as a permanent "—" on the scoreboard and pollute trending. (Those already in the
# registry — SPX/DJI/IXIC/SOX/NDX — are caught by the type check above; this set
# covers the ones that are NOT in the registry but still match the US shape.)
# NB: "MSCI" is also a real equity (NYSE:MSCI), but in podcast context it almost
# always means the index family, so we reject it here as observed feed junk.
_INDEX_SYMBOLS = frozenset({
    "VIX", "VXN", "RUT", "RUI", "RUA", "NBI", "MSCI",
    "DJIA", "GSPC", "COMP", "INX", "TNX", "MID", "OEX",
})

# Bare asset-class / instrument words that happen to match the US letter shape.
_NON_SYMBOL_WORDS = frozenset({
    "ETF", "ETN", "REIT", "REITS", "BOND", "BONDS", "FUND", "FUNDS",
    "INDEX", "FOREX", "CRYPTO",
})

# Format-valid (they fit the US-letter shape) but NOT exchange listings. The LLM drops
# these into the "ticker" slot and the shape check alone would wave them through:
#   1. Symbols it invents for well-known PRIVATE companies, or wrong/observed-junk
#      symbols with no price data on our feeds ("TSMC" for TSM/2330, "SPACE" for SpaceX).
#   2. PEOPLE — central bankers / officials / executives / investors named by surname
#      or nickname. "JPOW" (Jerome Powell) is the recurring offender; an abbreviation
#      like it looks exactly like a 4-letter ticker, so only a denylist catches it.
#   3. MACRO / index / policy abbreviations the prompt already says to skip but that
#      still slip through. Kept deliberately small and unambiguous to avoid colliding
#      with a real ticker; the prompt is the first line of defense for the long tail.
# (SPCE is intentionally absent — it is a real ticker, Virgin Galactic; the model
# misusing it for SpaceX is a prompt problem, not a symbol-validity one.)
_NON_TICKERS = frozenset({
    # Private companies / wrong-or-junk symbols with no price data.
    # (SPCX/SPACEX removed — SpaceX IPO'd on Nasdaq as SPCX 2026-06; it is now a real,
    # priced listing in the registry as type=company.)
    "ANTHR", "ANTHROPIC", "OPENAI", "OAI", "SPACE",
    "BYTEDANCE", "DEEPSEEK", "XAI", "GRK", "GROK", "STRIPE", "SHEIN",
    "TSMC", "WD", "GIGA", "ASE",
    # People — surnames / nicknames (the >5-letter ones are already rejected by the
    # length rule; listed for intent and in case the format floor ever loosens).
    "JPOW", "POWELL", "YELLEN", "BERNANKE", "GREENSPAN", "LAGARDE",
    "MUSK", "BUFFETT", "DIMON", "TRUMP", "BIDEN",
    # Macro / index / policy — unambiguous non-equities.
    "FED", "FOMC", "ECB", "BOJ", "PBOC", "VIX", "DXY", "LIBOR", "SOFR",
    # Country / region abbreviations the LLM emits as ticker symbols (most are
    # 2 letters and would otherwise pass the US-letter shape).
    "US", "TW", "CN", "KR", "JP", "EU", "HK", "IN",
    "INDIA", "CHINA", "JAPAN", "KOREA",
    # Foreign / unlisted-on-our-feeds companies that pass the US-letter shape:
    # YMTC (Yangtze Memory, PRC state-owned), BNP (BNP Paribas, Euronext),
    # LINEPAY (payment brand, unlisted).
    "YMTC", "BNP", "LINEPAY",
    # Additional index / benchmark codes (HSCEI, Taiwan/Tokyo exchange shorthands).
    "HSCEI", "CRBRS", "TSE",
})


def is_valid_ticker_symbol(raw: object) -> bool:
    """True if ``raw`` is a plausible real, *tradeable* exchange symbol.

    Rejects, in order: non-strings; name+ticker / multi-word strings (spaces or
    brackets); known index symbols, asset-class words, and private-company
    hallucinations. Registry members are valid only when their ``type`` is
    tradeable (the registry also stores indices/private cos for display
    metadata). Anything left must match the TW-number or US-letter shape.
    """
    if not isinstance(raw, str):
        return False
    s = raw.strip().upper()
    if not s or _BAD_CHARS_RE.search(s):
        return False
    if s in _NON_TICKERS or s in _INDEX_SYMBOLS or s in _NON_SYMBOL_WORDS:
        return False
    info = lookup_ticker(s)
    if info is not None:
        return info.type in _TRADEABLE_TYPES
    return bool(_TW_RE.match(s) or _US_RE.match(s))


def valid_tickers(symbols: object) -> list[str]:
    """Filter an iterable of symbols to valid, canonical, de-duplicated tickers."""
    if not symbols:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for s in symbols:
        if is_valid_ticker_symbol(s):
            c = canonical_symbol(s)  # type: ignore[arg-type]
            if c not in seen:
                seen.add(c)
                out.append(c)
    return out


@lru_cache(maxsize=1)
def all_ticker_infos() -> tuple[TickerInfo, ...]:
    """Every distinct ticker in the registry — one :class:`TickerInfo` per symbol.

    Used by the news pipeline to seed its deterministic alias dictionary.
    """
    seen: dict[str, TickerInfo] = {}
    for info in _index().values():
        seen.setdefault(info.symbol, info)
    return tuple(seen.values())
