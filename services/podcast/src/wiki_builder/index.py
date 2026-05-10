"""Rebuild the wiki index.md from the current wiki contents."""

import re
from pathlib import Path
from typing import Optional

import yaml


WIKI_ROOT = Path(__file__).resolve().parents[3] / "wiki"


def _parse_frontmatter(text: str) -> dict:
    m = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    if not m:
        return {}
    try:
        return yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return {}


def _collect_pages(directory: Path) -> list[dict]:
    """Collect all markdown pages from a directory with their frontmatter."""
    pages = []
    if not directory.exists():
        return pages
    for f in sorted(directory.glob("*.md")):
        fm = _parse_frontmatter(f.read_text(encoding="utf-8"))
        fm["_filename"] = f.stem
        fm["_path"] = f.relative_to(directory.parent)
        pages.append(fm)
    return pages


def rebuild_index(wiki_root: Optional[Path] = None) -> Path:
    """Rebuild wiki/index.md from the current wiki contents.

    Returns the path to index.md.
    """
    root = wiki_root or WIKI_ROOT
    root.mkdir(parents=True, exist_ok=True)

    episodes = _collect_pages(root / "episodes")
    entities = _collect_pages(root / "entities")
    topics = _collect_pages(root / "topics")
    supply_chain = _collect_pages(root / "supply-chain")

    lines = [
        "# Tinboker Knowledge Wiki",
        "",
        f"_Auto-generated index — {len(episodes)} episodes, "
        f"{len(entities)} entities, {len(topics)} topics_",
        "",
    ]

    # Episodes (sorted by date descending)
    lines += ["## Episodes", ""]
    episodes_sorted = sorted(episodes, key=lambda p: p.get("date", ""), reverse=True)
    for ep in episodes_sorted:
        title = ep.get("title", ep["_filename"])
        date = ep.get("date", "")
        tickers = [str(t) for t in ep.get("tickers", []) or []]
        ticker_str = f" — {', '.join(tickers)}" if tickers else ""
        lines.append(f"- [[{ep['_path']}|{title}]] ({date}){ticker_str}")
    lines.append("")

    # Entities (sorted by name)
    lines += ["## Entities", ""]
    entities_sorted = sorted(entities, key=lambda p: p.get("name", p["_filename"]))
    for ent in entities_sorted:
        name = ent.get("name", ent["_filename"])
        etype = ent.get("entity_type", "")
        lines.append(f"- [[{ent['_path']}|{name}]] ({etype})")
    lines.append("")

    # Topics (sorted by name)
    lines += ["## Topics", ""]
    topics_sorted = sorted(topics, key=lambda p: p.get("name", p["_filename"]))
    for t in topics_sorted:
        name = t.get("name", t["_filename"])
        lines.append(f"- [[{t['_path']}|{name}]]")
    lines.append("")

    # Supply chain maps
    if supply_chain:
        lines += ["## Supply Chain Maps", ""]
        for sc in sorted(supply_chain, key=lambda p: p.get("entity", p["_filename"])):
            entity = sc.get("entity", sc["_filename"])
            lines.append(f"- [[{sc['_path']}|{entity}]]")
        lines.append("")

    index_path = root / "index.md"
    index_path.write_text("\n".join(lines), encoding="utf-8")
    return index_path
