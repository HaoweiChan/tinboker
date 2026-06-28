"""Sector/theme exposure resolver for podcast content.

Runtime extraction is intentionally offline: this module reads the compiled
``sector_and_theme_universe.json`` artifact and never calls FinMind, ETF issuer
endpoints, Tavily, or scraping code. Maintenance jobs refresh the artifact.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Iterable

from shared.platform_client import fetch_sectors_universe

_CJK_RE = re.compile(r"[\u3400-\u9fff]")
_LATIN_WORD_RE = re.compile(r"[a-z0-9][a-z0-9+.-]{1,12}")
_UNRESOLVED_UPPER_RE = re.compile(r"\b[A-Z][A-Z0-9+.-]{1,10}\b")
DEFAULT_MAX_TICKERS = 10

# Common macro/finance/general acronyms that the uppercase scanner would otherwise
# surface as "emerging market concepts". They are not curation candidates, so we
# drop them to keep ``unresolved_market_trends`` (written to every episode doc)
# low-noise. Values are normalized (lower-cased) to match ``normalize_text``.
_UNRESOLVED_STOPWORDS: frozenset[str] = frozenset({
    "ceo", "cfo", "coo", "cto", "cio", "vp", "ir", "vc", "pe", "pb", "ps", "eps",
    "roe", "roa", "roi", "gdp", "cpi", "ppi", "pce", "ism", "pmi", "fomc", "fed",
    "ecb", "boj", "imf", "usd", "twd", "jpy", "eur", "rmb", "cny", "krw", "etf",
    "ipo", "spo", "m&a", "esg", "yoy", "qoq", "mom", "ttm", "q1", "q2", "q3", "q4",
    "h1", "h2", "1h", "2h", "fy", "ai", "ev", "iot", "5g", "6g", "pc", "tv", "us",
    "uk", "eu", "ok", "ceo's", "api", "app", "ui", "ux", "faq", "diy", "b2b", "b2c",
})


@dataclass(frozen=True)
class ExposureMatch:
    exposure: dict[str, Any]
    alias: str
    normalized_alias: str
    start: int
    end: int


def normalize_text(text: str) -> str:
    """Normalize Chinese/English market phrases for matching.

    English is lower-cased, whitespace/punctuation is collapsed, and simple
    singular/plural variants are handled in the alias index.
    """
    s = unicodedata.normalize("NFKC", str(text or "")).lower()
    s = re.sub(r"[_/\\-]+", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def _english_variants(alias: str) -> set[str]:
    norm = normalize_text(alias)
    out = {norm} if norm else set()
    if not norm or _CJK_RE.search(norm):
        return out
    words = norm.split()
    last = words[-1]
    variants = set(out)
    endings = []
    if last.endswith("ies") and len(last) > 3:
        endings.append(last[:-3] + "y")
    if last.endswith("es") and len(last) > 2:
        endings.append(last[:-2])
    if last.endswith("s") and len(last) > 1:
        endings.append(last[:-1])
    if not last.endswith("s"):
        endings.append(last + "s")
    for replacement in endings:
        if replacement:
            variants.add(" ".join([*words[:-1], replacement]))
    return variants


def _member_sort_key(member: dict[str, Any]) -> tuple[int, float, float, str]:
    source = str(member.get("source") or "")
    curated_rank = int(member.get("rank") or 1_000_000)
    if source == "curated":
        return (0, curated_rank, 0, str(member.get("ticker") or ""))
    market_cap_rank = member.get("market_cap_rank")
    liquidity_rank = member.get("liquidity_rank")
    rank_value = float(market_cap_rank or liquidity_rank or curated_rank or 1_000_000)
    return (1, rank_value, float(curated_rank), str(member.get("ticker") or ""))


def _clean_member(member: dict[str, Any]) -> dict[str, Any]:
    out = {
        "ticker": str(member.get("ticker") or "").upper(),
        "name": str(member.get("name") or member.get("ticker") or ""),
        "market": str(member.get("market") or ""),
        "source": str(member.get("source") or "compiled"),
    }
    if member.get("name_en"):
        out["name_en"] = str(member["name_en"])
    if member.get("reason"):
        out["reason"] = str(member["reason"])
    return out


@lru_cache(maxsize=1)
def _universe() -> dict[str, Any]:
    universe_data = fetch_sectors_universe()
    if not universe_data:
        from shared.sectors_seed_backup import SECTORS_SEED
        universe_data = {
            "max_tickers": DEFAULT_MAX_TICKERS,
            "exposures": SECTORS_SEED,
        }
    max_tickers = int(universe_data.get("max_tickers") or DEFAULT_MAX_TICKERS)
    exposures = []
    for item in universe_data.get("exposures") or []:
        copied = dict(item)
        members = [m for m in copied.get("members") or [] if isinstance(m, dict)]
        copied["members"] = sorted(members, key=_member_sort_key)
        exposures.append(copied)
    return {"max_tickers": max_tickers, "exposures": exposures}


@lru_cache(maxsize=1)
def _alias_index() -> list[tuple[str, str, dict[str, Any]]]:
    """Return ``[(normalized_alias, raw_alias, exposure), ...]`` longest first.

    Multiple exposures may share one alias; all are retained, which gives the
    many-to-many alias behavior required by the extraction plan.
    """
    rows: list[tuple[str, str, dict[str, Any]]] = []
    for exposure in _universe()["exposures"]:
        aliases = exposure.get("aliases") or []
        for alias in aliases:
            for variant in _english_variants(str(alias)):
                rows.append((variant, str(alias), exposure))
    rows.sort(key=lambda r: (len(r[0]), len(r[1])), reverse=True)
    return rows


def _overlaps(span: tuple[int, int], spans: Iterable[tuple[int, int]]) -> bool:
    start, end = span
    return any(start < used_end and end > used_start for used_start, used_end in spans)


def find_exposure_matches(text: str) -> list[ExposureMatch]:
    """Find sector/theme aliases using longest-match-first string matching."""
    normalized = normalize_text(text)
    if not normalized:
        return []
    used_spans: list[tuple[int, int]] = []
    matches: list[ExposureMatch] = []
    for norm_alias, raw_alias, exposure in _alias_index():
        if not norm_alias:
            continue
        if _CJK_RE.search(norm_alias):
            pattern = re.escape(norm_alias)
        else:
            pattern = rf"(?<![a-z0-9]){re.escape(norm_alias)}(?![a-z0-9])"
        for match in re.finditer(pattern, normalized):
            span = match.span()
            if _overlaps(span, used_spans):
                continue
            used_spans.append(span)
            matches.append(
                ExposureMatch(
                    exposure=exposure,
                    alias=raw_alias,
                    normalized_alias=norm_alias,
                    start=span[0],
                    end=span[1],
                )
            )
            break
    matches.sort(key=lambda m: (m.start, m.end))
    return matches


def normalize_exposure_id(exposure_id: str | None) -> str:
    """Canonical exposure id: themes and sectors share one ``sector_`` namespace.

    Curated themes were historically keyed ``theme_<id>`` and official sectors
    ``sector_<id>`` — but they are one concept ("a sector") to the user, so both
    collapse to ``sector_<id>``. Apply at every read/display boundary so that
    pre-migration episode data still keyed ``theme_<id>`` reconciles with the
    unified universe without a hard dependency on the backfill having run.
    """
    s = str(exposure_id or "")
    return "sector_" + s[len("theme_"):] if s.startswith("theme_") else s


def _exposure_payload(match: ExposureMatch, *, max_tickers: int | None = None) -> dict[str, Any]:
    exposure = match.exposure
    cap = max_tickers or _universe()["max_tickers"]
    members = exposure.get("members") or []
    return {
        "exposure_id": normalize_exposure_id(exposure.get("exposure_id")),
        "exposure_type": exposure.get("exposure_type"),
        "display_name": exposure.get("display_name"),
        "mention_text": match.alias,
        "confidence": 1.0,
        "icon_id": exposure.get("icon_id"),
        "color_hex": exposure.get("color_hex"),
        "resolved_tickers": [_clean_member(m) for m in members[:cap]],
        "total_matches": len(members),
    }


def resolve_text(text: str, *, max_tickers: int | None = None) -> dict[str, list[dict[str, Any]]]:
    """Resolve known exposures and emit credible unresolved market trends."""
    matches = find_exposure_matches(text)
    exposures: list[dict[str, Any]] = []
    seen: set[str] = set()
    for match in matches:
        payload = _exposure_payload(match, max_tickers=max_tickers)
        exposure_id = str(payload.get("exposure_id") or "")
        if exposure_id and exposure_id not in seen:
            seen.add(exposure_id)
            exposures.append(payload)
    unresolved = find_unresolved_market_trends(text, matches)
    return {"sector_exposures": exposures, "unresolved_market_trends": unresolved}


def find_unresolved_market_trends(
    text: str,
    matches: Iterable[ExposureMatch] | None = None,
) -> list[dict[str, Any]]:
    """Best-effort unresolved trend candidates for demand-driven curation.

    This is deliberately conservative: exact deterministic aliases are resolved
    elsewhere with confidence 1.0, while unmapped uppercase market concepts like
    ``CPO`` are retained at lower confidence for the background aggregator.
    """
    normalized = normalize_text(text)
    matched_aliases = {m.normalized_alias for m in (matches or [])}
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for match in _UNRESOLVED_UPPER_RE.finditer(str(text or "")):
        raw = match.group(0)
        norm = normalize_text(raw)
        if (
            norm in matched_aliases
            or any(norm and norm in alias for alias in matched_aliases)
            or norm in seen
        ):
            continue
        # Avoid common ticker-like one-offs; curation triggers only after recurrence.
        if len(norm) < 2:
            continue
        # Drop macro/finance/general acronyms — they are noise, not market concepts.
        if norm in _UNRESOLVED_STOPWORDS:
            continue
        seen.add(norm)
        out.append({
            "mention_text": raw,
            "normalized_text": norm,
            "context": str(text or "")[:240],
            "confidence": 0.74,
        })
    # English lowercase phrases are not lifted here; they need recurrence and/or
    # agentic curation from unresolved uppercase concepts to stay low-noise.
    _ = normalized
    return out


def flatten_exposure_ids(sector_exposures: Iterable[dict[str, Any]]) -> dict[str, list[str]]:
    """Flat, Firestore-queryable id arrays for an episode's exposures."""
    exposure_ids: set[str] = set()
    for item in sector_exposures or []:
        if item.get("exposure_id"):
            exposure_ids.add(str(item["exposure_id"]))
    return {
        "sector_exposure_ids": sorted(exposure_ids),
    }


def flatten_unresolved_trend_ids(unresolved: Iterable[dict[str, Any]]) -> list[str]:
    ids = {
        str(item.get("normalized_text") or "").strip()
        for item in (unresolved or [])
        if item.get("normalized_text")
    }
    return sorted(i for i in ids if i)


def aggregate_unresolved_trends(
    rows: Iterable[dict[str, Any]],
    *,
    threshold: int,
) -> list[dict[str, Any]]:
    counts: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = str(row.get("normalized_text") or "").strip()
        if not key:
            continue
        bucket = counts.setdefault(key, {"normalized_text": key, "count": 0, "examples": []})
        bucket["count"] += 1
        if len(bucket["examples"]) < 5:
            bucket["examples"].append(row)
    return sorted(
        [v for v in counts.values() if v["count"] >= threshold],
        key=lambda item: (-int(item["count"]), str(item["normalized_text"])),
    )


def resolve_clustered_events(
    events: Iterable[dict[str, Any]],
    *,
    max_tickers: int | None = None,
) -> dict[str, Any]:
    sector_exposures: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    seen_exposures: set[tuple[str, int, int]] = set()
    seen_unresolved: set[tuple[str, int]] = set()

    for event in events or []:
        sentences = [s for s in (event.get("sentences") or []) if isinstance(s, dict)]
        text_parts = [str(event.get("section_topic") or "")]
        text_parts.extend(str(s.get("content") or "") for s in sentences)
        text = " ".join(part for part in text_parts if part)
        if not text:
            continue

        sentence_indices = [s.get("index") for s in sentences if isinstance(s.get("index"), int)]
        start_index = min(sentence_indices) if sentence_indices else None
        end_index = max(sentence_indices) if sentence_indices else None
        start_time = event.get("start")
        end_time = event.get("end")

        resolved = resolve_text(text, max_tickers=max_tickers)
        for item in resolved["sector_exposures"]:
            keyed = (str(item.get("exposure_id")), int(start_time or 0), int(end_time or 0))
            if keyed in seen_exposures:
                continue
            seen_exposures.add(keyed)
            item = dict(item)
            item.update({
                "start_index": start_index,
                "end_index": end_index,
                "start_time": start_time,
                "end_time": end_time,
            })
            sector_exposures.append(item)
        for item in resolved["unresolved_market_trends"]:
            keyed = (str(item.get("normalized_text")), int(start_time or 0))
            if keyed in seen_unresolved:
                continue
            seen_unresolved.add(keyed)
            item = dict(item)
            item["start_time"] = start_time
            unresolved.append(item)

    flat = flatten_exposure_ids(sector_exposures)
    return {
        "sector_exposures": sector_exposures,
        "unresolved_market_trends": unresolved,
        **flat,
        "unresolved_market_trend_ids": flatten_unresolved_trend_ids(unresolved),
    }
