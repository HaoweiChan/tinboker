"""Ticker registry — canonical symbols + display metadata (zh name, market, sector).

The registry data lives in ``shared/data/tickers.json``. This module loads it once and exposes:

- :func:`canonical_symbol` — normalize any seen form (e.g. ``"2330.TW"``, ``"2330 tw"``) to the
  canonical symbol (``"2330"``); unknown symbols return ``raw.strip().upper()`` unchanged.
- :func:`lookup_ticker` — return :class:`TickerInfo` for a symbol/alias, or ``None`` if not in the
  registry.

Consumer: ``shared.wiki_builder.ingest_episode`` (to set real names + market on entity pages).
Extend ``tickers.json`` freely.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

_DATA_FILE = Path(__file__).resolve().parent / "data" / "tickers.json"


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


@lru_cache(maxsize=1)
def _index() -> dict[str, TickerInfo]:
    """Flat lookup index: every canonical symbol, alias, and normalized form -> TickerInfo."""
    if not _DATA_FILE.exists():
        return {}
    raw = json.loads(_DATA_FILE.read_text(encoding="utf-8"))
    out: dict[str, TickerInfo] = {}
    for symbol, meta in (raw.get("tickers") or {}).items():
        aliases = meta.get("aliases", []) or []
        info = TickerInfo(
            symbol=symbol,
            name=meta.get("name", symbol),
            name_en=meta.get("name_en", symbol),
            market=meta.get("market", ""),
            sector=meta.get("sector", ""),
            type=meta.get("type", "company"),
            aliases=tuple(aliases),
        )
        keys = {symbol, _norm(symbol), *aliases, *(_norm(a) for a in aliases)}
        for k in keys:
            if k:
                out.setdefault(k, info)
    return out


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


# A real listing is a Taiwan number (4-6 digits, optional trailing letter for ETFs
# like 00878B) or a US-style symbol (1-5 letters, optional .CLASS). Everything else —
# CJK category names ("被動元件"), phrases ("EDGE COMPUTING相關類股"), and over-length
# words ("OPENAI", "ANTHROPIC") — is the LLM mislabelling a sector or private company.
_TW_RE = re.compile(r"^\d{3,6}[A-Z]?$")
_US_RE = re.compile(r"^[A-Z]{1,5}(?:\.[A-Z]{1,2})?$")

# Format-valid but NOT listed: symbols the LLM invents for well-known private
# companies. (SPCE is intentionally absent — it is a real ticker, Virgin Galactic;
# the model misusing it for SpaceX is a prompt problem, not a symbol-validity one.)
_NON_TICKERS = frozenset({
    "ANTHR", "ANTHROPIC", "OPENAI", "OAI", "SPACEX", "SPCX",
    "BYTEDANCE", "DEEPSEEK", "XAI", "GRK", "GROK", "STRIPE", "SHEIN",
})


def is_valid_ticker_symbol(raw: object) -> bool:
    """True if ``raw`` is a plausible real exchange symbol.

    Registry/alias members are always valid (the registry is curated but small, so
    it is a known-good allowlist, NOT an exhaustive one). Anything else must match a
    TW-number or US-letter shape and not be a known private-company hallucination.
    """
    if not isinstance(raw, str):
        return False
    s = raw.strip().upper()
    if not s or s in _NON_TICKERS:
        return False
    if lookup_ticker(s) is not None:
        return True
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
