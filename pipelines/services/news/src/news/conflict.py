"""News-vs-news claim contradiction check — one focused OpenRouter yes/no call.

``wiki_builder.ingest_news_article`` stays LLM-agnostic; it takes a
``conflict_checker`` callable. :func:`check_conflict` is that callable for the
news pipeline. A failed check is treated as "no conflict" so a transient LLM
error never fabricates a contradiction.
"""

from __future__ import annotations

from typing import Callable

from .llm import call_json
from .prompts import CONFLICT_SYSTEM, CONFLICT_USER


def check_conflict(
    new_claim: dict,
    old_claim: dict,
    *,
    llm: Callable[[str, str], dict] | None = None,
) -> bool:
    """True when the two claims genuinely contradict each other."""
    llm = llm or call_json
    user = CONFLICT_USER.format(
        predicate=new_claim.get("predicate", ""),
        new_object=new_claim.get("object", ""),
        old_object=old_claim.get("object", ""),
    )
    try:
        result = llm(CONFLICT_SYSTEM, user)
    except Exception as exc:  # noqa: BLE001 — a failed check must not fabricate a conflict
        print(f"  ⚠ conflict check failed: {exc}")
        return False
    return bool(result.get("conflict"))
