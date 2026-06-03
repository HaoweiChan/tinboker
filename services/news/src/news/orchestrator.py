"""End-to-end news pipeline: RSS feeds → shared wiki.

Drives steps 1-7 for every feed in ``feeds.json``. Processing is best-effort
per article — one failing article is logged and skipped, never aborting the run.
The fetch / extract / LLM seams are injectable so the whole pipeline runs
offline under test.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from shared.wiki_builder import get_repository
from shared.wiki_builder.repository import WikiRepository

from .alias_index import build_alias_index
from .conflict import check_conflict
from .feeds import load_feeds
from .pipeline.steps.dedup import dedup, is_duplicate
from .pipeline.steps.dict_prepass import dict_prepass
from .pipeline.steps.extract import extract
from .pipeline.steps.fetch_feeds import fetch_feeds
from .pipeline.steps.llm_enrich import llm_enrich
from .pipeline.steps.resolve import resolve
from .pipeline.steps.wiki_write import wiki_write


@dataclass
class RunSummary:
    """Per-run counters reported at the end of an ingest run."""

    feed_entries: int = 0
    unique_articles: int = 0
    ingested: int = 0
    skipped: int = 0
    failed: int = 0

    def __str__(self) -> str:
        return (
            f"news run: {self.feed_entries} feed entries seen, "
            f"{self.unique_articles} unique, {self.ingested} ingested, "
            f"{self.skipped} skipped (unchanged), {self.failed} failed"
        )


def run(
    *,
    feeds_path: str | None = None,
    repository: WikiRepository | None = None,
    limit: int | None = None,
    parse: Callable[[str], Any] | None = None,
    fetch: Callable[[str], str | None] | None = None,
    extractor: Callable[[str], str | None] | None = None,
    llm: Callable[[str, str], dict] | None = None,
    detect_conflicts: bool = True,
) -> RunSummary:
    """Run the full pipeline and return a :class:`RunSummary`."""
    repo = repository or get_repository()
    feeds = load_feeds(feeds_path)
    entries = fetch_feeds(feeds, parse=parse)
    articles = dedup(entries, repo)
    if limit is not None:
        articles = articles[:limit]

    index = build_alias_index(repo)
    summary = RunSummary(feed_entries=len(entries), unique_articles=len(articles))

    conflict_checker: Callable[[dict, dict], bool] | None = None
    if detect_conflicts:
        def conflict_checker(new_row: dict, old_row: dict) -> bool:
            return check_conflict(new_row, old_row, llm=llm)

    for article in articles:
        try:
            extract(article, fetch=fetch, extractor=extractor)
            if is_duplicate(article):
                summary.skipped += 1
                continue
            dict_prepass(article, index)
            llm_enrich(article, index, llm=llm)
            resolve(article, index, llm=llm)
            wiki_write(article, repo, conflict_checker=conflict_checker)
            summary.ingested += 1
            print(f"  ✓ ingested: {article.title}  ({len(article.claims)} claims)")
        except Exception as exc:  # noqa: BLE001 — one bad article must not abort the run
            summary.failed += 1
            print(f"  ⚠ article failed ({article.url}): {exc}")

    print(summary)
    return summary
