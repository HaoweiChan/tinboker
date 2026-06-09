"""Step 5 — one OpenRouter call: typed claims + tags + missed entity mentions.

The LLM sees the indexed paragraphs and the dict-prepass candidates as hints,
and returns akbp-shaped claims grounded in a specific paragraph. Claim subjects
stay as written here — step 6 (resolve) canonicalizes them.
"""

from __future__ import annotations

from typing import Callable

from shared.wiki_builder import normalize_event_type

from ...alias_index import AliasIndex
from ...llm import call_json
from ...prompts import ENRICH_SYSTEM, ENRICH_USER
from ..article import Article


def llm_enrich(
    article: Article,
    index: AliasIndex,
    *,
    llm: Callable[[str, str], dict] | None = None,
) -> Article:
    """Populate ``article.claims``, ``tags``, ``summary`` and ``raw_mentions``."""
    if not article.paragraphs:
        return article
    llm = llm or call_json

    paragraphs_block = "\n".join(f"[{p.index}] {p.text}" for p in article.paragraphs)
    candidate_names = [
        index.entity(slug).name for slug in article.candidate_entities if index.entity(slug)
    ]
    user = ENRICH_USER.format(
        title=article.title,
        candidates=", ".join(candidate_names) if candidate_names else "(none)",
        paragraphs=paragraphs_block,
    )
    result = llm(ENRICH_SYSTEM, user)

    article.summary = str(result.get("summary") or "").strip()
    article.tags = [str(t).strip() for t in (result.get("tags") or []) if str(t).strip()]
    article.raw_mentions = [
        str(m).strip() for m in (result.get("entities") or []) if str(m).strip()
    ]

    claims: list[dict] = []
    for raw in result.get("claims") or []:
        if not isinstance(raw, dict) or not str(raw.get("subject") or "").strip():
            continue
        claim = dict(raw)
        claim["event_type"] = normalize_event_type(claim.get("event_type"))
        claim["source_url"] = article.url
        claim["claim_date"] = article.published
        pidx = claim.get("paragraph_index")
        if isinstance(pidx, int) and 0 <= pidx < len(article.paragraphs):
            claim["paragraph_hash"] = article.paragraphs[pidx].hash
        else:
            claim["paragraph_hash"] = None
        claims.append(claim)
    article.claims = claims
    return article
