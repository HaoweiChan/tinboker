#!/usr/bin/env python3
"""Phase C: backfill the tinboker_wiki content tables from the Firestore mirror.

Backfill order (each step idempotent via upsert):
  1. podcasts          — derived from unique podcast_name values in the mirror
  2. tickers           — from tickers.json registry (every canonical symbol)
  3. episodes          — from firestore_mirror.episodes (doc JSONB)
  4. ticker_insights   — download GCS JSON per episode → build_episode_insight_docs
  5. trending_tickers  — aggregated in-memory from the insights collected in step 4

Requires env vars:
    WIKI_DATABASE_URL          target: tinboker_wiki (postgresql+psycopg://...)
    EPISODE_DATABASE_URL       source: podcast_db mirror (postgresql:// or postgresql+psycopg://)
    GOOGLE_APPLICATION_CREDENTIALS  for GCS downloads (step 4 only; skip with --skip-insights)

Usage:
    uv run python services/podcast/scripts/backfill_mirror_to_content_store.py --dry-run
    uv run python services/podcast/scripts/backfill_mirror_to_content_store.py --limit 20
    uv run python services/podcast/scripts/backfill_mirror_to_content_store.py --skip-insights
    uv run python services/podcast/scripts/backfill_mirror_to_content_store.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Make shared importable when run as a plain script (also pip-installed in venv)
_REPO_ROOT = Path(__file__).resolve().parents[3]
_SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "libs" / "shared" / "src"))
sys.path.insert(0, str(_SERVICE_ROOT / "src"))

from podcast.exporters.ticker_insights import build_episode_insight_docs  # noqa: E402
from podcast.exporters.trending_tickers import aggregate_trending  # noqa: E402
from shared.db import (  # noqa: E402
    Episode,
    Podcast,
    Ticker,
    TickerInsight,
    TrendingTicker,
    get_repositories,
)
from shared.tickers import _index as ticker_index  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ts_to_ms(ts: datetime | None) -> int | None:
    if ts is None:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return int(ts.timestamp() * 1000)


def _date_to_ms(date_str: str | None) -> int | None:
    if not date_str:
        return None
    try:
        dt = datetime.strptime(date_str[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)
    except ValueError:
        return None


def _is_zh(name: str) -> bool:
    return any("一" <= ch <= "鿿" for ch in (name or ""))


def _extract_image_urls(images: object) -> list[str]:
    if not isinstance(images, list):
        return []
    out = []
    for img in images:
        if isinstance(img, str):
            out.append(img)
        elif isinstance(img, dict):
            url = img.get("url")
            if url:
                out.append(str(url))
    return out


def _read_gcs_json(gs_url: str) -> object | None:
    if not gs_url or not gs_url.startswith("gs://"):
        return None
    bucket, _, path = gs_url[5:].partition("/")
    from google.cloud import storage  # type: ignore[import-untyped]
    try:
        blob = storage.Client().bucket(bucket).blob(path)
        return json.loads(blob.download_as_text(encoding="utf-8"))
    except Exception:
        return None  # caller handles


# ---------------------------------------------------------------------------
# Step builders
# ---------------------------------------------------------------------------

def _build_episode(row: dict) -> Episode:
    doc: dict = row.get("doc") or {}
    episode_id: str = row["episode_id"]
    podcast_name: str = row["podcast_name"]

    created_time_ts: datetime | None = row.get("created_time")
    created_time_ms = _ts_to_ms(created_time_ts)

    spotify_release_date = doc.get("spotify_release_date")
    released_at_ms = _date_to_ms(spotify_release_date)

    raw_tickers = row.get("related_tickers")
    if isinstance(raw_tickers, list):
        related_tickers = [str(t) for t in raw_tickers if t]
    elif isinstance(raw_tickers, str):
        try:
            related_tickers = json.loads(raw_tickers)
        except Exception:
            related_tickers = []
    else:
        related_tickers = []

    raw_tags = doc.get("tags") or []
    tags = [str(t) for t in raw_tags if t] if isinstance(raw_tags, list) else []

    ep_num = doc.get("episode_number")
    try:
        episode_number = int(ep_num) if ep_num is not None else None
    except (TypeError, ValueError):
        episode_number = None

    spotify_dur = doc.get("spotify_duration_ms")
    try:
        spotify_duration_ms = int(spotify_dur) if spotify_dur is not None else None
    except (TypeError, ValueError):
        spotify_duration_ms = None

    return Episode(
        id=episode_id,
        podcast_name=podcast_name,
        episode_title=doc.get("episode_title") or doc.get("title"),
        episode_number=episode_number,
        created_time=created_time_ms,
        released_at_ms=released_at_ms,
        spotify_id=doc.get("spotify_id"),
        spotify_url=doc.get("spotify_url"),
        spotify_embed_url=doc.get("spotify_embed_url"),
        spotify_release_date=spotify_release_date,
        spotify_description=doc.get("spotify_description"),
        spotify_duration_ms=spotify_duration_ms,
        spotify_images=_extract_image_urls(doc.get("spotify_images")),
        mp3_url=doc.get("mp3_url"),
        transcript_url=doc.get("transcript_url"),
        summary_url=doc.get("summary_url"),
        summary_image_url=doc.get("summary_image_url"),
        events_markdown_url=doc.get("events_markdown_url"),
        sentences_markdown_url=doc.get("sentences_markdown_url"),
        marp_markdown_url=doc.get("marp_markdown_url"),
        ticker_marp_markdown_url=doc.get("ticker_marp_markdown_url"),
        ticker_insights_url=doc.get("ticker_insights_url") or doc.get("ticker_recommendations_url"),
        summary_content=doc.get("summary_content"),
        key_insights=doc.get("key_insights") or [],
        events_markdown_content=doc.get("events_markdown_content"),
        sentences_markdown_content=doc.get("sentences_markdown_content"),
        marp_markdown_content=doc.get("marp_markdown_content"),
        ticker_marp_markdown_content=doc.get("ticker_marp_markdown_content"),
        ticker_insights_content=doc.get("ticker_insights_content") or doc.get("ticker_recommendations_content"),
        related_tickers=related_tickers,
        tags=tags,
        num_likes=int(doc.get("num_likes") or 0),
        number_click=int(doc.get("number_click") or 0),
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    # Bootstrap secrets from GSM when running on the VPS (no-op if env vars already set)
    try:
        from secrets_bootstrap import bootstrap  # type: ignore[import-untyped]
        bootstrap()
    except ImportError:
        pass

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="report counts but skip all writes")
    ap.add_argument("--limit", type=int, help="process at most N episodes (for testing)")
    ap.add_argument("--skip-insights", action="store_true", help="skip ticker_insights + trending backfill")
    ap.add_argument("--wiki-url", default=os.environ.get("WIKI_DATABASE_URL"), help="target DB URL")
    ap.add_argument("--mirror-url", default=os.environ.get("EPISODE_DATABASE_URL"), help="source mirror DB URL")
    args = ap.parse_args()

    if not args.wiki_url:
        print("ERROR: WIKI_DATABASE_URL is not set (use --wiki-url or set env var)", file=sys.stderr)
        return 2
    if not args.mirror_url:
        print("ERROR: EPISODE_DATABASE_URL is not set (use --mirror-url or set env var)", file=sys.stderr)
        return 2

    # wiki target uses postgresql+psycopg:// (SQLAlchemy); mirror source uses psycopg.connect()
    # which wants a plain postgresql:// libpq URI — strip any +driver suffix.
    wiki_url = args.wiki_url
    mirror_url = args.mirror_url.replace("postgresql+psycopg://", "postgresql://", 1).replace("postgresql+psycopg2://", "postgresql://", 1)

    # ------------------------------------------------------------------
    # Open target (tinboker_wiki)
    # ------------------------------------------------------------------
    print("Connecting to target (tinboker_wiki)...")
    repos = get_repositories(database_url=wiki_url)
    print("  OK\n")

    # ------------------------------------------------------------------
    # Open source (podcast_db via psycopg)
    # ------------------------------------------------------------------
    print("Connecting to source (podcast_db mirror)...")
    import psycopg  # type: ignore[import-untyped]
    import psycopg.rows  # type: ignore[import-untyped]

    src_conn = psycopg.connect(mirror_url, row_factory=psycopg.rows.dict_row)
    print("  OK\n")

    # ------------------------------------------------------------------
    # Step 1: podcasts
    # ------------------------------------------------------------------
    print("Step 1: podcasts")
    with src_conn.cursor() as cur:
        cur.execute("""
            SELECT DISTINCT podcast_name FROM firestore_mirror.episodes
            ORDER BY podcast_name
        """)
        podcast_names: list[str] = [r["podcast_name"] for r in cur.fetchall() if r["podcast_name"]]

    # Also pull any extra metadata from firestore_mirror.podcasts if available
    podcast_meta: dict[str, dict] = {}
    try:
        with src_conn.cursor() as cur:
            cur.execute("SELECT * FROM firestore_mirror.podcasts")
            for row in cur.fetchall():
                name = row.get("podcast_name") or row.get("name")
                if name:
                    podcast_meta[name] = dict(row)
    except Exception:
        pass  # table might not exist or have different schema

    print(f"  {len(podcast_names)} distinct podcasts in mirror")
    written_podcasts = 0
    for name in podcast_names:
        meta = podcast_meta.get(name, {})
        doc = meta.get("doc") or {}
        if isinstance(doc, str):
            try:
                doc = json.loads(doc)
            except Exception:
                doc = {}
        podcast = Podcast(
            name=name,
            spotify_show_link=meta.get("spotify_show_link") or doc.get("spotify_show_link"),
            description=meta.get("description") or doc.get("description"),
            thumbnail_url=meta.get("thumbnail_url") or doc.get("thumbnail_url"),
            language="zh" if _is_zh(name) else "en",
        )
        if args.dry_run:
            written_podcasts += 1
        else:
            repos.podcasts.upsert(podcast)
            written_podcasts += 1
    print(f"  {'[dry-run] would write' if args.dry_run else 'wrote'} {written_podcasts} podcasts\n")

    # ------------------------------------------------------------------
    # Step 2: tickers from registry
    # ------------------------------------------------------------------
    print("Step 2: tickers from tickers.json")
    seen_symbols: set[str] = set()
    tickers_to_write: list[Ticker] = []
    for info in ticker_index().values():
        if info.symbol in seen_symbols:
            continue
        seen_symbols.add(info.symbol)
        tickers_to_write.append(
            Ticker(
                symbol=info.symbol,
                name=info.name,
                market=info.market,
                sector=info.sector,
            )
        )
    print(f"  {len(tickers_to_write)} unique symbols in registry")
    if not args.dry_run:
        for t in tickers_to_write:
            repos.tickers.upsert(t)
    print(f"  {'[dry-run] would write' if args.dry_run else 'wrote'} {len(tickers_to_write)} tickers\n")

    # ------------------------------------------------------------------
    # Step 3: episodes
    # ------------------------------------------------------------------
    print("Step 3: episodes")
    with src_conn.cursor() as cur:
        cur.execute("""
            SELECT episode_id, podcast_name, created_time, related_tickers, doc
            FROM firestore_mirror.episodes
            ORDER BY created_time DESC NULLS LAST
        """)
        mirror_rows: list[dict] = cur.fetchall()

    if args.limit:
        mirror_rows = mirror_rows[: args.limit]

    print(f"  {len(mirror_rows)} episodes to process")
    written_eps = 0
    for row in mirror_rows:
        ep = _build_episode(row)
        if args.dry_run:
            written_eps += 1
        else:
            repos.episodes.upsert(ep)
            written_eps += 1
    print(f"  {'[dry-run] would write' if args.dry_run else 'wrote'} {written_eps} episodes\n")

    # ------------------------------------------------------------------
    # Step 4: ticker_insights (skippable; requires GCS access)
    # ------------------------------------------------------------------
    all_insight_dicts: list[dict] = []  # for step 5 aggregation

    if args.skip_insights:
        print("Step 4: ticker_insights  [skipped]\n")
    else:
        print("Step 4: ticker_insights (downloading from GCS)")
        insight_targets = [
            r for r in mirror_rows
            if (r.get("doc") or {}).get("ticker_insights_url") or (r.get("doc") or {}).get("ticker_recommendations_url")
        ]
        print(f"  {len(insight_targets)} episodes have ticker_insights_url")

        written_insights = 0
        skipped_insights: list[str] = []
        known_tickers: set[str] = seen_symbols.copy()  # registry symbols already in tickers table
        for i, row in enumerate(insight_targets, 1):
            ep_id: str = row["episode_id"]
            doc: dict = row.get("doc") or {}
            gcs_url: str = doc.get("ticker_insights_url") or doc["ticker_recommendations_url"]
            podcaster: str = row["podcast_name"] or ""
            # Use spotify_release_date as the canonical launch time; fall back to created_time
            launch_time = doc.get("spotify_release_date") or row.get("created_time")

            raw_payload = _read_gcs_json(gcs_url)
            if raw_payload is None:
                if not args.dry_run:
                    print(f"  [{i}/{len(insight_targets)}] {ep_id}: GCS read failed — skip")
                skipped_insights.append(ep_id)
                continue

            insight_docs = build_episode_insight_docs(
                raw_payload=raw_payload,
                episode_id=ep_id,
                podcaster=podcaster,
                podcast_launch_time=launch_time,
            )
            if not insight_docs:
                skipped_insights.append(ep_id)
                continue

            for ticker, idoc in insight_docs.items():
                all_insight_dicts.append(idoc)
                if not args.dry_run:
                    # Ensure the ticker row exists (FK); registry gaps are filled with minimal metadata
                    if ticker not in known_tickers:
                        info = ticker_index().get(ticker)
                        repos.tickers.upsert(Ticker(
                            symbol=ticker,
                            name=info.name if info else ticker,
                            market=info.market if info else "",
                            sector=info.sector if info else "",
                        ))
                        known_tickers.add(ticker)
                    repos.ticker_insights.upsert(
                        TickerInsight(
                            episode_id=ep_id,
                            ticker=ticker,
                            bluf_thesis=idoc.get("bluf_thesis"),
                            time_horizon=idoc.get("time_horizon"),
                            sentiment_label=idoc.get("sentiment_label"),
                            sentiment_score=idoc.get("sentiment_score"),
                            reasons=idoc.get("reasons") or [],
                            risks=idoc.get("risks") or [],
                            podcaster=idoc.get("podcaster"),
                            podcast_launch_time=idoc.get("podcast_launch_time"),
                        )
                    )
                written_insights += 1

            if i % 50 == 0 or i == len(insight_targets):
                print(f"  [{i}/{len(insight_targets)}] {written_insights} insight docs so far")

        print(f"  {'[dry-run] would write' if args.dry_run else 'wrote'} {written_insights} ticker_insight rows")
        if skipped_insights:
            print(f"  skipped {len(skipped_insights)} episodes: {skipped_insights[:5]}{'...' if len(skipped_insights) > 5 else ''}")
        print()

    # ------------------------------------------------------------------
    # Step 5: trending_tickers (aggregate from collected insights)
    # ------------------------------------------------------------------
    if args.skip_insights:
        print("Step 5: trending_tickers  [skipped — no insights collected]\n")
    else:
        print("Step 5: trending_tickers (aggregating in-memory)")
        trending_docs = aggregate_trending(all_insight_dicts)
        print(f"  {len(trending_docs)} tickers")
        if not args.dry_run:
            for ticker_sym, tdoc in trending_docs.items():
                repos.trending_tickers.upsert(
                    TrendingTicker(
                        ticker=ticker_sym,
                        count_30d=tdoc.get("count_30d", 0),
                        count_90d=tdoc.get("count_90d", 0),
                        count_all_time=tdoc.get("count_all_time", 0),
                        sentiment_label=tdoc.get("sentiment_label"),
                        sentiment_score=tdoc.get("sentiment_score"),
                        last_mentioned=tdoc.get("last_mentioned"),
                        top_podcasters=tdoc.get("top_podcasters") or [],
                        top_episodes=tdoc.get("top_episodes") or [],
                    )
                )
        print(f"  {'[dry-run] would write' if args.dry_run else 'wrote'} {len(trending_docs)} trending_ticker rows\n")

    # ------------------------------------------------------------------
    # Verification gate
    # ------------------------------------------------------------------
    print("=" * 60)
    print("Verification")
    if not args.dry_run:
        ep_count = repos.episodes.count()
        pod_count = len(repos.podcasts.list_all())
        recent = repos.episodes.list_recent(limit=5)
        print(f"  episodes   : {ep_count}")
        print(f"  podcasts   : {pod_count}")
        print(f"  recent 5   : {[e.id for e in recent]}")

        if ep_count < 849:
            print(f"  WARNING: episode count {ep_count} < 849 — check mirror sync")
        if pod_count < 10:
            print(f"  WARNING: podcast count {pod_count} < 10 — check mirror data")
    else:
        print(f"  [dry-run] mirror has {len(mirror_rows)} episodes, {len(podcast_names)} podcasts")

    src_conn.close()
    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
