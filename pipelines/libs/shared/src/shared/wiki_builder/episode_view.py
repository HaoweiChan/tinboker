"""Read episode wiki pages into the shapes the platform webui's episode feed / detail want.

Parses the rendered markdown body back into structured pieces (summary excerpt, events timeline,
ticker-recommendation table, related links) and combines them with the frontmatter. Content-shape
aware (like :mod:`.records` / :mod:`.stats`); the storage layer stays agnostic.
"""

from __future__ import annotations

import re
from typing import Any

from ..tickers import canonical_symbol
from .models import WikiPage
from .records import normalize_sentiment
from .slugify import ticker_slug

_REC_HEADER = "## Ticker Recommendations"
_EVENTS_HEADER = "## Events Timeline"
_WIKILINK_RE = re.compile(r"\[\[(entities|topics)/([^\]|]+?)(?:\|[^\]]*)?\]\]")

# slug -> that page's frontmatter dict (used to resolve display names)
NameMap = dict[str, dict[str, Any]]


def _section(body: str, header: str) -> str:
    """Return the text under ``header`` up to the next ``## ...`` heading (stripped)."""
    lines = body.splitlines()
    try:
        start = next(i for i, ln in enumerate(lines) if ln.strip() == header)
    except StopIteration:
        return ""
    out: list[str] = []
    for ln in lines[start + 1 :]:
        if ln.strip().startswith("## "):
            break
        out.append(ln)
    return "\n".join(out).strip()


def summary_text(body: str) -> str:
    """The prose between the ``# title`` heading and the first ``## ...`` section."""
    lines = body.splitlines()
    out: list[str] = []
    started = False
    for ln in lines:
        s = ln.strip()
        if not started:
            if s.startswith("# "):  # the H1 title line
                started = True
            continue
        if s.startswith("## "):
            break
        out.append(ln)
    return "\n".join(out).strip()


def parse_ticker_recommendations(body: str) -> list[dict[str, Any]]:
    """Parse the ``## Ticker Recommendations`` markdown table into structured rows.

    Returns ``[{sym, sentiment, sentiment_score, time_horizon, thesis}]`` — ``sym`` is the
    canonical symbol, ``sentiment`` is normalized (bull|bear|neut|"").
    """
    rows: list[dict[str, Any]] = []
    section = _section(body, _REC_HEADER)
    for raw in section.splitlines():
        s = raw.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if not cells or cells[0].lower() in {"ticker", ""} or set("".join(cells)) <= set("-: "):
            continue  # header / separator row
        ticker, sentiment = cells[0], (cells[1] if len(cells) > 1 else "")
        score = cells[2] if len(cells) > 2 else ""
        horizon = cells[3] if len(cells) > 3 else ""
        thesis = cells[4] if len(cells) > 4 else ""
        if not ticker:
            continue
        rows.append(
            {
                "sym": canonical_symbol(ticker),
                "sentiment": normalize_sentiment(sentiment),
                "sentiment_raw": sentiment,
                "sentiment_score": score,
                "time_horizon": horizon,
                "thesis": thesis,
            }
        )
    return rows


def _related(body: str) -> dict[str, list[str]]:
    entities: list[str] = []
    topics: list[str] = []
    for kind, target in _WIKILINK_RE.findall(body):
        slug = target.strip()
        bucket = entities if kind == "entities" else topics
        if slug and slug not in bucket:
            bucket.append(slug)
    return {"entities": entities, "topics": topics}


def _tickers(page: WikiPage, entity_names: NameMap | None) -> list[dict[str, Any]]:
    names = entity_names or {}
    raw_sentiment = page.frontmatter.get("ticker_sentiment") or {}
    sentiment_map = {canonical_symbol(str(k)): str(v) for k, v in raw_sentiment.items()}
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in page.frontmatter.get("tickers") or []:
        sym = canonical_symbol(str(raw))
        if not sym or sym in seen:
            continue
        seen.add(sym)
        meta = names.get(ticker_slug(sym), {})
        out.append(
            {
                "sym": sym,
                "slug": ticker_slug(sym),
                "name": meta.get("name", sym),
                "market": meta.get("market"),
                "sentiment": sentiment_map.get(sym),
            }
        )
    return out


def feed_item(page: WikiPage, entity_names: NameMap | None = None) -> dict[str, Any]:
    """A compact episode record for the feed/list views."""
    fm = page.frontmatter
    body = page.body
    summary = summary_text(body)
    return {
        "slug": page.slug,
        "podcast": str(fm.get("podcast", "")),
        "episode_number": fm.get("episode_number"),
        "title": page.title or fm.get("title", page.slug),
        "date": fm.get("date"),
        "duration_minutes": fm.get("duration_minutes"),
        "summary_excerpt": (summary[:280] + "…") if len(summary) > 280 else summary,
        "tickers": _tickers(page, entity_names),
        "tags": [str(t) for t in (fm.get("tags") or [])],
        "source_urls": fm.get("source_urls") or {},
    }


def _named_links(slugs: list[str], names: NameMap) -> list[dict[str, str]]:
    return [{"slug": s, "name": names.get(s, {}).get("name", s)} for s in slugs]


def episode_detail(
    page: WikiPage,
    entity_names: NameMap | None = None,
    topic_names: NameMap | None = None,
) -> dict[str, Any]:
    """The full episode detail record (everything the detail page needs that we have today)."""
    fm = page.frontmatter
    body = page.body
    recs = parse_ticker_recommendations(body)
    rec_by_sym = {r["sym"]: r for r in recs}
    tickers = _tickers(page, entity_names)
    for t in tickers:  # attach the thesis / score / horizon onto the ticker rows
        rec = rec_by_sym.get(t["sym"])
        if rec:
            t["thesis"] = rec["thesis"]
            t["sentiment_score"] = rec["sentiment_score"]
            t["time_horizon"] = rec["time_horizon"]
    related = _related(body)
    return {
        "slug": page.slug,
        "podcast": str(fm.get("podcast", "")),
        "episode_number": fm.get("episode_number"),
        "title": page.title or fm.get("title", page.slug),
        "date": fm.get("date"),
        "duration_minutes": fm.get("duration_minutes"),
        "summary": summary_text(body),
        "events_markdown": _section(body, _EVENTS_HEADER) or None,
        "ticker_recommendations": recs,
        "tickers": tickers,
        "tags": [str(t) for t in (fm.get("tags") or [])],
        "source_urls": fm.get("source_urls") or {},
        "related": {
            "entities": _named_links(related["entities"], entity_names or {}),
            "topics": _named_links(related["topics"], topic_names or {}),
        },
        # TODO (roadmap slice D): the content pipeline doesn't yet emit these.
        "bullets": [],
        "chapters": [],
        "clips": [],
    }
