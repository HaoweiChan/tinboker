"""In-memory ``alias → canonical entity`` index.

Built once per ingest run from two sources (the design plan's "alias resolution
location: both"):

1. the curated **ticker registry** seed (``shared/data/tickers.json``), and
2. the live **entity-page ``frontmatter.aliases``** store — a one-time scan of
   the wiki's entity pages.

This is the only place "TSMC = 台積電 = 2330" is reconciled. It is the cheap
deterministic dictionary the dict-prepass and L1 resolution consult before any
LLM call.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from shared.tickers import all_ticker_infos
from shared.wiki_builder.repository import WikiRepository
from shared.wiki_builder.slugify import ticker_slug

_CJK_RE = re.compile(r"[㐀-鿿]")
_MIN_ALIAS_LEN = 2


def _norm(text: str) -> str:
    return unicodedata.normalize("NFKC", str(text or "")).strip().lower()


def _has_cjk(text: str) -> bool:
    return bool(_CJK_RE.search(text))


@dataclass
class ResolvedEntity:
    """A canonical entity the news pipeline can attach claims/mentions to."""

    slug: str
    name: str
    type: str = "company"
    symbol: str | None = None
    market: str | None = None
    sector: str | None = None
    new_aliases: set[str] = field(default_factory=set)

    def to_ingest_dict(self) -> dict:
        """Shape expected by ``wiki_builder.ingest_news_article``'s ``entities``."""
        out: dict = {"slug": self.slug, "name": self.name, "type": self.type}
        if self.symbol:
            out["symbol"] = self.symbol
        if self.market:
            out["market"] = self.market
        if self.sector:
            out["sector"] = self.sector
        if self.new_aliases:
            out["aliases"] = sorted(self.new_aliases)
        return out


class AliasIndex:
    """Maps normalized alias text to a :class:`ResolvedEntity`."""

    def __init__(self) -> None:
        self._by_alias: dict[str, ResolvedEntity] = {}
        self._by_slug: dict[str, ResolvedEntity] = {}

    def add(self, entity: ResolvedEntity, aliases: list[str]) -> ResolvedEntity:
        """Register an entity and its aliases; merges into an existing slug."""
        entity = self._by_slug.setdefault(entity.slug, entity)
        for alias in aliases:
            n = _norm(alias)
            if n:
                self._by_alias.setdefault(n, entity)
        return entity

    def lookup(self, text: str) -> ResolvedEntity | None:
        """Exact (normalized) alias match — the L1 deterministic hit."""
        return self._by_alias.get(_norm(text))

    def entity(self, slug: str) -> ResolvedEntity | None:
        return self._by_slug.get(slug)

    @property
    def entities(self) -> list[ResolvedEntity]:
        return list(self._by_slug.values())

    def find_in_text(self, text: str) -> list[ResolvedEntity]:
        """Every entity whose alias occurs in ``text`` (the dict-prepass match).

        CJK aliases match as substrings; Latin/digit aliases match on word
        boundaries to avoid spurious hits.
        """
        norm = _norm(text)
        hits: dict[str, ResolvedEntity] = {}
        for alias, entity in self._by_alias.items():
            if len(alias) < _MIN_ALIAS_LEN or entity.slug in hits:
                continue
            if _has_cjk(alias):
                matched = alias in norm
            else:
                matched = re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", norm) is not None
            if matched:
                hits[entity.slug] = entity
        return list(hits.values())


def build_alias_index(repo: WikiRepository) -> AliasIndex:
    """Build the alias index from the ticker registry + entity-page alias store."""
    index = AliasIndex()

    for info in all_ticker_infos():
        entity = ResolvedEntity(
            slug=ticker_slug(info.symbol),
            name=info.name or info.symbol,
            type=info.type or "company",
            symbol=info.symbol,
            market=info.market or None,
            sector=info.sector or None,
        )
        aliases = [info.symbol, info.name, info.name_en, *info.aliases]
        index.add(entity, [a for a in aliases if a])

    for page in repo.list_pages(kind="entity", limit=1_000_000):
        fm = page.frontmatter
        tickers = [str(t) for t in (fm.get("tickers") or [])]
        existing = index.entity(page.slug)
        entity = existing or ResolvedEntity(
            slug=page.slug,
            name=str(fm.get("name") or page.title or page.slug),
            type=str(fm.get("entity_type") or "company"),
            symbol=tickers[0] if tickers else None,
            market=fm.get("market"),
            sector=fm.get("sector"),
        )
        aliases = [entity.name, *tickers, *(str(a) for a in (fm.get("aliases") or []))]
        index.add(entity, [a for a in aliases if a])

    return index
