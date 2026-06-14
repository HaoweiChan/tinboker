"""Self-healing reconcile for ``episodes/{id}.released_at_ms``.

``released_at_ms`` is the episode's TRUE publish time (handoff spec § 2.3 #1).
The live pipeline already writes it from the feed ``datePublished`` for every
episode it ingests (see ``pipeline.utils.create_episode_object`` /
``models.podcast_models._compute_released_at_ms``). But a historical bulk
re-ingest — or any ingest that ran while the feed date was momentarily
unavailable — can leave ``released_at_ms`` pinned to ``created_time`` (the
ingestion time). That mis-sorts old episodes into recent feeds and corrupts any
time-based filter/stat keyed on the publish date.

This pass re-derives ``released_at_ms`` from the in-memory feed (already fetched
by the orchestrator each run) and fixes any mismatch. It is the same correction
``scripts/backfill_released_at_ms.py`` applies, but runs inline so the data
self-heals over time without a manual backfill.

Cost: ONE Firestore read per show (``get_podcast_episodes``) plus a write only
for each mismatched doc — a no-op once the data is correct. It touches ONLY
``released_at_ms``; ``created_time`` is never mutated, so no ``new_episode``
notification is re-fired (handoff spec § 6.3).
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional

from src.pipeline.utils import _date_published_to_ms


def _feed_indexes(feed_episodes: List[Dict]):
    """Build (title, number) and title-only lookups of feed publish-ms.

    The (title, number) key is preferred; the title-only map is a fallback for
    docs whose stored ``episode_number`` is null. Newest-first feed order means
    the title-only map keeps the most recent date on a title collision.
    """
    by_key: Dict[tuple, int] = {}
    by_title: Dict[str, int] = {}
    for ep in feed_episodes:
        title = ep.get("title")
        if not title:
            continue
        ms = _date_published_to_ms(ep)
        if ms is None:
            continue
        number = ep.get("episodeNumber")
        by_key[(title, number)] = ms
        by_title.setdefault(title, ms)
    return by_key, by_title


def reconcile_show_released_at_ms(
    firebase_service,
    podcast_name: str,
    feed_episodes: List[Dict],
    *,
    apply: bool = True,
    log: Callable[[str], None] = print,
) -> Dict[str, int]:
    """Heal stored ``released_at_ms`` for one show against the feed.

    Args:
        firebase_service: a ``FirebaseService`` instance.
        podcast_name: canonical show name (matches the stored ``podcast_name``).
        feed_episodes: the raw podcasttomp3 feed list (each item carries
            ``title``/``episodeNumber``/``datePublished``).
        apply: when False, only counts/logs what WOULD change (dry run).
        log: sink for progress lines (defaults to ``print``).

    Returns:
        ``{"checked": int, "fixed": int, "failed": int}``.
    """
    by_key, by_title = _feed_indexes(feed_episodes)
    if not by_key and not by_title:
        return {"checked": 0, "fixed": 0, "failed": 0}

    try:
        stored = firebase_service.get_podcast_episodes(podcast_name)
    except Exception as e:  # noqa: BLE001 — reconcile is best-effort, never fatal
        log(f"  [reconcile] {podcast_name}: could not load episodes ({e})")
        return {"checked": 0, "fixed": 0, "failed": 0}

    checked = fixed = failed = 0
    for doc in stored or []:
        title = doc.get("episode_title")
        if not title:
            continue
        number = doc.get("episode_number")
        feed_ms: Optional[int] = by_key.get((title, number))
        if feed_ms is None:
            feed_ms = by_title.get(title)
        if feed_ms is None:
            continue
        checked += 1
        if doc.get("released_at_ms") == feed_ms:
            continue

        ep_id = doc.get("id")
        verb = "would set" if not apply else "set"
        log(
            f"  [reconcile] {podcast_name} {ep_id}: {verb} released_at_ms "
            f"{doc.get('released_at_ms')} -> {feed_ms}"
        )
        if not apply:
            fixed += 1
            continue
        try:
            # Partial update: touches ONLY released_at_ms.
            firebase_service.update_episode_fields(ep_id, {"released_at_ms": feed_ms})
            fixed += 1
        except Exception as e:  # noqa: BLE001
            failed += 1
            log(f"  [reconcile] {ep_id}: write failed ({e})")

    if fixed or failed:
        log(
            f"  [reconcile] {podcast_name}: {fixed} fixed, {failed} failed "
            f"({checked} checked)"
        )
    return {"checked": checked, "fixed": fixed, "failed": failed}
