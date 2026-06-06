"""Content-derived aggregates over the wiki — for the platform webui's dashboards.

Everything here is computed on the fly from ``wiki_pages`` (episode/entity/topic) — episode
dates, ``tickers``/``tags`` membership, and the ``ticker_sentiment`` map written by
``ingest_episode``. No pipeline changes; for now it re-reads the (small) page set per call.

Used by the ``/api/wiki/stats/*`` routes on the podcast service. Knows about episodes / tickers /
sentiment — that's content shape, like :mod:`.records` / :mod:`.ingest` — but never touches the
storage layer's internals.
"""

from __future__ import annotations

from collections import Counter
from datetime import date, timedelta
from typing import Any

from ..tickers import canonical_symbol
from .repository import WikiRepository
from .slugify import slugify, ticker_slug

SENTIMENT_KEYS = ("bull", "bear", "neut")


# --- internal helpers ----------------------------------------------------
def _parse_date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        return None


def _episodes(repo: WikiRepository) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for p in repo.list_pages(kind="episode", limit=1_000_000):
        fm = p.frontmatter
        out.append(
            {
                "slug": p.slug,
                "title": p.title or fm.get("title", p.slug),
                "podcast": str(fm.get("podcast", "")),
                "date": _parse_date(fm.get("date")),
                "tickers": [canonical_symbol(str(t)) for t in (fm.get("tickers") or [])],
                "tags": [str(t) for t in (fm.get("tags") or [])],
                "sentiment": {
                    canonical_symbol(str(k)): str(v)
                    for k, v in (fm.get("ticker_sentiment") or {}).items()
                },
            }
        )
    return out


def _ref_date(episodes: list[dict[str, Any]], as_of: date | None) -> date:
    if as_of is not None:
        return as_of
    dates = [e["date"] for e in episodes if e["date"]]
    return max(dates) if dates else date.today()


def _within(
    episodes: list[dict[str, Any]], days: int | None, as_of: date | None
) -> list[dict[str, Any]]:
    if not days:
        return episodes
    ref = _ref_date(episodes, as_of)
    start = ref - timedelta(days=days)
    return [e for e in episodes if e["date"] and start <= e["date"] <= ref]


def _zero_dist() -> dict[str, int]:
    return {k: 0 for k in SENTIMENT_KEYS}


def _pages_frontmatter(repo: WikiRepository, kind: str) -> dict[str, dict[str, Any]]:
    return {p.slug: dict(p.frontmatter) for p in repo.list_pages(kind=kind, limit=1_000_000)}


def _dominant(counter: Counter) -> str | None:
    relevant = [(k, v) for k, v in counter.items() if k in SENTIMENT_KEYS and v]
    return max(relevant, key=lambda kv: kv[1])[0] if relevant else None


# --- public aggregates ---------------------------------------------------
def top_tickers(
    repo: WikiRepository, *, days: int = 7, limit: int = 10, as_of: date | None = None
) -> list[dict[str, Any]]:
    """Tickers ranked by # episodes mentioning them in the window, with a sentiment split."""
    episodes = _within(_episodes(repo), days, as_of)
    mentions: Counter = Counter()
    dists: dict[str, Counter] = {}
    for ep in episodes:
        for sym in set(ep["tickers"]):
            mentions[sym] += 1
            sent = ep["sentiment"].get(sym)
            if sent in SENTIMENT_KEYS:
                dists.setdefault(sym, Counter())[sent] += 1
    entities = _pages_frontmatter(repo, "entity")
    rows: list[dict[str, Any]] = []
    for sym, count in mentions.most_common(limit):
        meta = entities.get(ticker_slug(sym), {})
        dist = {k: dists.get(sym, Counter()).get(k, 0) for k in SENTIMENT_KEYS}
        rows.append(
            {
                "sym": sym,
                "slug": ticker_slug(sym),
                "name": meta.get("name", sym),
                "market": meta.get("market"),
                "sector": meta.get("sector"),
                "mentions": count,
                "dist": dist,
            }
        )
    return rows


def top_shows(
    repo: WikiRepository, *, days: int = 7, limit: int = 10, as_of: date | None = None
) -> list[dict[str, Any]]:
    """Podcasts ranked by # episodes in the window, with delta vs. the previous equal window."""
    episodes = _episodes(repo)
    ref = _ref_date(episodes, as_of)
    cur: Counter = Counter()
    prev: Counter = Counter()
    for ep in episodes:
        d = ep["date"]
        if not d or not ep["podcast"]:
            continue
        if ref - timedelta(days=days) <= d <= ref:
            cur[ep["podcast"]] += 1
        elif ref - timedelta(days=2 * days) <= d < ref - timedelta(days=days):
            prev[ep["podcast"]] += 1
    rows: list[dict[str, Any]] = []
    for show, count in cur.most_common(limit):
        before = prev.get(show, 0)
        delta_pct = round((count - before) / before * 100) if before else None
        rows.append(
            {"podcast": show, "episodes": count, "prev_episodes": before, "delta_pct": delta_pct}
        )
    return rows


def topics(
    repo: WikiRepository, *, days: int | None = None, limit: int = 20, as_of: date | None = None
) -> list[dict[str, Any]]:
    """Topics ranked by # episodes, with a normalized weight and a dominant sentiment."""
    episodes = _within(_episodes(repo), days, as_of)
    counts: Counter = Counter()
    sentiments: dict[str, Counter] = {}
    for ep in episodes:
        ep_dominant = _dominant(Counter(v for v in ep["sentiment"].values() if v in SENTIMENT_KEYS))
        for tag in set(ep["tags"]):
            counts[tag] += 1
            if ep_dominant:
                sentiments.setdefault(tag, Counter())[ep_dominant] += 1
    if not counts:
        return []
    max_count = max(counts.values())
    topic_meta = _pages_frontmatter(repo, "topic")
    rows: list[dict[str, Any]] = []
    for tag, count in counts.most_common(limit):
        slug = slugify(tag)
        rows.append(
            {
                "tag": tag,
                "slug": slug,
                "name": topic_meta.get(slug, {}).get("name", tag),
                "count": count,
                "weight": round(count / max_count, 3),
                "sentiment": _dominant(sentiments.get(tag, Counter())) or "neut",
            }
        )
    return rows


def pulse(repo: WikiRepository, *, on_date: date | None = None) -> dict[str, Any]:
    """One day's activity: episodes, distinct tickers mentioned, and overall sentiment split."""
    episodes = _episodes(repo)
    ref = _ref_date(episodes, on_date)
    day_eps = [e for e in episodes if e["date"] == ref]
    tickers: set[str] = set()
    dist: Counter = Counter()
    for ep in day_eps:
        tickers.update(ep["tickers"])
        for sent in ep["sentiment"].values():
            if sent in SENTIMENT_KEYS:
                dist[sent] += 1
    sentiment = {k: dist.get(k, 0) for k in SENTIMENT_KEYS}
    sentiment["dominant"] = _dominant(dist) or "neut"
    return {
        "date": ref.isoformat(),
        "episode_count": len(day_eps),
        "ticker_count": len(tickers),
        "sentiment": sentiment,
    }


def entity_aggregate(
    repo: WikiRepository, slug: str, *, days: int | None = None
) -> dict[str, Any] | None:
    """Per-entity rollup: mention counts, last-mentioned-at, sentiment split, recent episodes."""
    page = repo.get_page("entity", slug)
    if page is None:
        return None
    episodes = _episodes(repo)
    mentioning = [e for e in episodes if any(ticker_slug(t) == slug for t in e["tickers"])]
    if days:
        ref = _ref_date(episodes, None)
        start = ref - timedelta(days=days)
        windowed = [e for e in mentioning if e["date"] and start <= e["date"] <= ref]
    else:
        windowed = mentioning
    dist: Counter = Counter()
    for ep in windowed:
        for sym in ep["tickers"]:
            if ticker_slug(sym) == slug and ep["sentiment"].get(sym) in SENTIMENT_KEYS:
                dist[ep["sentiment"][sym]] += 1
    dated = sorted((e for e in mentioning if e["date"]), key=lambda e: e["date"], reverse=True)
    recent: list[dict[str, Any]] = []
    for e in sorted(
        windowed, key=lambda e: (e["date"] is not None, e["date"] or date.min), reverse=True
    )[:10]:
        match_sym = next((s for s in e["tickers"] if ticker_slug(s) == slug), "")
        recent.append(
            {
                "slug": e["slug"],
                "title": e["title"],
                "podcast": e["podcast"],
                "date": e["date"].isoformat() if e["date"] else None,
                "sentiment": e["sentiment"].get(match_sym),
            }
        )
    fm = page.frontmatter
    return {
        "slug": slug,
        "name": fm.get("name", slug),
        "market": fm.get("market"),
        "sector": fm.get("sector"),
        "entity_type": fm.get("entity_type"),
        "mentions": len(windowed),
        "total_mentions": len(mentioning),
        "last_mentioned_at": dated[0]["date"].isoformat() if dated else None,
        "dist": {k: dist.get(k, 0) for k in SENTIMENT_KEYS},
        "recent_episodes": recent,
    }
