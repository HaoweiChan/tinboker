"""Ingest episode data into the wiki.

Main entry point: ``ingest_episode`` takes the same data available after
the podcast summarization step and writes/updates the relevant wiki pages.
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from .slugify import episode_slug, ticker_slug, slugify
from .pages import render_episode_page, render_entity_page, render_topic_page


WIKI_ROOT = Path(__file__).resolve().parents[3] / "wiki"


def _parse_frontmatter(text: str) -> dict:
    """Extract YAML frontmatter from a markdown page."""
    m = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    if not m:
        return {}
    try:
        return yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return {}


def _read_page(path: Path) -> str | None:
    if path.exists():
        return path.read_text(encoding="utf-8")
    return None


def _ensure_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _append_mention_to_entity(
    entity_path: Path,
    episode_link: str,
    context: str,
) -> None:
    """Append an episode mention to an existing entity page (idempotent)."""
    content = _read_page(entity_path)
    if content is None:
        return
    if episode_link in content:
        return
    marker = "## Episode Mentions"
    if marker in content:
        idx = content.index(marker) + len(marker)
        insert_line = f"\n- [[{episode_link}]] — {context}"
        content = content[:idx] + insert_line + content[idx:]
    else:
        content += f"\n## Episode Mentions\n\n- [[{episode_link}]] — {context}\n"
    entity_path.write_text(content, encoding="utf-8")


def _append_ticker_history(
    entity_path: Path,
    date: str,
    sentiment: str,
    score: Any,
    thesis: str,
) -> None:
    """Append a ticker history row to an existing entity page (idempotent)."""
    content = _read_page(entity_path)
    if content is None:
        return
    row = f"| {date} | {sentiment} | {score} | {thesis.replace('|', '—')} |"
    if row in content:
        return
    marker = "## Ticker History"
    if marker in content:
        # Find the end of the table header (two lines after marker)
        idx = content.index(marker)
        rest = content[idx:]
        lines = rest.split("\n")
        insert_pos = idx
        for i, line in enumerate(lines):
            insert_pos = idx + sum(len(l) + 1 for l in lines[:i + 1])
            if line.startswith("|---"):
                insert_pos = idx + sum(len(l) + 1 for l in lines[:i + 1])
                break
        # Find the last table row
        for i in range(len(lines) - 1, 0, -1):
            if lines[i].startswith("|"):
                insert_pos = idx + sum(len(l) + 1 for l in lines[:i + 1])
                break
        content = content[:insert_pos] + row + "\n" + content[insert_pos:]
    else:
        content += (
            f"\n## Ticker History\n\n"
            f"| Date | Sentiment | Score | Thesis |\n"
            f"|------|-----------|-------|--------|\n"
            f"{row}\n"
        )
    entity_path.write_text(content, encoding="utf-8")


def _append_episode_to_topic(
    topic_path: Path,
    episode_link: str,
    context: str,
) -> None:
    """Append an episode link to an existing topic page (idempotent)."""
    content = _read_page(topic_path)
    if content is None:
        return
    if episode_link in content:
        return
    marker = "## Episodes"
    if marker in content:
        idx = content.index(marker) + len(marker)
        insert_line = f"\n- [[{episode_link}]] — {context}"
        content = content[:idx] + insert_line + content[idx:]
    else:
        content += f"\n## Episodes\n\n- [[{episode_link}]] — {context}\n"
    topic_path.write_text(content, encoding="utf-8")


def ingest_episode(
    podcast_name: str,
    episode_number: Optional[int],
    title: str,
    date: Optional[str],
    tickers: List[str],
    tags: List[str],
    summary_text: str,
    events_markdown: Optional[str] = None,
    ticker_recommendations: Optional[Dict[str, Any]] = None,
    source_urls: Optional[Dict[str, str]] = None,
    wiki_root: Optional[Path] = None,
) -> Path:
    """Write episode data into the wiki.

    Creates/overwrites the episode page and creates/updates entity and topic
    pages referenced by the episode.

    Returns the path to the written episode page.
    """
    root = wiki_root or WIKI_ROOT
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")

    ep_slug = episode_slug(podcast_name, episode_number, title)
    ep_link = f"episodes/{ep_slug}"

    # 1. Write episode page
    ep_path = root / "episodes" / f"{ep_slug}.md"
    _ensure_dir(ep_path)
    ep_content = render_episode_page(
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
    ep_path.write_text(ep_content, encoding="utf-8")

    # 2. Create/update entity pages for each ticker
    recs = (ticker_recommendations or {}).get("ticker_recommendations", [])
    recs_by_ticker = {r["ticker"].upper(): r for r in recs if "ticker" in r}

    for t in tickers:
        t_slug = ticker_slug(t)
        entity_path = root / "entities" / f"{t_slug}.md"
        _ensure_dir(entity_path)

        if not entity_path.exists():
            entity_content = render_entity_page(
                entity_id=t_slug,
                name=t.upper(),
                entity_type="company",
                tickers=[t.upper()],
                mentions=[{"episode_link": ep_link, "context": title}],
                ticker_history=[],
            )
            entity_path.write_text(entity_content, encoding="utf-8")
        else:
            _append_mention_to_entity(entity_path, ep_link, title)

        rec = recs_by_ticker.get(t.upper())
        if rec:
            _append_ticker_history(
                entity_path,
                date=date,
                sentiment=rec.get("sentiment", ""),
                score=rec.get("sentiment_score", ""),
                thesis=rec.get("bluf_thesis", ""),
            )

    # 3. Create/update topic pages for each tag
    for tag in tags:
        t_slug = slugify(tag)
        topic_path = root / "topics" / f"{t_slug}.md"
        _ensure_dir(topic_path)

        if not topic_path.exists():
            entity_slugs = [ticker_slug(t) for t in tickers]
            topic_content = render_topic_page(
                topic_id=t_slug,
                name=tag,
                episodes=[{"link": ep_link, "context": title}],
                entities=entity_slugs,
            )
            topic_path.write_text(topic_content, encoding="utf-8")
        else:
            _append_episode_to_topic(topic_path, ep_link, title)

    return ep_path


def ingest_supply_chain(
    entities: list[dict],
    edges: list[dict],
    evidence: list[dict],
    wiki_root: Optional[Path] = None,
) -> int:
    """Ingest supply-chain data from the knowledge-graph pipeline.

    Updates entity pages with supply-chain relationships and creates
    supply-chain map pages.

    Returns the number of pages written/updated.
    """
    root = wiki_root or WIKI_ROOT
    count = 0

    entity_map = {e["id"]: e for e in entities}

    for edge in edges:
        src_id = edge.get("src", "")
        dst_id = edge.get("dst", "")
        rel = edge.get("rel", "RELATED_TO")
        status = edge.get("props", {}).get("status", "active")

        src_entity = entity_map.get(src_id, {})
        dst_entity = entity_map.get(dst_id, {})
        src_name = src_entity.get("props", {}).get("name", src_id)
        dst_name = dst_entity.get("props", {}).get("name", dst_id)

        src_slug = slugify(src_name)
        dst_slug = slugify(dst_name)

        # Ensure entity pages exist
        for eid, ename, eslug in [(src_id, src_name, src_slug), (dst_id, dst_name, dst_slug)]:
            epath = root / "entities" / f"{eslug}.md"
            _ensure_dir(epath)
            if not epath.exists():
                etype = entity_map.get(eid, {}).get("type", "company")
                entity_content = render_entity_page(
                    entity_id=eslug,
                    name=ename,
                    entity_type=etype,
                    tickers=[],
                    mentions=[],
                    ticker_history=[],
                )
                epath.write_text(entity_content, encoding="utf-8")
                count += 1

        # Write supply-chain page for source entity
        sc_path = root / "supply-chain" / f"{src_slug}.md"
        _ensure_dir(sc_path)
        content = _read_page(sc_path) or ""

        rel_line = f"[[entities/{dst_slug}]] — {rel} ({status})"
        if rel_line not in content:
            if not content:
                content = (
                    f"---\ntype: supply_chain\nentity: {src_slug}\n---\n\n"
                    f"# {src_name} — Supply Chain\n\n"
                    f"## Downstream (Customers)\n\n"
                )
            if "## Downstream" not in content:
                content += "\n## Downstream (Customers)\n\n"
            content += f"- {rel_line}\n"
            sc_path.write_text(content, encoding="utf-8")
            count += 1

    return count
