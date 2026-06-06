"""Step 6 — resolve every mention to a canonical entity slug.

L1: exact registry/alias hit (deterministic, no LLM).
L3: one LLM disambiguation call for the genuine residuals only.
(L2 embeddings are deferred — see the design plan.)

Newly-confirmed aliases (residual mentions that the LLM tied to an entity) are
collected on the entity so ``ingest_news_article`` appends them to the entity
page's ``frontmatter.aliases`` — the live alias store.
"""

from __future__ import annotations

from typing import Callable

from shared.wiki_builder.slugify import slugify

from ...alias_index import AliasIndex, ResolvedEntity
from ...llm import call_json
from ...prompts import DISAMBIG_SYSTEM, DISAMBIG_USER
from ..article import Article

_MAX_KNOWN_IN_PROMPT = 400


def _collect_mentions(article: Article) -> list[str]:
    """Distinct mention strings: claim subjects first, then LLM-surfaced entities."""
    mentions: list[str] = []
    seen: set[str] = set()
    for claim in article.claims:
        m = str(claim.get("subject") or "").strip()
        if m and m.lower() not in seen:
            seen.add(m.lower())
            mentions.append(m)
    for m in article.raw_mentions:
        if m and m.lower() not in seen:
            seen.add(m.lower())
            mentions.append(m)
    return mentions


def _resolve_residuals(
    residuals: list[str],
    resolved: dict[str, ResolvedEntity],
    index: AliasIndex,
    llm: Callable[[str, str], dict],
) -> None:
    """L3 — one LLM disambiguation call mapping residual mentions to entities."""
    known = index.entities[:_MAX_KNOWN_IN_PROMPT]
    user = DISAMBIG_USER.format(
        known="\n".join(f"{e.slug} — {e.name}" for e in known),
        mentions="\n".join(f"- {m}" for m in residuals),
    )
    try:
        result = llm(DISAMBIG_SYSTEM, user)
    except Exception as exc:  # noqa: BLE001 — disambiguation is best-effort
        print(f"  ⚠ entity disambiguation failed: {exc}")
        return

    for item in result.get("resolutions") or []:
        if not isinstance(item, dict):
            continue
        mention = str(item.get("mention") or "").strip()
        slug = str(item.get("slug") or "").strip()
        if not mention or not slug or slug == "SKIP":
            continue
        if slug == "NEW":
            name = str(item.get("name") or mention).strip()
            new_slug = slugify(name)
            if not new_slug:
                continue
            entity = index.entity(new_slug) or ResolvedEntity(
                slug=new_slug, name=name, type=str(item.get("type") or "company")
            )
            entity.new_aliases.add(mention)
            index.add(entity, [name, mention])
        else:
            entity = index.entity(slug)
            if entity is None:
                continue
            entity.new_aliases.add(mention)  # newly-confirmed alias
        resolved[mention.lower()] = entity


def resolve(
    article: Article,
    index: AliasIndex,
    *,
    llm: Callable[[str, str], dict] | None = None,
) -> Article:
    """Rewrite claim subjects to canonical slugs and build ``article.entities``."""
    llm = llm or call_json
    resolved: dict[str, ResolvedEntity] = {}
    residuals: list[str] = []
    for mention in _collect_mentions(article):
        entity = index.lookup(mention)
        if entity is not None:
            resolved[mention.lower()] = entity
        else:
            residuals.append(mention)

    if residuals:
        _resolve_residuals(residuals, resolved, index, llm)

    # Rewrite claim subjects to canonical slugs; drop claims whose subject never resolved.
    kept: list[dict] = []
    for claim in article.claims:
        entity = resolved.get(str(claim.get("subject") or "").strip().lower())
        if entity is None:
            continue
        claim["subject"] = entity.slug
        kept.append(claim)
    article.claims = kept

    # Entity set: every resolved mention + every dict-prepass candidate.
    used: dict[str, ResolvedEntity] = {e.slug: e for e in resolved.values()}
    for slug in article.candidate_entities:
        entity = index.entity(slug)
        if entity is not None:
            used.setdefault(slug, entity)

    article.entities = [e.to_ingest_dict() for e in used.values()]
    return article
