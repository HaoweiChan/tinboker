"""Markdown *views* over wiki records.

The database is the source of truth; markdown is reconstructed on demand here
(for the ``.md`` HTTP route, Obsidian exports, debugging). Nothing in the
storage path depends on this module.
"""

from __future__ import annotations

from typing import Iterable

import yaml

from .models import WikiPage


def page_to_markdown(page: WikiPage) -> str:
    """Reconstruct a single ``.md`` document from a record."""
    front = {"type": page.kind, **page.frontmatter}
    front_yaml = yaml.safe_dump(
        front, allow_unicode=True, sort_keys=False, default_flow_style=None
    ).strip()
    return f"---\n{front_yaml}\n---\n\n{page.body.strip()}\n"


def build_index_markdown(pages: Iterable[WikiPage]) -> str:
    """Render the equivalent of the old ``wiki/index.md`` from a page list."""
    by_kind: dict[str, list[WikiPage]] = {}
    for p in pages:
        by_kind.setdefault(p.kind, []).append(p)

    episodes = by_kind.get("episode", [])
    entities = by_kind.get("entity", [])
    topics = by_kind.get("topic", [])
    supply_chain = by_kind.get("supply_chain", [])

    lines = [
        "# Tinboker Knowledge Wiki",
        "",
        f"_Auto-generated index — {len(episodes)} episodes, "
        f"{len(entities)} entities, {len(topics)} topics_",
        "",
        "## Episodes",
        "",
    ]
    for ep in sorted(episodes, key=lambda p: str(p.frontmatter.get("date", "")), reverse=True):
        title = ep.title or ep.slug
        date = ep.frontmatter.get("date", "")
        tickers = [str(t) for t in ep.frontmatter.get("tickers", []) or []]
        suffix = f" — {', '.join(tickers)}" if tickers else ""
        lines.append(f"- [[episodes/{ep.slug}|{title}]] ({date}){suffix}")
    lines += ["", "## Entities", ""]
    for ent in sorted(entities, key=lambda p: (p.title or p.slug).lower()):
        etype = ent.frontmatter.get("entity_type", "")
        lines.append(f"- [[entities/{ent.slug}|{ent.title or ent.slug}]] ({etype})")
    lines += ["", "## Topics", ""]
    for t in sorted(topics, key=lambda p: (p.title or p.slug).lower()):
        lines.append(f"- [[topics/{t.slug}|{t.title or t.slug}]]")
    if supply_chain:
        lines += ["", "## Supply Chain Maps", ""]
        for sc in sorted(supply_chain, key=lambda p: p.slug):
            lines.append(f"- [[supply-chain/{sc.slug}|{sc.title or sc.slug}]]")
    lines.append("")
    return "\n".join(lines)
