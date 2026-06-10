"""Render content data into :class:`WikiPage` records.

These functions know the *shape* of episode / entity / topic content (that
shape is content, not infra) but they emit plain ``WikiPage`` records — they no
longer touch the filesystem. Markdown is a *view* (see :mod:`.views`), not the
storage format.
"""

from __future__ import annotations

import re
from typing import Any

from ..tickers import canonical_symbol
from .models import WikiPage
from .slugify import episode_slug, news_slug, slugify, ticker_slug

_SENTIMENT_KEYS = ("bull", "bear", "neut")

# Controlled vocabularies for news claims (akbp-shaped, collapsed lifecycle).
EVENT_TYPES = (
    "earnings",
    "guidance",
    "m_and_a",
    "regulatory",
    "product",
    "rating",
    "macro",
    "other",
)
CLAIM_STATUSES = ("active", "superseded", "contested")


_EVENT_TYPE_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("m_and_a", ("m_and_a", "merger", "acquisition", "takeover", "buyout", "deal")),
    ("earnings", ("earning", "result", "quarter", "revenue", "profit")),
    ("guidance", ("guidance", "outlook", "forecast")),
    ("regulatory", ("regulat", "antitrust", "lawsuit", "legal", "probe", "fine", "sanction")),
    ("product", ("product", "launch", "release", "unveil")),
    ("rating", ("rating", "upgrade", "downgrade", "price_target", "analyst", "initiat")),
    ("macro", ("macro", "economy", "economic", "inflation", "rates", "tariff", "gdp")),
)


def normalize_event_type(value: Any) -> str:
    """Map a free-form event-type label to the controlled vocab; unknown -> 'other'."""
    s = re.sub(r"[^a-z]+", "_", str(value or "").lower().replace("&", " and ")).strip("_")
    if s in EVENT_TYPES:
        return s
    for canon, keywords in _EVENT_TYPE_KEYWORDS:
        if any(k in s for k in keywords):
            return canon
    return "other"


def normalize_claim_status(value: Any) -> str:
    """Map a free-form claim status to the controlled vocab; unknown -> 'active'."""
    s = str(value or "").strip().lower()
    return s if s in CLAIM_STATUSES else "active"


def normalize_sentiment(value: Any) -> str:
    """Map a free-form sentiment label to ``'bull' | 'bear' | 'neut' | ''`` (unrecognized).

    Handles English ('bullish', 'positive', 'buy', …), Chinese (看多/看空/中性) and the short
    forms already used elsewhere ('bull'/'bear'/'neut').
    """
    s = str(value or "").strip().lower()
    if not s:
        return ""
    if "bull" in s or "多" in s or s in {"positive", "buy", "overweight", "long"}:
        return "bull"
    if "bear" in s or "空" in s or s in {"negative", "sell", "underweight", "short"}:
        return "bear"
    if "neut" in s or "中" in s or s in {"hold", "mixed", "flat"}:
        return "neut"
    return ""


def render_episode_page(
    podcast_name: str,
    episode_number: int | None,
    title: str,
    date: str,
    tickers: list[str],
    tags: list[str],
    summary_text: str,
    events_markdown: str | None,
    ticker_insights: list | dict[str, Any] | None,
    source_urls: dict[str, str] | None,
) -> WikiPage:
    slug = episode_slug(podcast_name, episode_number, title)

    frontmatter: dict[str, Any] = {"podcast": podcast_name}
    if episode_number is not None:
        frontmatter["episode_number"] = episode_number
    frontmatter["title"] = title
    frontmatter["date"] = date
    frontmatter["tickers"] = [str(t) for t in tickers]
    frontmatter["tags"] = [str(t) for t in tags]
    if source_urls:
        clean = {k: v for k, v in source_urls.items() if v}
        if clean:
            frontmatter["source_urls"] = clean

    lines: list[str] = [f"# {title}", ""]
    if summary_text:
        lines += [summary_text.strip(), ""]
    if events_markdown:
        lines += ["## Events Timeline", "", events_markdown.strip(), ""]

    if isinstance(ticker_insights, list):
        insights = ticker_insights
    elif isinstance(ticker_insights, dict):
        insights = ticker_insights.get("ticker_insights") or ticker_insights.get("ticker_recommendations", [])
    else:
        insights = []
    if insights:
        lines += [
            "## Ticker Insights",
            "",
            "| Ticker | Sentiment | Score | Time Horizon | Thesis |",
            "|--------|-----------|-------|--------------|--------|",
        ]
        for rec in insights:
            thesis = str(rec.get("bluf_thesis", "")).replace("|", "—")
            lines.append(
                f"| {rec.get('ticker', '')} | {rec.get('sentiment', '')} "
                f"| {rec.get('sentiment_score', '')} | {rec.get('time_horizon', '')} | {thesis} |"
            )
        lines.append("")

    # Structured per-ticker sentiment (canonical symbol -> bull|bear|neut) for the stats API.
    sentiment_map: dict[str, str] = {}
    for rec in insights:
        sym = rec.get("ticker")
        sent = normalize_sentiment(rec.get("sentiment", ""))
        if sym and sent:
            sentiment_map[canonical_symbol(str(sym))] = sent
    if sentiment_map:
        frontmatter["ticker_sentiment"] = sentiment_map

    related = [f"- [[entities/{ticker_slug(t)}]]" for t in tickers]
    related += [f"- [[topics/{slugify(tag)}]]" for tag in tags]
    if related:
        lines += ["## Related", "", *related, ""]

    return WikiPage(
        kind="episode", slug=slug, title=title, frontmatter=frontmatter, body="\n".join(lines)
    )


def render_entity_page(
    entity_id: str,
    name: str,
    entity_type: str,
    tickers: list[str],
    mentions: list[dict[str, str]] | None = None,
    ticker_history: list[dict[str, Any]] | None = None,
    supply_upstream: list[dict[str, str]] | None = None,
    supply_downstream: list[dict[str, str]] | None = None,
    market: str | None = None,
    sector: str | None = None,
    news_mentions: list[dict[str, str]] | None = None,
    aliases: list[str] | None = None,
    claim_index: list[dict[str, Any]] | None = None,
    conflicts: list[dict[str, Any]] | None = None,
) -> WikiPage:
    mentions = mentions or []
    ticker_history = ticker_history or []
    news_mentions = news_mentions or []

    frontmatter: dict[str, Any] = {
        "id": entity_id,
        "name": name,
        "entity_type": entity_type,
        "tickers": [str(t) for t in tickers],
    }
    if market:
        frontmatter["market"] = market
    if sector:
        frontmatter["sector"] = sector
    # Append-only opaque fields: the live alias store, a compact claim rollup, and
    # contradiction flags. Written only when the news path supplies them.
    if aliases:
        frontmatter["aliases"] = sorted({str(a) for a in aliases if a})
    if claim_index:
        frontmatter["claim_index"] = claim_index
    if conflicts:
        frontmatter["conflicts"] = conflicts

    lines: list[str] = [f"# {name}", ""]
    if mentions:
        lines += ["## Episode Mentions", ""]
        for m in mentions:
            lines.append(f"- [[{m.get('episode_link', '')}]] — {m.get('context', '')}")
        lines.append("")
    if news_mentions:
        lines += ["## News Mentions", ""]
        for m in news_mentions:
            lines.append(f"- [[{m.get('news_link', '')}]] — {m.get('context', '')}")
        lines.append("")
    if supply_upstream or supply_downstream:
        lines += ["## Supply Chain", ""]
        for s in supply_upstream or []:
            lines.append(f"- Supplied by: [[entities/{s['slug']}]] — {s.get('rel', '')}")
        for s in supply_downstream or []:
            lines.append(f"- Supplies to: [[entities/{s['slug']}]] — {s.get('rel', '')}")
        lines.append("")
    if ticker_history:
        lines += [
            "## Ticker History",
            "",
            "| Date | Sentiment | Score | Thesis |",
            "|------|-----------|-------|--------|",
        ]
        for h in ticker_history:
            thesis = str(h.get("thesis", "")).replace("|", "—")
            cells = [h.get("date", ""), h.get("sentiment", ""), h.get("score", ""), thesis]
            lines.append("| " + " | ".join(str(c) for c in cells) + " |")
        lines.append("")

    return WikiPage(
        kind="entity", slug=entity_id, title=name, frontmatter=frontmatter, body="\n".join(lines)
    )


def render_topic_page(
    topic_id: str,
    name: str,
    episodes: list[dict[str, str]] | None = None,
    entities: list[str] | None = None,
) -> WikiPage:
    episodes = episodes or []
    entities = entities or []

    lines: list[str] = [f"# {name}", ""]
    if episodes:
        lines += ["## Episodes", ""]
        for ep in episodes:
            lines.append(f"- [[{ep['link']}]] — {ep.get('context', '')}")
        lines.append("")
    if entities:
        lines += ["## Related Entities", ""]
        for e in entities:
            lines.append(f"- [[entities/{e}]]")
        lines.append("")

    return WikiPage(
        kind="topic",
        slug=topic_id,
        title=name,
        frontmatter={"id": topic_id, "name": name},
        body="\n".join(lines),
    )


def normalize_claim(claim: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of a claim with controlled-vocab fields normalized + keys filled.

    Guarantees ``event_type`` and ``status`` sit in their controlled vocab and
    every akbp-shaped key is present, so stored claims have a stable shape
    regardless of what the enrichment LLM emitted.
    """
    c = dict(claim)
    c["event_type"] = normalize_event_type(c.get("event_type"))
    c["status"] = normalize_claim_status(c.get("status"))
    for key in ("id", "subject", "predicate", "object", "sentiment", "source_url", "quote"):
        c.setdefault(key, "")
    for key in ("confidence", "claim_date", "paragraph_index", "paragraph_hash", "superseded_by"):
        c.setdefault(key, None)
    return c


def _claim_bullet(claim: dict[str, Any]) -> list[str]:
    """Render one claim as markdown lines for the article body."""
    subject = str(claim.get("subject", "")).strip()
    predicate = str(claim.get("predicate", "")).strip()
    obj = str(claim.get("object", "")).strip().replace("\n", " ")
    event_type = normalize_event_type(claim.get("event_type"))
    sentiment = normalize_sentiment(claim.get("sentiment")) or "neut"
    confidence = claim.get("confidence")
    head = f"[[entities/{subject}]]" if subject else "(unresolved)"
    meta = f"*{event_type} · {sentiment}"
    if isinstance(confidence, (int, float)):
        meta += f" · conf {confidence:.2f}"
    meta += "*"
    out = [f"- {head} **{predicate}** {obj} — {meta}".rstrip()]
    quote = str(claim.get("quote", "")).strip()
    if quote:
        out.append(f"  > {quote}")
    src = str(claim.get("source_url", "")).strip()
    if src:
        cite = f"  — [source]({src})"
        pidx = claim.get("paragraph_index")
        if pidx is not None:
            cite += f" ¶{pidx}"
        out.append(cite)
    return out


def render_news_article_page(
    *,
    url: str,
    title: str,
    source: str,
    date: str,
    content_hash: str,
    tickers: list[str],
    entity_slugs: list[str],
    tags: list[str],
    claims: list[dict[str, Any]],
    paragraphs: list[dict[str, Any]],
    summary: str = "",
) -> WikiPage:
    """Render a fetched news article into a ``kind='news_article'`` WikiPage.

    ``frontmatter`` carries the akbp-shaped ``claims`` plus the denormalized
    ``tickers``/``event_types``/``date`` arrays the GIN index answers cheaply,
    and ``paragraphs`` (index + sha1 hash + text) — the citation store the
    context endpoint reads. The body is a digest view, not a reproduction of
    the source article.
    """
    norm_claims = [normalize_claim(c) for c in claims]

    event_types: list[str] = []
    for c in norm_claims:
        et = c["event_type"]
        if et not in event_types:
            event_types.append(et)

    frontmatter: dict[str, Any] = {
        "url": url,
        "title": title,
        "source": source,
        "date": date,
        "content_hash": content_hash,
        "tickers": [str(t) for t in tickers],
        "event_types": event_types,
        "tags": [str(t) for t in tags],
        "claims": norm_claims,
        "paragraphs": paragraphs,
    }

    lines: list[str] = [f"# {title}", ""]
    if summary:
        lines += [summary.strip(), ""]
    lines += [f"*Source: [{source}]({url}) — {date}*", ""]
    if norm_claims:
        lines += ["## Claims", ""]
        for c in norm_claims:
            lines += _claim_bullet(c)
        lines.append("")
    related = [f"- [[entities/{s}]]" for s in entity_slugs]
    related += [f"- [[topics/{slugify(tag)}]]" for tag in tags]
    if related:
        lines += ["## Related", "", *related, ""]

    return WikiPage(
        kind="news_article",
        slug=news_slug(url),
        title=title,
        frontmatter=frontmatter,
        body="\n".join(lines),
    )


def render_supply_chain_page(entity_slug: str, entity_name: str) -> WikiPage:
    body = f"# {entity_name} — Supply Chain\n\n## Downstream (Customers)\n"
    return WikiPage(
        kind="supply_chain",
        slug=entity_slug,
        title=f"{entity_name} — Supply Chain",
        frontmatter={"entity": entity_slug},
        body=body,
    )
