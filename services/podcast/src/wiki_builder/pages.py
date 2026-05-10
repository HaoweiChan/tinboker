"""Markdown page generators for the wiki.

Each function returns the full markdown text for a page.
"""

from datetime import datetime
from typing import Any

from .slugify import episode_slug, ticker_slug, slugify


def render_episode_page(
    podcast_name: str,
    episode_number: int | None,
    title: str,
    date: str,
    tickers: list[str],
    tags: list[str],
    summary_text: str,
    events_markdown: str | None,
    ticker_recommendations: dict[str, Any] | None,
    source_urls: dict[str, str] | None,
) -> str:
    """Render a full episode wiki page."""
    slug = episode_slug(podcast_name, episode_number, title)
    quoted = [f'"{t}"' if t.isdigit() else t for t in tickers]
    tickers_yaml = ", ".join(quoted) if quoted else ""
    tags_yaml = ", ".join(tags) if tags else ""

    lines = [
        "---",
        "type: episode",
        f"podcast: {podcast_name}",
    ]
    if episode_number is not None:
        lines.append(f"episode_number: {episode_number}")
    lines += [
        f"title: \"{title}\"",
        f"date: {date}",
        f"tickers: [{tickers_yaml}]",
        f"tags: [{tags_yaml}]",
    ]
    if source_urls:
        lines.append("source_urls:")
        for key, url in source_urls.items():
            if url:
                lines.append(f"  {key}: {url}")
    lines += ["---", "", f"# {title}", ""]

    # Summary body
    if summary_text:
        lines.append(summary_text.strip())
        lines.append("")

    # Events section
    if events_markdown:
        lines += ["## Events Timeline", "", events_markdown.strip(), ""]

    # Ticker recommendations table
    if ticker_recommendations:
        recs = ticker_recommendations.get("ticker_recommendations", [])
        if recs:
            lines += ["## Ticker Recommendations", ""]
            lines.append("| Ticker | Sentiment | Score | Time Horizon | Thesis |")
            lines.append("|--------|-----------|-------|--------------|--------|")
            for rec in recs:
                t = rec.get("ticker", "")
                sent = rec.get("sentiment", "")
                score = rec.get("sentiment_score", "")
                horizon = rec.get("time_horizon", "")
                thesis = rec.get("bluf_thesis", "").replace("|", "—")
                lines.append(f"| {t} | {sent} | {score} | {horizon} | {thesis} |")
            lines.append("")

    # Related links
    related: list[str] = []
    for t in tickers:
        related.append(f"- [[entities/{ticker_slug(t)}]]")
    for tag in tags:
        related.append(f"- [[topics/{slugify(tag)}]]")
    if related:
        lines += ["## Related", ""] + related + [""]

    return "\n".join(lines)


def render_entity_page(
    entity_id: str,
    name: str,
    entity_type: str,
    tickers: list[str],
    mentions: list[dict[str, str]],
    ticker_history: list[dict[str, Any]],
    supply_upstream: list[dict[str, str]] | None = None,
    supply_downstream: list[dict[str, str]] | None = None,
) -> str:
    """Render or update an entity wiki page."""
    tickers_yaml = ", ".join(tickers) if tickers else ""

    lines = [
        "---",
        "type: entity",
        f"id: {entity_id}",
        f"name: \"{name}\"",
        f"entity_type: {entity_type}",
        f"tickers: [{tickers_yaml}]",
        "---",
        "",
        f"# {name}",
        "",
    ]

    # Episode mentions
    if mentions:
        lines += ["## Episode Mentions", ""]
        for m in mentions:
            ep = m.get("episode_link", "")
            ctx = m.get("context", "")
            lines.append(f"- [[{ep}]] — {ctx}")
        lines.append("")

    # Supply chain
    if supply_upstream or supply_downstream:
        lines.append("## Supply Chain")
        lines.append("")
        if supply_upstream:
            for s in supply_upstream:
                lines.append(f"- Supplied by: [[entities/{s['slug']}]] — {s.get('rel', '')}")
        if supply_downstream:
            for s in supply_downstream:
                lines.append(f"- Supplies to: [[entities/{s['slug']}]] — {s.get('rel', '')}")
        lines.append("")

    # Ticker history
    if ticker_history:
        lines += ["## Ticker History", ""]
        lines.append("| Date | Sentiment | Score | Thesis |")
        lines.append("|------|-----------|-------|--------|")
        for h in ticker_history:
            lines.append(
                f"| {h.get('date', '')} | {h.get('sentiment', '')} "
                f"| {h.get('score', '')} | {h.get('thesis', '').replace('|', '—')} |"
            )
        lines.append("")

    return "\n".join(lines)


def render_topic_page(
    topic_id: str,
    name: str,
    episodes: list[dict[str, str]],
    entities: list[str],
) -> str:
    """Render a topic wiki page."""
    lines = [
        "---",
        "type: topic",
        f"id: {topic_id}",
        f"name: \"{name}\"",
        "---",
        "",
        f"# {name}",
        "",
    ]

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

    return "\n".join(lines)
