"""Ingest episode and supply-chain content into a :class:`WikiRepository`.

Entry points:
  - :func:`ingest_episode` — podcast episode data (used by ``services/podcast``)
  - :func:`ingest_supply_chain` — entity/edge data (knowledge-graph follow-up)

These build :class:`WikiPage` records and persist them via the repository; they
do not touch the filesystem.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

from ..tickers import canonical_symbol, lookup_ticker
from .factory import get_repository
from .models import WikiPage
from .records import (
    normalize_claim,
    normalize_sentiment,
    render_entity_page,
    render_episode_page,
    render_news_article_page,
    render_supply_chain_page,
    render_topic_page,
)
from .repository import WikiRepository
from .slugify import news_slug, slugify, ticker_slug


def _canonical_tickers(tickers: list[str]) -> list[str]:
    """Canonicalize + de-duplicate a ticker list, preserving first-seen order."""
    seen: dict[str, None] = {}
    for t in tickers:
        sym = canonical_symbol(t)
        if sym:
            seen.setdefault(sym, None)
    return list(seen)


def _append_line_to_section(body: str, marker: str, line: str) -> str:
    """Insert ``line`` once as the first item under ``marker``.

    Creates the section (with a blank line after the heading) if it is missing.
    """
    if line in body:
        return body
    idx = body.find(marker)
    if idx == -1:
        return body.rstrip() + f"\n\n{marker}\n\n{line}\n"
    nl = body.find("\n", idx)
    insert_at = len(body) if nl == -1 else nl + 1
    if body[insert_at : insert_at + 1] == "\n":  # keep one blank line after the heading
        insert_at += 1
    return body[:insert_at] + line + "\n" + body[insert_at:]


def _append_ticker_history(
    page: WikiPage, *, date: str, sentiment: str, score: Any, thesis: str
) -> None:
    row = f"| {date} | {sentiment} | {score} | {str(thesis).replace('|', '—')} |"
    body = page.body
    if row in body:
        return
    marker = "## Ticker History"
    if marker not in body:
        page.body = body.rstrip() + (
            "\n\n## Ticker History\n\n"
            "| Date | Sentiment | Score | Thesis |\n"
            "|------|-----------|-------|--------|\n"
            f"{row}\n"
        )
        return
    lines = body.split("\n")
    start = next(i for i, ln in enumerate(lines) if ln.strip() == marker)
    last_table_row = start
    for i in range(start + 1, len(lines)):
        if lines[i].lstrip().startswith("|"):
            last_table_row = i
        elif lines[i].strip().startswith("#"):
            break
    lines.insert(last_table_row + 1, row)
    page.body = "\n".join(lines)


def ingest_episode(
    podcast_name: str,
    episode_number: int | None,
    title: str,
    date: str | None,
    tickers: list[str],
    tags: list[str],
    summary_text: str,
    events_markdown: str | None = None,
    ticker_recommendations: dict[str, Any] | None = None,
    source_urls: dict[str, str] | None = None,
    repository: WikiRepository | None = None,
) -> WikiPage:
    """Persist episode data: the episode page plus referenced entity/topic pages.

    Returns the (persisted) episode :class:`WikiPage`.
    """
    repo = repository or get_repository()
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")

    tickers = _canonical_tickers(tickers)  # registry-canonical symbols (e.g. "2330.TW" -> "2330")

    episode_page = render_episode_page(
        podcast_name=podcast_name,
        episode_number=episode_number,
        title=title,
        date=date,
        tickers=tickers,
        tags=tags,
        summary_text=summary_text,
        events_markdown=events_markdown,
        ticker_recommendations=ticker_recommendations,
        source_urls=source_urls,
    )
    ep_link = f"episodes/{episode_page.slug}"
    episode_page = repo.upsert_page(episode_page)

    recs = (ticker_recommendations or {}).get("ticker_recommendations", [])
    recs_by_ticker = {canonical_symbol(r["ticker"]): r for r in recs if r.get("ticker")}

    for ticker in tickers:
        t_slug = ticker_slug(ticker)
        page = repo.get_page("entity", t_slug)
        if page is None:
            info = lookup_ticker(ticker)
            page = render_entity_page(
                entity_id=t_slug,
                name=info.name if info else ticker,
                entity_type=info.type if info else "company",
                tickers=[ticker],
                mentions=[{"episode_link": ep_link, "context": title}],
                ticker_history=[],
                market=info.market if info else None,
                sector=info.sector if info else None,
            )
        else:
            page.body = _append_line_to_section(
                page.body, "## Episode Mentions", f"- [[{ep_link}]] — {title}"
            )
        rec = recs_by_ticker.get(ticker)
        if rec:
            _append_ticker_history(
                page,
                date=date,
                sentiment=rec.get("sentiment", ""),
                score=rec.get("sentiment_score", ""),
                thesis=rec.get("bluf_thesis", ""),
            )
        repo.upsert_page(page)

    for tag in tags:
        tg_slug = slugify(tag)
        page = repo.get_page("topic", tg_slug)
        if page is None:
            page = render_topic_page(
                topic_id=tg_slug,
                name=tag,
                episodes=[{"link": ep_link, "context": title}],
                entities=[ticker_slug(t) for t in tickers],
            )
        else:
            page.body = _append_line_to_section(
                page.body, "## Episodes", f"- [[{ep_link}]] — {title}"
            )
        repo.upsert_page(page)

    return episode_page


def _news_claim_index_rows(
    claims: list[dict[str, Any]],
    entity_slug: str,
    article_slug: str,
    url: str,
    date: str,
) -> list[dict[str, Any]]:
    """Compact ``claim_index`` rows for one entity, drawn from this article's claims."""
    rows: list[dict[str, Any]] = []
    for c in claims:
        if c.get("subject") != entity_slug:
            continue
        rows.append(
            {
                "claim_id": c.get("id", ""),
                "source_slug": article_slug,
                "source_url": url,
                "predicate": c.get("predicate", ""),
                "object": c.get("object", ""),
                "event_type": c.get("event_type", "other"),
                "date": date,
                "sentiment": c.get("sentiment", ""),
                "confidence": c.get("confidence"),
                "status": c.get("status", "active"),
            }
        )
    return rows


def _norm_text(value: Any) -> str:
    """Whitespace-collapsed, lower-cased text for loose equality checks."""
    return " ".join(str(value or "").lower().split())


def _claim_rows_by_date(a: dict[str, Any], b: dict[str, Any]) -> tuple[dict, dict]:
    """Return (newer, older) of two claim_index rows, ordered by their ``date``."""
    return (a, b) if str(a.get("date") or "") >= str(b.get("date") or "") else (b, a)


def _conflict_key(conflict: dict[str, Any]) -> tuple:
    """Stable identity for a conflict record, for append-dedup."""
    if conflict.get("type") == "news_vs_news":
        return ("news_vs_news", conflict["older"]["claim_id"], conflict["newer"]["claim_id"])
    return ("sentiment", conflict["news"]["claim_id"], conflict["podcast"].get("date"))


def _set_claim_status_on_article(
    repo: WikiRepository, source_slug: str, claim_id: str, status: str, superseded_by: Any
) -> None:
    """Persist a claim status change onto its source ``news_article`` page."""
    if not source_slug or not claim_id:
        return
    page = repo.get_page("news_article", source_slug)
    if page is None:
        return
    changed = False
    for claim in page.frontmatter.get("claims") or []:
        if claim.get("id") == claim_id:
            claim["status"] = status
            claim["superseded_by"] = superseded_by
            changed = True
    if changed:
        repo.upsert_page(page)


def _detect_news_conflicts(
    repo: WikiRepository,
    new_rows: list[dict[str, Any]],
    prior_rows: list[dict[str, Any]],
    conflict_checker: Callable[[dict, dict], bool],
) -> list[dict[str, Any]]:
    """News-vs-news: same ``(subject, predicate)`` + differing ``object`` -> LLM check.

    On a confirmed conflict the older claim's ``status`` is set to ``superseded``
    (newer confidence ≥ older) or ``contested``, both on the entity ``claim_index``
    row (mutated in place) and on its source article page.
    """
    conflicts: list[dict[str, Any]] = []
    for new in new_rows:
        for old in prior_rows:
            if old.get("status") != "active":
                continue
            if _norm_text(new.get("predicate")) != _norm_text(old.get("predicate")):
                continue
            if _norm_text(new.get("object")) == _norm_text(old.get("object")):
                continue
            if not conflict_checker(new, old):
                continue
            newer, older = _claim_rows_by_date(new, old)
            superseded = (newer.get("confidence") or 0) >= (older.get("confidence") or 0)
            older["status"] = "superseded" if superseded else "contested"
            older["superseded_by"] = newer.get("claim_id") if superseded else None
            _set_claim_status_on_article(
                repo,
                str(older.get("source_slug") or ""),
                str(older.get("claim_id") or ""),
                older["status"],
                older["superseded_by"],
            )
            conflicts.append(
                {
                    "type": "news_vs_news",
                    "predicate": new.get("predicate"),
                    "newer": {
                        "claim_id": newer.get("claim_id"),
                        "object": newer.get("object"),
                        "source_slug": newer.get("source_slug"),
                        "date": newer.get("date"),
                    },
                    "older": {
                        "claim_id": older.get("claim_id"),
                        "object": older.get("object"),
                        "source_slug": older.get("source_slug"),
                        "date": older.get("date"),
                    },
                    "resolution": older["status"],
                }
            )
    return conflicts


def _latest_podcast_sentiment(
    repo: WikiRepository, entity_slug: str, symbol: str
) -> tuple[str, str]:
    """Most recent podcast sentiment for ``symbol`` from episodes linking this entity."""
    best_date, best_sentiment = "", ""
    for link in repo.list_links(dst=("entity", entity_slug)):
        if link.src_kind != "episode":
            continue
        episode = repo.get_page("episode", link.src_slug)
        if episode is None:
            continue
        sentiment = (episode.frontmatter.get("ticker_sentiment") or {}).get(symbol)
        ep_date = str(episode.frontmatter.get("date") or "")
        if sentiment and ep_date >= best_date:
            best_date, best_sentiment = ep_date, str(sentiment)
    return best_sentiment, best_date


def _detect_sentiment_conflicts(
    repo: WikiRepository, entity_page: WikiPage, new_rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """News-vs-podcast: a news claim's sentiment opposing the latest podcast sentiment."""
    symbol = next((str(t) for t in (entity_page.frontmatter.get("tickers") or [])), "")
    if not symbol:
        return []
    podcast_sentiment, podcast_date = _latest_podcast_sentiment(repo, entity_page.slug, symbol)
    if podcast_sentiment not in ("bull", "bear"):
        return []

    conflicts: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in new_rows:
        news_sentiment = normalize_sentiment(row.get("sentiment"))
        if {news_sentiment, podcast_sentiment} != {"bull", "bear"}:
            continue
        key = _norm_text(row.get("predicate"))
        if key in seen:
            continue
        seen.add(key)
        conflicts.append(
            {
                "type": "sentiment",
                "predicate": row.get("predicate"),
                "news": {
                    "claim_id": row.get("claim_id"),
                    "sentiment": news_sentiment,
                    "source_slug": row.get("source_slug"),
                    "date": row.get("date"),
                },
                "podcast": {"sentiment": podcast_sentiment, "date": podcast_date},
            }
        )
    return conflicts


def ingest_news_article(
    url: str,
    title: str,
    source: str,
    date: str | None,
    content_hash: str,
    paragraphs: list[dict[str, Any]],
    claims: list[dict[str, Any]],
    tags: list[str],
    entities: list[dict[str, Any]] | None = None,
    summary: str = "",
    conflict_checker: Callable[[dict, dict], bool] | None = None,
    repository: WikiRepository | None = None,
) -> WikiPage:
    """Persist a news article: the article page plus referenced entity/topic pages.

    Mirrors :func:`ingest_episode` — renders the page, upserts it, then
    **append-only enriches** the shared ``entity``/``topic`` pages (never
    overwrites). Re-ingesting the same article URL is idempotent: the slug is a
    hash of the canonical URL, so ``upsert_page`` replaces in place.

    ``entities`` is the resolver's output — one dict per canonical entity with
    ``slug`` (required), ``name``, ``type``, optional ``symbol`` (registry
    ticker), ``market``, ``sector`` and ``aliases`` (newly-confirmed). Every
    distinct ``claim['subject']`` is expected to appear here.

    When ``conflict_checker`` is supplied, Phase-2 contradiction detection runs:
    a new claim conflicting with a prior claim on the same ``(subject,
    predicate)`` flags the entity page's ``conflicts`` and supersedes/contests
    the older claim. ``conflict_checker(new_row, old_row) -> bool`` is the
    (LLM-backed) yes/no decision, injected so this layer stays LLM-agnostic.

    Returns the (persisted) ``news_article`` :class:`WikiPage`.
    """
    repo = repository or get_repository()
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")
    entities = entities or []

    article_slug = news_slug(url)

    # Normalize claims and give each a stable id within the article.
    norm_claims: list[dict[str, Any]] = []
    for i, raw in enumerate(claims):
        c = normalize_claim(raw)
        if not c.get("id"):
            c["id"] = f"{article_slug}-c{i}"
        norm_claims.append(c)

    tickers = _canonical_tickers([str(e["symbol"]) for e in entities if e.get("symbol")])
    entity_slugs = [str(e["slug"]) for e in entities if e.get("slug")]

    article_page = render_news_article_page(
        url=url,
        title=title,
        source=source,
        date=date,
        content_hash=content_hash,
        tickers=tickers,
        entity_slugs=entity_slugs,
        tags=tags,
        claims=norm_claims,
        paragraphs=paragraphs,
        summary=summary,
    )
    article_page = repo.upsert_page(article_page)
    news_link = f"news/{article_slug}"

    for ent in entities:
        slug = str(ent.get("slug") or "")
        if not slug:
            continue
        rollup = _news_claim_index_rows(norm_claims, slug, article_slug, url, date)
        new_aliases = [str(a) for a in (ent.get("aliases") or []) if a]

        page = repo.get_page("entity", slug)
        if page is None:
            page = render_entity_page(
                entity_id=slug,
                name=str(ent.get("name") or slug),
                entity_type=str(ent.get("type") or "company"),
                tickers=[str(ent["symbol"])] if ent.get("symbol") else [],
                news_mentions=[{"news_link": news_link, "context": title}],
                aliases=new_aliases,
                claim_index=rollup,
                market=ent.get("market"),
                sector=ent.get("sector"),
            )
            prior_rows: list[dict[str, Any]] = []
        else:
            page.body = _append_line_to_section(
                page.body, "## News Mentions", f"- [[{news_link}]] — {title}"
            )
            if new_aliases:
                merged = set(page.frontmatter.get("aliases") or []) | set(new_aliases)
                page.frontmatter["aliases"] = sorted(merged)
            # Replace this article's rows in claim_index (idempotent re-ingest), keep the rest.
            prior_rows = [
                r
                for r in (page.frontmatter.get("claim_index") or [])
                if r.get("source_slug") != article_slug
            ]
            page.frontmatter["claim_index"] = prior_rows + rollup

        # Phase 2 — contradiction detection (only when a checker is supplied).
        if conflict_checker is not None:
            found = _detect_news_conflicts(repo, rollup, prior_rows, conflict_checker)
            found += _detect_sentiment_conflicts(repo, page, rollup)
            if found:
                existing = page.frontmatter.get("conflicts") or []
                existing_keys = {_conflict_key(c) for c in existing}
                fresh = [c for c in found if _conflict_key(c) not in existing_keys]
                if fresh:
                    page.frontmatter["conflicts"] = existing + fresh

        repo.upsert_page(page)

    for tag in tags:
        tg_slug = slugify(tag)
        page = repo.get_page("topic", tg_slug)
        if page is None:
            page = render_topic_page(topic_id=tg_slug, name=tag, entities=entity_slugs)
        page.body = _append_line_to_section(
            page.body, "## News Articles", f"- [[{news_link}]] — {title}"
        )
        repo.upsert_page(page)

    return article_page


def ingest_supply_chain(
    entities: list[dict],
    edges: list[dict],
    evidence: list[dict] | None = None,
    repository: WikiRepository | None = None,
) -> int:
    """Persist supply-chain data (entity pages + per-source supply-chain pages).

    Returns the number of pages created/updated.
    """
    repo = repository or get_repository()
    count = 0
    entity_map = {e["id"]: e for e in entities}

    for edge in edges:
        src_id = edge.get("src", "")
        dst_id = edge.get("dst", "")
        rel = edge.get("rel", "RELATED_TO")
        status = edge.get("props", {}).get("status", "active")

        src_name = entity_map.get(src_id, {}).get("props", {}).get("name", src_id)
        dst_name = entity_map.get(dst_id, {}).get("props", {}).get("name", dst_id)
        src_slug = slugify(src_name)
        dst_slug = slugify(dst_name)

        for eid, ename, eslug in ((src_id, src_name, src_slug), (dst_id, dst_name, dst_slug)):
            if repo.get_page("entity", eslug) is None:
                etype = entity_map.get(eid, {}).get("type", "company")
                repo.upsert_page(
                    render_entity_page(
                        entity_id=eslug, name=ename, entity_type=etype, tickers=[]
                    )
                )
                count += 1

        sc_page = repo.get_page("supply_chain", src_slug) or render_supply_chain_page(
            src_slug, src_name
        )
        rel_line = f"- [[entities/{dst_slug}]] — {rel} ({status})"
        if rel_line not in sc_page.body:
            sc_page.body = _append_line_to_section(
                sc_page.body, "## Downstream (Customers)", rel_line
            )
            repo.upsert_page(sc_page)
            count += 1

    return count
