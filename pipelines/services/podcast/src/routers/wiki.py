"""Wiki content API — read/write the Postgres-backed knowledge wiki.

The podcast pipeline (running on the same box as Postgres) writes through the
``WikiRepository`` directly; this HTTP surface is for external readers, a future
UI, and the knowledge-graph service. Write/destructive routes require X-API-Key
(same as the rest of the podcast API); reads are open.
"""

from __future__ import annotations

import hashlib
from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from shared.tickers import canonical_symbol
from shared.wiki_builder import (
    WikiPage,
    build_index_markdown,
    episode_view,
    get_repository,
    ingest_episode,
    page_to_markdown,
    stats,
)
from shared.wiki_builder.repository import WikiRepository
from shared.wiki_builder.slugify import slugify, ticker_slug

from ..auth import verify_api_key

router = APIRouter(prefix="/api/wiki", tags=["wiki"])

_repository: WikiRepository | None = None


def get_repo() -> WikiRepository:
    """FastAPI dependency: the process-wide wiki repository.

    Tests override this via ``app.dependency_overrides[get_repo]``.
    """
    global _repository
    if _repository is None:
        _repository = get_repository()
    return _repository


# --- schemas -------------------------------------------------------------
class WikiPageIn(BaseModel):
    title: str = ""
    frontmatter: dict[str, Any] = Field(default_factory=dict)
    body: str = ""


class WikiPageOut(WikiPageIn):
    kind: str
    slug: str
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @classmethod
    def from_page(cls, page: WikiPage) -> "WikiPageOut":
        return cls(
            kind=page.kind,
            slug=page.slug,
            title=page.title,
            frontmatter=page.frontmatter,
            body=page.body,
            created_at=page.created_at,
            updated_at=page.updated_at,
        )


class WikiLinkOut(BaseModel):
    src_kind: str
    src_slug: str
    dst_kind: str
    dst_slug: str
    context: str = ""


class EpisodeIngestIn(BaseModel):
    podcast_name: str
    episode_number: int | None = None
    title: str
    date: str | None = None
    tickers: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    summary_text: str = ""
    events_markdown: str | None = None
    ticker_recommendations: dict[str, Any] | None = None
    source_urls: dict[str, str] | None = None


def _parse_frontmatter_query(q: str | None) -> dict[str, Any] | None:
    if not q:
        return None
    out: dict[str, Any] = {}
    for part in q.split(","):
        if ":" in part:
            key, value = part.split(":", 1)
            key = key.strip()
            if key:
                out[key] = value.strip()
    return out or None


# --- routes (static paths before /pages/{kind}/{slug}) -------------------
@router.get("/health")
async def wiki_health(repo: WikiRepository = Depends(get_repo)) -> dict:
    return repo.health()


@router.get("/pages")
async def list_wiki_pages(
    kind: str | None = Query(None),
    q: str | None = Query(None, description="frontmatter filter, e.g. 'tickers:TSM'"),
    limit: int = Query(200, ge=1, le=2000),
    offset: int = Query(0, ge=0),
    repo: WikiRepository = Depends(get_repo),
) -> dict:
    pages = repo.list_pages(
        kind=kind, frontmatter_filter=_parse_frontmatter_query(q), limit=limit, offset=offset
    )
    return {"count": len(pages), "pages": [WikiPageOut.from_page(p).model_dump() for p in pages]}


@router.get("/index")
async def wiki_index(
    format: str = Query("json", pattern="^(json|md)$"),
    repo: WikiRepository = Depends(get_repo),
) -> Any:
    pages = repo.list_pages(limit=100000)
    if format == "md":
        return Response(build_index_markdown(pages), media_type="text/markdown; charset=utf-8")
    by_kind: dict[str, list[dict[str, Any]]] = {}
    for p in pages:
        by_kind.setdefault(p.kind, []).append(
            {"slug": p.slug, "title": p.title, "frontmatter": p.frontmatter}
        )
    return by_kind


@router.get("/links")
async def list_wiki_links(
    src_kind: str | None = None,
    src_slug: str | None = None,
    dst_kind: str | None = None,
    dst_slug: str | None = None,
    repo: WikiRepository = Depends(get_repo),
) -> dict:
    src = (src_kind, src_slug) if src_kind and src_slug else None
    dst = (dst_kind, dst_slug) if dst_kind and dst_slug else None
    links = repo.list_links(src=src, dst=dst)
    return {"links": [WikiLinkOut(**link.to_dict()).model_dump() for link in links]}


@router.post("/ingest/episode", dependencies=[Depends(verify_api_key)])
async def ingest_episode_route(
    payload: EpisodeIngestIn, repo: WikiRepository = Depends(get_repo)
) -> dict:
    page = ingest_episode(repository=repo, **payload.model_dump())
    return {"episode_kind": page.kind, "episode_slug": page.slug}


# --- episode feed / detail (a richer, structured view over kind='episode' pages) ---
def _entity_name_map(repo: WikiRepository) -> dict[str, dict[str, Any]]:
    return {p.slug: dict(p.frontmatter) for p in repo.list_pages(kind="entity", limit=1_000_000)}


def _topic_name_map(repo: WikiRepository) -> dict[str, dict[str, Any]]:
    return {p.slug: dict(p.frontmatter) for p in repo.list_pages(kind="topic", limit=1_000_000)}


def _episode_sort_key(item: dict[str, Any]) -> tuple:
    # newest first; undated last; stable tiebreak on slug
    return (item.get("date") or "", item.get("slug") or "")


@router.get("/episodes")
async def list_episodes(
    podcast: list[str] | None = Query(None, description="filter to one or more show names"),
    ticker: str | None = Query(None, description="filter to episodes mentioning this ticker"),
    tag: str | None = Query(None, description="filter to episodes with this tag"),
    limit: int = Query(30, ge=1, le=200),
    offset: int = Query(0, ge=0),
    repo: WikiRepository = Depends(get_repo),
) -> dict:
    names = _entity_name_map(repo)
    want_ticker = ticker_slug(canonical_symbol(ticker)) if ticker else None
    items: list[dict[str, Any]] = []
    for page in repo.list_pages(kind="episode", limit=1_000_000):
        item = episode_view.feed_item(page, names)
        if podcast and item["podcast"] not in podcast:
            continue
        if tag and tag not in item["tags"]:
            continue
        if want_ticker and want_ticker not in {t["slug"] for t in item["tickers"]}:
            continue
        items.append(item)
    items.sort(key=_episode_sort_key, reverse=True)
    return {
        "total": len(items),
        "limit": limit,
        "offset": offset,
        "episodes": items[offset : offset + limit],
    }


@router.get("/episodes/{slug}")
async def get_episode(slug: str, repo: WikiRepository = Depends(get_repo)) -> dict:
    page = repo.get_page("episode", slug)
    if page is None:
        raise HTTPException(status_code=404, detail=f"episode/{slug} not found")
    return episode_view.episode_detail(page, _entity_name_map(repo), _topic_name_map(repo))


# --- news articles (read routes for the news-ingest path) ----------------
def _news_feed_item(page: WikiPage) -> dict[str, Any]:
    """Summary view of a ``news_article`` page (no claim bodies)."""
    fm = page.frontmatter
    return {
        "slug": page.slug,
        "title": page.title or str(fm.get("title", "")),
        "source": str(fm.get("source", "")),
        "date": str(fm.get("date", "")),
        "url": str(fm.get("url", "")),
        "tickers": [str(t) for t in (fm.get("tickers") or [])],
        "event_types": [str(e) for e in (fm.get("event_types") or [])],
        "tags": [str(t) for t in (fm.get("tags") or [])],
        "claim_count": len(fm.get("claims") or []),
    }


@router.get("/news")
async def list_news(
    ticker: str | None = Query(None, description="filter to articles mentioning this ticker"),
    event_type: str | None = Query(None, description="filter by claim event_type"),
    source: str | None = Query(None, description="filter by feed source name"),
    on_date: str | None = Query(None, alias="date", description="exact article date YYYY-MM-DD"),
    date_from: str | None = Query(None, description="inclusive lower bound YYYY-MM-DD"),
    date_to: str | None = Query(None, description="inclusive upper bound YYYY-MM-DD"),
    limit: int = Query(30, ge=1, le=200),
    offset: int = Query(0, ge=0),
    repo: WikiRepository = Depends(get_repo),
) -> dict:
    """Paginated, date-sorted (newest first) feed of ingested news articles."""
    want_ticker = canonical_symbol(ticker) if ticker else None
    items: list[dict[str, Any]] = []
    for page in repo.list_pages(kind="news_article", limit=1_000_000):
        item = _news_feed_item(page)
        if want_ticker and want_ticker not in item["tickers"]:
            continue
        if event_type and event_type not in item["event_types"]:
            continue
        if source and item["source"] != source:
            continue
        if on_date and item["date"] != on_date:
            continue
        if date_from and item["date"] < date_from:
            continue
        if date_to and item["date"] > date_to:
            continue
        items.append(item)
    items.sort(key=lambda i: (i["date"], i["slug"]), reverse=True)
    return {
        "total": len(items),
        "limit": limit,
        "offset": offset,
        "articles": items[offset : offset + limit],
    }


@router.get("/news/{slug}")
async def get_news_article(slug: str, repo: WikiRepository = Depends(get_repo)) -> dict:
    """Full article detail — claims with paragraph-level citations."""
    page = repo.get_page("news_article", slug)
    if page is None:
        raise HTTPException(status_code=404, detail=f"news_article/{slug} not found")
    fm = page.frontmatter
    detail = _news_feed_item(page)
    detail["claims"] = list(fm.get("claims") or [])
    detail["paragraphs"] = list(fm.get("paragraphs") or [])
    detail["body"] = page.body
    return detail


# --- structured claim query + contradictions (Phase 2, SQL/Python — no LLM) ---
@router.get("/claims")
async def list_claims(
    ticker: str | None = Query(None, description="filter by claim subject (ticker)"),
    event_type: str | None = Query(None, description="filter by event_type"),
    status: str | None = Query(None, description="active | superseded | contested"),
    date_from: str | None = Query(None, description="inclusive lower bound YYYY-MM-DD"),
    date_to: str | None = Query(None, description="inclusive upper bound YYYY-MM-DD"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    repo: WikiRepository = Depends(get_repo),
) -> dict:
    """Claims flattened across all news articles — a structured, LLM-free query."""
    want_subject = ticker_slug(canonical_symbol(ticker)) if ticker else None
    claims: list[dict[str, Any]] = []
    for page in repo.list_pages(kind="news_article", limit=1_000_000):
        article_date = str(page.frontmatter.get("date") or "")
        for claim in page.frontmatter.get("claims") or []:
            if want_subject and claim.get("subject") != want_subject:
                continue
            if event_type and claim.get("event_type") != event_type:
                continue
            if status and (claim.get("status") or "active") != status:
                continue
            claim_date = str(claim.get("claim_date") or article_date)
            if date_from and claim_date < date_from:
                continue
            if date_to and claim_date > date_to:
                continue
            claims.append(
                {
                    **claim,
                    "article_slug": page.slug,
                    "article_title": page.title,
                    "article_date": article_date,
                }
            )
    claims.sort(
        key=lambda c: (str(c.get("claim_date") or c.get("article_date") or ""),
                       str(c.get("article_slug") or "")),
        reverse=True,
    )
    return {
        "total": len(claims),
        "limit": limit,
        "offset": offset,
        "claims": claims[offset : offset + limit],
    }


@router.get("/contradictions")
async def list_contradictions(
    ticker: str | None = Query(None, description="filter to one entity (ticker)"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    repo: WikiRepository = Depends(get_repo),
) -> dict:
    """Confirmed conflicts flagged on entity pages by contradiction detection."""
    want_slug = ticker_slug(canonical_symbol(ticker)) if ticker else None
    items: list[dict[str, Any]] = []
    for page in repo.list_pages(kind="entity", limit=1_000_000):
        if want_slug and page.slug != want_slug:
            continue
        for conflict in page.frontmatter.get("conflicts") or []:
            items.append({"entity_slug": page.slug, "entity_name": page.title, **conflict})
    return {
        "total": len(items),
        "limit": limit,
        "offset": offset,
        "contradictions": items[offset : offset + limit],
    }


# --- context endpoint (Phase 3) — token-budgeted cited excerpts -----------
def _estimate_tokens(text: str) -> int:
    """Heuristic token count: CJK chars ≈ 1 token, other text ≈ 4 chars/token."""
    cjk = sum(1 for ch in text if "一" <= ch <= "鿿")
    return max(1, cjk + (len(text) - cjk) // 4)


def _resolve_context_targets(repo: WikiRepository, topic: str) -> list[tuple[str, str]]:
    """Resolve a free-form topic to (kind, slug) targets — topic and/or entity pages."""
    targets: list[tuple[str, str]] = []
    topic_slug = slugify(topic)
    entity_slug = ticker_slug(canonical_symbol(topic))
    if repo.get_page("topic", topic_slug):
        targets.append(("topic", topic_slug))
    if repo.get_page("entity", entity_slug):
        targets.append(("entity", entity_slug))
    if topic_slug != entity_slug and repo.get_page("entity", topic_slug):
        targets.append(("entity", topic_slug))
    return targets


def _news_excerpts(page: WikiPage) -> list[dict[str, Any]]:
    """Cited paragraph excerpts from a news_article page (one per cited paragraph)."""
    fm = page.frontmatter
    paragraphs = {p.get("index"): p for p in (fm.get("paragraphs") or [])}
    article_date = str(fm.get("date") or "")
    excerpts: list[dict[str, Any]] = []
    seen: set[str] = set()
    for claim in fm.get("claims") or []:
        para = paragraphs.get(claim.get("paragraph_index"))
        text = str((para or {}).get("text") or claim.get("quote") or "").strip()
        phash = str((para or {}).get("hash") or claim.get("paragraph_hash") or "")
        if not text or phash in seen:
            continue
        seen.add(phash)
        excerpts.append(
            {
                "page_kind": "news_article",
                "page_slug": page.slug,
                "source_url": str(fm.get("url") or ""),
                "paragraph_hash": phash,
                "paragraph_index": claim.get("paragraph_index"),
                "text": text,
                "date": article_date,
                "confidence": claim.get("confidence"),
            }
        )
    if not excerpts and (fm.get("paragraphs") or []):
        first = fm["paragraphs"][0]
        excerpts.append(
            {
                "page_kind": "news_article",
                "page_slug": page.slug,
                "source_url": str(fm.get("url") or ""),
                "paragraph_hash": str(first.get("hash") or ""),
                "paragraph_index": first.get("index"),
                "text": str(first.get("text") or "").strip(),
                "date": article_date,
                "confidence": None,
            }
        )
    return excerpts


def _episode_excerpt(page: WikiPage) -> list[dict[str, Any]]:
    """A single summary excerpt from an episode page, cited by episode slug."""
    head = page.body.split("\n## ", 1)[0]
    text = " ".join(
        " ".join(ln for ln in head.splitlines() if not ln.startswith("# ")).split()
    )
    if not text:
        return []
    return [
        {
            "page_kind": "episode",
            "page_slug": page.slug,
            "source_url": "",
            "paragraph_hash": hashlib.sha1(text.encode("utf-8")).hexdigest()[:16],
            "paragraph_index": 0,
            "text": text,
            "date": str(page.frontmatter.get("date") or ""),
            "confidence": 0.5,
        }
    ]


@router.get("/context")
async def wiki_context(
    topic: str = Query(..., description="topic name, entity name, or ticker"),
    tokens: int = Query(2000, ge=100, le=32000, description="token budget for the pack"),
    repo: WikiRepository = Depends(get_repo),
) -> dict:
    """Token-budgeted pack of cited excerpts about a topic (news + episodes).

    Resolves the topic to entity/topic pages, gathers the ``news_article`` and
    ``episode`` pages linked to them, ranks excerpts by recency + confidence,
    and packs them to the budget — with an explicit ``omitted`` signal.
    """
    targets = _resolve_context_targets(repo, topic)
    if not targets:
        raise HTTPException(status_code=404, detail=f"no topic or entity matches '{topic}'")

    source_keys: set[tuple[str, str]] = set()
    for kind, slug in targets:
        for link in repo.list_links(dst=(kind, slug)):
            if link.src_kind in ("news_article", "episode"):
                source_keys.add((link.src_kind, link.src_slug))

    excerpts: list[dict[str, Any]] = []
    for src_kind, src_slug in source_keys:
        page = repo.get_page(src_kind, src_slug)
        if page is None:
            continue
        if src_kind == "news_article":
            excerpts.extend(_news_excerpts(page))
        else:
            excerpts.extend(_episode_excerpt(page))

    # Rank by recency, then confidence (undated / unscored sort last).
    excerpts.sort(
        key=lambda e: (str(e.get("date") or ""), e.get("confidence") or 0.0),
        reverse=True,
    )

    packed: list[dict[str, Any]] = []
    used = 0
    omitted = 0
    for excerpt in excerpts:
        cost = _estimate_tokens(excerpt["text"])
        if used + cost <= tokens:
            excerpt["tokens"] = cost
            used += cost
            packed.append(excerpt)
        else:
            omitted += 1

    return {
        "topic": topic,
        "resolved_targets": [{"kind": k, "slug": s} for k, s in targets],
        "token_budget": tokens,
        "tokens_used": used,
        "excerpts": packed,
        "omitted": {
            "count": omitted,
            "reason": "token budget exceeded" if omitted else "",
        },
    }


# --- stats / aggregates (content-derived; for the platform webui's dashboards) ---
def _parse_as_of(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"invalid date: {value}") from exc


@router.get("/stats/top-tickers")
async def stats_top_tickers(
    days: int = Query(7, ge=1, le=365),
    limit: int = Query(10, ge=1, le=100),
    repo: WikiRepository = Depends(get_repo),
) -> dict:
    return {"window_days": days, "tickers": stats.top_tickers(repo, days=days, limit=limit)}


@router.get("/stats/top-shows")
async def stats_top_shows(
    days: int = Query(7, ge=1, le=365),
    limit: int = Query(10, ge=1, le=100),
    repo: WikiRepository = Depends(get_repo),
) -> dict:
    return {"window_days": days, "shows": stats.top_shows(repo, days=days, limit=limit)}


@router.get("/stats/topics")
async def stats_topics(
    days: int | None = Query(None, ge=1, le=365, description="omit for all-time"),
    limit: int = Query(20, ge=1, le=200),
    repo: WikiRepository = Depends(get_repo),
) -> dict:
    return {"window_days": days, "topics": stats.topics(repo, days=days, limit=limit)}


@router.get("/stats/pulse")
async def stats_pulse(
    on_date: str | None = Query(
        None, alias="date", description="YYYY-MM-DD; omit for the latest episode day"
    ),
    repo: WikiRepository = Depends(get_repo),
) -> dict:
    return stats.pulse(repo, on_date=_parse_as_of(on_date))


@router.get("/stats/dashboard")
async def stats_dashboard(
    days: int = Query(7, ge=1, le=365),
    repo: WikiRepository = Depends(get_repo),
) -> dict:
    return {
        "window_days": days,
        "pulse": stats.pulse(repo),
        "top_tickers": stats.top_tickers(repo, days=days, limit=8),
        "top_shows": stats.top_shows(repo, days=days, limit=6),
        "topics": stats.topics(repo, days=None, limit=20),
    }


@router.get("/stats/entity/{slug}")
async def stats_entity(
    slug: str,
    days: int | None = Query(None, ge=1, le=3650),
    repo: WikiRepository = Depends(get_repo),
) -> dict:
    agg = stats.entity_aggregate(repo, slug, days=days)
    if agg is None:
        raise HTTPException(status_code=404, detail=f"entity/{slug} not found")
    return agg


# NOTE: the `.md` route must precede `/pages/{kind}/{slug}` so the suffix matches.
@router.get("/pages/{kind}/{slug}.md")
async def get_wiki_page_markdown(
    kind: str, slug: str, repo: WikiRepository = Depends(get_repo)
) -> Response:
    page = repo.get_page(kind, slug)
    if page is None:
        raise HTTPException(status_code=404, detail=f"{kind}/{slug} not found")
    return Response(page_to_markdown(page), media_type="text/markdown; charset=utf-8")


@router.get("/pages/{kind}/{slug}")
async def get_wiki_page(
    kind: str, slug: str, repo: WikiRepository = Depends(get_repo)
) -> WikiPageOut:
    page = repo.get_page(kind, slug)
    if page is None:
        raise HTTPException(status_code=404, detail=f"{kind}/{slug} not found")
    return WikiPageOut.from_page(page)


@router.put("/pages/{kind}/{slug}", dependencies=[Depends(verify_api_key)])
async def upsert_wiki_page(
    kind: str, slug: str, body: WikiPageIn, repo: WikiRepository = Depends(get_repo)
) -> WikiPageOut:
    page = repo.upsert_page(
        WikiPage(
            kind=kind, slug=slug, title=body.title, frontmatter=body.frontmatter, body=body.body
        )
    )
    return WikiPageOut.from_page(page)


@router.delete("/pages/{kind}/{slug}", dependencies=[Depends(verify_api_key)])
async def delete_wiki_page(
    kind: str, slug: str, repo: WikiRepository = Depends(get_repo)
) -> dict:
    return {"deleted": repo.delete_page(kind, slug)}
