"""Podcast service for managing podcast data from Firestore"""
import os
import json
import asyncio
import logging
from typing import Optional, List, Collection
from datetime import datetime
from src.config import settings
from src.models.podcast import Podcast, Episode
from src.schemas.search import SearchResultItem
from src.cache.redis_client import cache_get, cache_set, cache_delete, cache_delete_pattern
from src.cache.cache_config import CACHE_TTL
from src.services.firestore_service import FirestoreService
from src.services.gcs_content import GCSContentService
from src.services.episode_transformer import EpisodeTransformer
import httpx


logger = logging.getLogger(__name__)

EPISODE_DETAIL_CONTENT_FIELDS = frozenset({
    "summary_content",
    "events_markdown_content",
    "sentences_markdown_content",
    "modified_summary_content",
})


class PodcastService:
    """Service for podcast CRUD operations, search, and summary management"""

    def __init__(self, firestore_service: Optional[FirestoreService] = None):
        self.firestore_service = firestore_service or FirestoreService()
        self.gcs = GCSContentService()
        self.transformer = EpisodeTransformer(self.gcs)

    # ── Release scoping ──────────────────────────────────────────────
    # The public catalog is restricted to a launch subset: only podcasts whose
    # content_sources row is active and tagged with an allowed language
    # (settings.release_podcast_languages, default ["zh-TW"]), and — once a
    # reliable released_at_ms is backfilled — only episodes published within
    # settings.release_episode_max_age_days. Both are applied at this single
    # read chokepoint so every surface (feed, channel, ticker, tag, search,
    # trending) inherits them.

    async def _allowed_podcast_names(self) -> Optional[frozenset]:
        """Podcast names permitted by the current release language scope.

        Sourced from the content_sources registry (Postgres): active podcasts
        whose language is in settings.release_podcast_languages. Cached in Redis.
        Returns None when no language restriction is configured (filter off).
        An empty/unavailable registry yields an empty set (fail closed — never
        leak out-of-scope shows), and is not cached so it retries next call.
        """
        langs = settings.release_podcast_languages
        if not langs:
            return None
        cache_key = f"release:allowed_podcasts:{','.join(sorted(langs))}"
        cached = await cache_get(cache_key)
        if cached is not None:
            try:
                return frozenset(json.loads(cached))
            except Exception:
                pass
        names = await asyncio.to_thread(self._query_allowed_podcast_names, langs)
        if names:
            try:
                await cache_set(cache_key, json.dumps(sorted(names)), CACHE_TTL["podcast_list"])
            except Exception:
                pass
        else:
            logger.error(
                "Release allowlist resolved to 0 podcasts for languages %s — "
                "content_sources empty or DB unavailable; serving no episodes.", langs,
            )
        return frozenset(names)

    @staticmethod
    def _query_allowed_podcast_names(langs: List[str]) -> List[str]:
        """Query content_sources for active podcast names in the given languages."""
        from src.database import postgres
        from src.services.content_source_service import ContentSourceService
        try:
            if postgres.SessionLocal is None:
                postgres.init_engine()
            db = postgres.SessionLocal()
            try:
                items, _ = ContentSourceService(db).list_sources(
                    source_type="podcast", active=True, limit=1000,
                )
                langset = set(langs)
                return [s.name for s in items if (s.language or "") in langset]
            finally:
                db.close()
        except Exception as e:
            logger.error("Failed to load release allowlist from content_sources: %s", e)
            return []

    async def _podcast_cover_map(self) -> dict:
        """name -> show cover image_url from content_sources (Spotify oEmbed art).

        Fills the podcast avatar for shows whose episodes carry no spotify_images.
        Cached in Redis.
        """
        cache_key = "podcast:covers"
        cached = await cache_get(cache_key)
        if cached is not None:
            try:
                return json.loads(cached)
            except Exception:
                pass
        covers = await asyncio.to_thread(self._query_podcast_covers)
        if covers:
            try:
                await cache_set(cache_key, json.dumps(covers), CACHE_TTL["podcast_list"])
            except Exception:
                pass
        return covers

    @staticmethod
    def _query_podcast_covers() -> dict:
        """Query content_sources for {podcast name: cover_image_url}."""
        from src.database import postgres
        from src.services.content_source_service import ContentSourceService
        try:
            if postgres.SessionLocal is None:
                postgres.init_engine()
            db = postgres.SessionLocal()
            try:
                items, _ = ContentSourceService(db).list_sources(source_type="podcast", limit=1000)
                return {s.name: s.cover_image_url for s in items if getattr(s, "cover_image_url", None)}
            finally:
                db.close()
        except Exception as e:
            logger.error("Failed to load podcast covers from content_sources: %s", e)
            return {}

    @staticmethod
    def _recency_cutoff_ms() -> Optional[int]:
        """Unix-ms cutoff for the 1-month window, or None when disabled."""
        days = settings.release_episode_max_age_days
        if not days or days <= 0:
            return None
        return int((datetime.now().timestamp() - days * 86400) * 1000)

    @staticmethod
    def _scope_tag() -> str:
        """Stable signature of the active release scope, for cache-key isolation."""
        langs = settings.release_podcast_languages
        lang_part = ",".join(sorted(langs)) if langs else "all"
        return f"{lang_part}:{settings.release_episode_max_age_days}"

    @staticmethod
    def _content_cache_tag(content_fields: Optional[Collection[str]]) -> str:
        """Stable cache-key suffix for hydrated content field sets.

        None means "all configured GCS-backed fields" for legacy/full payload callers.
        """
        if content_fields is None:
            return "full"
        return "fields-" + ",".join(sorted(content_fields))

    @staticmethod
    def _spotify_release_ms(value) -> Optional[int]:
        """Parse spotify_release_date ('YYYY-MM-DD' or ISO datetime) to Unix ms.

        This is the trustworthy publish signal. released_at_ms can fall back to
        ingestion time for episodes re-ingested without a feed date, which makes
        old/empty episodes mis-float to the top of recency-sorted feeds.
        """
        if not value or not isinstance(value, str):
            return None
        s = value.strip()
        if not s:
            return None
        try:
            dt = datetime.fromisoformat(s.replace('Z', '+00:00'))
        except ValueError:
            try:
                dt = datetime.strptime(s[:10], '%Y-%m-%d')
            except ValueError:
                return None
        return int(dt.timestamp() * 1000)

    @staticmethod
    def _episode_release_ms(episode: Episode) -> int:
        """Publish time for recency/sort: prefer the true Spotify publish date,
        then released_at_ms, then created_time."""
        sp = PodcastService._spotify_release_ms(getattr(episode, 'spotify_release_date', None))
        if sp is not None:
            return sp
        return episode.released_at_ms if episode.released_at_ms is not None else (episode.created_time or 0)

    def _dict_release_ms(self, ep: dict) -> int:
        """Publish time (Unix ms) for a raw Firestore episode dict.
        Prefers spotify_release_date, then released_at_ms, then created_time."""
        sp = self._spotify_release_ms(ep.get('spotify_release_date'))
        if sp is not None:
            return sp
        r = self.transformer._normalize_released_at_ms(ep.get('released_at_ms'))
        if r is not None:
            return r
        return self.transformer.datetime_to_timestamp_ms(ep.get('created_time', datetime.now()))

    @staticmethod
    def _episode_has_content(ep: Episode) -> bool:
        """Whether an episode has publishable content. Re-ingested placeholder
        episodes carry no summary and no key_insights — hide them from public
        surfaces so empty cards never reach users."""
        return bool(
            (ep.summary_content or '').strip()
            or (ep.modified_summary_content or '').strip()
            or (ep.key_insights or [])
        )

    @staticmethod
    def _dict_has_content(ep: dict) -> bool:
        """Content guard for a raw Firestore episode dict (see _episode_has_content)."""
        return bool(
            (ep.get('summary_content') or '').strip()
            or (ep.get('modified_summary_content') or '').strip()
            or (ep.get('key_insights') or [])
        )

    @staticmethod
    def _scope_episodes(
        episodes: List[Episode], allowed: Optional[frozenset], cutoff: Optional[int],
    ) -> List[Episode]:
        """Drop episodes outside the release language allowlist / recency window,
        and always drop content-empty placeholder episodes."""
        out = []
        for ep in episodes:
            if not PodcastService._episode_has_content(ep):
                continue
            if allowed is not None and ep.podcast_name not in allowed:
                continue
            if cutoff is not None and PodcastService._episode_release_ms(ep) < cutoff:
                continue
            out.append(ep)
        return out

    async def _episode_in_scope(self, episode: Episode) -> bool:
        """Whether a single episode is visible under the current release scope."""
        allowed = await self._allowed_podcast_names()
        if allowed is not None and episode.podcast_name not in allowed:
            return False
        cutoff = self._recency_cutoff_ms()
        if cutoff is not None and self._episode_release_ms(episode) < cutoff:
            return False
        return True

    # ── Podcast queries ──────────────────────────────────────────────

    async def get_all_podcasts(
        self, sort_by: str = "name", order: str = "asc",
        limit: int = 50, offset: int = 0,
    ) -> List[Podcast]:
        """Get all podcasts (aggregated from episodes) with caching"""
        cache_key = f"podcast:list:{sort_by}:{order}:{self._scope_tag()}"
        cached = await cache_get(cache_key)
        if cached:
            try:
                podcasts = [Podcast(**item) for item in json.loads(cached)]
                return podcasts[offset:offset + limit]
            except Exception:
                pass

        try:
            allowed = await self._allowed_podcast_names()
            cutoff = self._recency_cutoff_ms()
            covers = await self._podcast_cover_map()
            all_episodes = await asyncio.to_thread(
                self.firestore_service.get_all_documents, "episodes",
            )
            podcast_dict: dict = {}
            for ep in all_episodes:
                name = ep.get('podcast_name')
                if not name:
                    continue
                if allowed is not None and name not in allowed:
                    continue
                if not self._dict_has_content(ep):
                    continue
                if cutoff is not None and self._dict_release_ms(ep) < cutoff:
                    continue
                entry = podcast_dict.setdefault(name, {'episodes': [], 'created_at': None, 'updated_at': None, 'image_url': None})
                ts = self.transformer.datetime_to_timestamp_ms(ep.get('created_time', datetime.now()))
                if entry['created_at'] is None or ts < entry['created_at']:
                    entry['created_at'] = ts
                if entry['updated_at'] is None or ts > entry['updated_at']:
                    entry['updated_at'] = ts
                    entry['latest_episode'] = ep
                imgs = ep.get('spotify_images', [])
                if imgs and isinstance(imgs, list) and len(imgs) > 0 and entry['image_url'] is None:
                    entry['image_url'] = imgs[0]
                entry['episodes'].append(ep)

            podcasts = []
            for name, data in podcast_dict.items():
                image_url = data.get('image_url')
                latest_imgs = data.get('latest_episode', {}).get('spotify_images', [])
                if latest_imgs and isinstance(latest_imgs, list) and len(latest_imgs) > 0:
                    image_url = latest_imgs[0]
                podcasts.append(Podcast(
                    id=name, name=name, episode_count=len(data['episodes']),
                    created_at=data['created_at'], updated_at=data['updated_at'],
                    image_url=image_url or covers.get(name),
                ))

            reverse = order.lower() == "desc"
            sort_keys = {
                "name": lambda x: x.name.lower(),
                "episode_count": lambda x: x.episode_count,
                "created_at": lambda x: x.created_at or 0,
                "updated_at": lambda x: x.updated_at or 0,
            }
            podcasts.sort(key=sort_keys.get(sort_by, sort_keys["name"]), reverse=reverse)

            try:
                await cache_set(cache_key, json.dumps([p.dict() for p in podcasts], default=str), CACHE_TTL["podcast_list"])
            except Exception:
                pass
            return podcasts[offset:offset + limit]
        except Exception as e:
            raise Exception(f"Failed to get podcasts: {e}") from e

    async def get_podcast_by_name(self, podcast_name: str) -> Optional[Podcast]:
        """Get podcast by name with caching"""
        allowed = await self._allowed_podcast_names()
        if allowed is not None and podcast_name not in allowed:
            return None
        cutoff = self._recency_cutoff_ms()
        covers = await self._podcast_cover_map()
        cache_key = f"podcast:{podcast_name}:{self._scope_tag()}"
        cached = await cache_get(cache_key)
        if cached:
            try:
                return Podcast(**json.loads(cached))
            except Exception:
                pass

        try:
            episodes = self.firestore_service.query_collection(
                collection="episodes", filters=[("podcast_name", "==", podcast_name)],
            )
            episodes = [ep for ep in episodes if self._dict_has_content(ep)]
            if cutoff is not None:
                episodes = [ep for ep in episodes if self._dict_release_ms(ep) >= cutoff]
            if not episodes:
                return None

            created_at = updated_at = None
            latest_image_url = None
            fallback_image_url = None
            for ep in episodes:
                ts = self.transformer.datetime_to_timestamp_ms(ep.get('created_time', datetime.now()))
                if created_at is None or ts < created_at:
                    created_at = ts
                if updated_at is None or ts > updated_at:
                    updated_at = ts
                images = ep.get('spotify_images', [])
                if images and isinstance(images, list) and len(images) > 0:
                    if ts == updated_at:
                        latest_image_url = images[0]
                    elif fallback_image_url is None:
                        fallback_image_url = images[0]

            podcast = Podcast(
                id=podcast_name, name=podcast_name, episode_count=len(episodes),
                created_at=created_at, updated_at=updated_at,
                image_url=latest_image_url or fallback_image_url or covers.get(podcast_name),
            )
            try:
                await cache_set(cache_key, json.dumps(podcast.dict(), default=str), CACHE_TTL["podcast_item"])
            except Exception:
                pass
            return podcast
        except Exception as e:
            raise Exception(f"Failed to get podcast: {e}") from e

    # ── Episode queries ──────────────────────────────────────────────

    async def get_episodes_by_podcast(
        self, podcast_name: str, sort_by: str = "created_time",
        order: str = "desc", limit: int = 50, offset: int = 0,
        enrich_content: bool = False,
    ) -> List[Episode]:
        """Get episodes for a podcast with caching"""
        allowed = await self._allowed_podcast_names()
        if allowed is not None and podcast_name not in allowed:
            return []
        cutoff = self._recency_cutoff_ms()
        cache_key = f"podcast:{podcast_name}:episodes:{sort_by}:{order}:{enrich_content}:{self._scope_tag()}"
        cached = await cache_get(cache_key)
        if cached:
            try:
                return [Episode(**i) for i in json.loads(cached)][offset:offset + limit]
            except Exception:
                pass

        try:
            episodes_dict = self.firestore_service.query_collection(
                collection="episodes", filters=[("podcast_name", "==", podcast_name)],
                order_by=None, direction=None, limit=None,
            )
            episodes = await asyncio.gather(
                *[self.transformer.to_episode(d, enrich_content=enrich_content) for d in episodes_dict]
            )
            episodes = self._scope_episodes(list(episodes), allowed, cutoff)
            reverse = order.lower() == "desc"
            sort_keys = {
                "created_time": lambda x: x.created_time or 0,
                "episode_number": lambda x: x.episode_number if x.episode_number is not None else 0,
                "episode_title": lambda x: (x.episode_title or "").lower(),
            }
            episodes = sorted(episodes, key=sort_keys.get(sort_by, sort_keys["created_time"]), reverse=reverse)
            try:
                await cache_set(cache_key, json.dumps([e.dict() for e in episodes], default=str), CACHE_TTL["podcast_episodes"])
            except Exception:
                pass
            return list(episodes)[offset:offset + limit]
        except Exception as e:
            raise Exception(f"Failed to get episodes: {e}") from e

    async def get_episode_by_id(
        self, podcast_name: str, episode_id: str, apply_scope: bool = True,
        content_fields: Optional[Collection[str]] = EPISODE_DETAIL_CONTENT_FIELDS,
    ) -> Optional[Episode]:
        """Get episode by ID with caching.

        apply_scope=False bypasses the release language/recency filter — used by
        admin mutations that need the episode back regardless of public scope.
        """
        content_tag = self._content_cache_tag(content_fields)
        cache_key = f"podcast:{podcast_name}:episode:{episode_id}:v2:{content_tag}"
        cached = await cache_get(cache_key)
        if cached:
            try:
                episode = Episode(**json.loads(cached))
                if apply_scope and not await self._episode_in_scope(episode):
                    return None
                return episode
            except Exception:
                pass

        try:
            episode_dict = self.firestore_service.get_document("episodes", episode_id)
            if not episode_dict or episode_dict.get('podcast_name') != podcast_name:
                return None
            episode = await self.transformer.to_episode(episode_dict, content_fields=content_fields)
            # Skip caching a partially-hydrated episode (content URL set but content
            # empty, e.g. a transient GCS read failure) so the next request re-attempts
            # the GCS read instead of pinning a blank payload for the full TTL.
            if not self.transformer.is_content_incomplete(episode_dict, content_fields=content_fields):
                try:
                    await cache_set(cache_key, json.dumps(episode.dict(), default=str), CACHE_TTL["podcast_episode"])
                except Exception:
                    pass
            else:
                logger.warning(
                    "Skipping cache for episode %s/%s: content hydration incomplete (GCS fetch likely failed)",
                    podcast_name, episode_id,
                )
            if apply_scope and not await self._episode_in_scope(episode):
                return None
            return episode
        except Exception as e:
            raise Exception(f"Failed to get episode: {e}") from e

    async def get_episode_by_id_only(
        self,
        episode_id: str,
        content_fields: Optional[Collection[str]] = EPISODE_DETAIL_CONTENT_FIELDS,
    ) -> Optional[Episode]:
        """Get an episode by id without requiring the podcast name.

        Episode docs are keyed by id in Firestore; get_episode_by_id only uses
        podcast_name for a redundant equality check, so it is not needed to look an
        episode up. Used when the client opens /episode/{id} cold (deep link / refresh /
        shared URL) and has no ?podcast= to supply the show name.
        """
        content_tag = self._content_cache_tag(content_fields)
        cache_key = f"episode:{episode_id}:v2:{content_tag}"
        cached = await cache_get(cache_key)
        if cached:
            try:
                episode = Episode(**json.loads(cached))
                if not await self._episode_in_scope(episode):
                    return None
                return episode
            except Exception:
                pass

        try:
            episode_dict = self.firestore_service.get_document("episodes", episode_id)
            if not episode_dict:
                return None
            episode = await self.transformer.to_episode(episode_dict, content_fields=content_fields)
            if not await self._episode_in_scope(episode):
                return None
            # Don't pin a half-hydrated episode (content URL present but content empty,
            # e.g. a transient GCS read failure) — leave it uncached so the next request
            # re-attempts the fetch instead of serving a blank for the full TTL.
            if not self.transformer.is_content_incomplete(episode_dict, content_fields=content_fields):
                try:
                    await cache_set(cache_key, json.dumps(episode.dict(), default=str), CACHE_TTL["podcast_episode"])
                except Exception:
                    pass
            else:
                logger.warning(
                    "Skipping cache for episode %s: content hydration incomplete (GCS fetch likely failed)",
                    episode_id,
                )
            return episode
        except Exception as e:
            raise Exception(f"Failed to get episode: {e}") from e

    async def get_recent_episodes(
        self, limit: int = 20, offset: int = 0,
        podcast_name: Optional[str] = None, enrich_content: bool = False,
    ) -> List[Episode]:
        """Get recent episodes across all podcasts, sorted by created_time descending"""
        allowed = await self._allowed_podcast_names()
        cutoff = self._recency_cutoff_ms()
        scoping_active = allowed is not None or cutoff is not None
        cache_key = f"episodes:recent:{podcast_name or 'all'}:{limit}:{offset}:{enrich_content}:{self._scope_tag()}"
        cached = await cache_get(cache_key)
        if cached:
            try:
                return [Episode(**i) for i in json.loads(cached)]
            except Exception:
                pass

        try:
            filters = [("podcast_name", "==", podcast_name)] if podcast_name else None
            order_by = "created_time" if not podcast_name else None
            direction = "DESCENDING" if not podcast_name else None
            # When scoping is active we must fetch the full sorted set, not just the
            # newest `limit`, or a window dominated by out-of-scope shows could
            # filter down to fewer than `limit` in-scope episodes.
            query_limit = None if (podcast_name or scoping_active) else limit

            episodes_dict = await asyncio.to_thread(
                self.firestore_service.query_collection,
                collection="episodes", filters=filters,
                order_by=order_by, direction=direction, limit=query_limit,
            )
            episodes = await asyncio.gather(
                *[self.transformer.to_episode(d, enrich_content=enrich_content) for d in episodes_dict]
            )
            episodes = self._scope_episodes(list(episodes), allowed, cutoff)
            # Sort the cross-podcast feed by true publish time (released_at_ms,
            # falling back to created_time), NOT ingestion time — so a chronological
            # newest-first feed interleaves shows instead of clustering each
            # podcaster's ingestion batch together.
            episodes = sorted(episodes, key=self._episode_release_ms, reverse=True)
            paginated = list(episodes)[offset:offset + limit]
            try:
                await cache_set(cache_key, json.dumps([e.dict() for e in paginated], default=str), CACHE_TTL["podcast_episodes"])
            except Exception:
                pass
            return paginated
        except Exception as e:
            raise Exception(f"Failed to get recent episodes: {e}") from e

    async def get_episodes_by_ticker(
        self, ticker: str, limit: int = 50, offset: int = 0,
        enrich_content: bool = False,
    ) -> List[Episode]:
        """Get episodes that mention a specific ticker"""
        ticker_upper = ticker.upper()
        allowed = await self._allowed_podcast_names()
        cutoff = self._recency_cutoff_ms()
        scoping_active = allowed is not None or cutoff is not None
        cache_key = f"episodes:ticker:{ticker_upper}:{limit}:{offset}:{enrich_content}:{self._scope_tag()}"
        cached = await cache_get(cache_key)
        if cached:
            try:
                return [Episode(**i) for i in json.loads(cached)]
            except Exception:
                pass

        try:
            # Over-fetch refs when scoping so out-of-scope/old episodes filtered out
            # below don't starve the requested page.
            fetch_limit = max((limit + offset) * 5, 100) if scoping_active else (limit + offset)
            episode_refs = self.firestore_service.get_subcollection_documents(
                collection="tickers", parent_doc_id=ticker_upper,
                subcollection="episodes", order_by="created_time",
                direction="DESCENDING", limit=fetch_limit,
            )

            dicts = []
            for ref in episode_refs:
                eid = ref.get('episode_id')
                if eid:
                    doc = self.firestore_service.get_document("episodes", eid)
                    if doc:
                        dicts.append(doc)

            episodes = await asyncio.gather(
                *[self.transformer.to_episode(d, enrich_content=enrich_content) for d in dicts]
            )
            episodes = self._scope_episodes(list(episodes), allowed, cutoff)
            paginated = episodes[offset:offset + limit]
            try:
                await cache_set(cache_key, json.dumps([e.dict() for e in paginated], default=str), CACHE_TTL["podcast_episodes"])
            except Exception:
                pass
            return paginated
        except Exception as e:
            raise Exception(f"Failed to get episodes by ticker: {e}") from e

    # ── Tag queries ──────────────────────────────────────────────────

    # Curated financial topic tags for the topics cloud. The `tags` Firestore
    # collection has ~7k entries (mostly ticker codes / long-tail junk like "0dte")
    # with no precomputed counts, and the per-episode `tags` field is ~always empty
    # (tags live in the summary markdown). Counting all 7k subcollections hangs the
    # backend, so we count only this meaningful, bounded set. Keep in sync with the
    # frontend topicLabels map in TopicsCloud.tsx.
    _TOPIC_TAGS = [
        "ai", "ai_chip", "advanced_packaging", "bitcoin", "capital_expenditure",
        "centralbanks", "cryptocurrency", "datacenters", "demographics", "digitalassets",
        "earningsreport", "electric_vehicles", "electricvehicles", "etf", "ev",
        "federalreserve", "financialregulation", "fiscalpolicy", "fixedincome",
        "interestrates", "interestratepolicy", "japanmarket", "labormarket",
        "low_earth_orbit_satellite", "marketnarratives", "media_industry",
        "mergers_and_acquisitions", "monetarypolicy", "powersupply", "privatemarkets",
        "semiconductor", "streaming_services", "supply_chain", "taiwaneconomy",
        "trade_war", "us_stocks", "useconomy", "usstockmarket", "ustreasuries", "valuation",
    ]

    async def get_all_tags(self) -> List[dict]:
        """Episode counts for the curated topic tags (bounded + cached).

        Counts each topic's `tags/{tag}/episodes` subcollection. All-time counts
        (not recency/zh-TW-scoped — the per-episode `tags` field is empty so a
        scoped count isn't available cheaply).
        """
        cache_key = "tags:topics:v3"
        cached = await cache_get(cache_key)
        if cached:
            try:
                return json.loads(cached)
            except Exception:
                pass
        try:
            sem = asyncio.Semaphore(12)

            async def _count(tid: str) -> Optional[dict]:
                async with sem:
                    try:
                        count = await asyncio.to_thread(
                            self.firestore_service.count_subcollection_documents,
                            collection="tags", parent_doc_id=tid, subcollection="episodes",
                        )
                    except Exception:
                        return None
                return {"id": tid, "name": tid, "episode_count": count} if count and count > 0 else None

            counted = await asyncio.gather(*[_count(t) for t in self._TOPIC_TAGS])
            result = sorted([r for r in counted if r], key=lambda x: x["episode_count"], reverse=True)
            try:
                await cache_set(cache_key, json.dumps(result), 3600)
            except Exception:
                pass
            return result
        except Exception as e:
            raise Exception(f"Failed to get all tags: {e}") from e

    async def get_episodes_by_tag(
        self, tag: str, limit: int = 50, offset: int = 0,
        enrich_content: bool = False,
    ) -> List[Episode]:
        """Get episodes for a specific tag"""
        try:
            allowed = await self._allowed_podcast_names()
            cutoff = self._recency_cutoff_ms()
            scoping_active = allowed is not None or cutoff is not None
            fetch_limit = max((limit + offset) * 5, 100) if scoping_active else (limit + offset)
            episode_refs = self.firestore_service.get_subcollection_documents(
                collection="tags", parent_doc_id=tag.lower(),
                subcollection="episodes", order_by="created_time",
                direction="DESCENDING", limit=fetch_limit,
            )

            dicts = []
            for ref in episode_refs:
                eid = ref.get('episode_id')
                if eid:
                    doc = self.firestore_service.get_document("episodes", eid)
                    if doc:
                        dicts.append(doc)

            episodes = await asyncio.gather(
                *[self.transformer.to_episode(d, enrich_content=enrich_content) for d in dicts]
            )
            episodes = self._scope_episodes(list(episodes), allowed, cutoff)
            return episodes[offset:offset + limit]
        except Exception as e:
            raise Exception(f"Failed to get episodes by tag: {e}") from e

    # ── Search ───────────────────────────────────────────────────────

    async def search_podcasts(self, query: str, limit: int = 5) -> List[SearchResultItem]:
        """Search podcasts by name"""
        try:
            async def _search():
                all_podcasts = await self.get_all_podcasts(limit=1000)
                q = query.lower()
                results = []
                for p in all_podcasts:
                    if q in p.name.lower():
                        results.append(SearchResultItem(
                            id=f"podcast-{p.id}", type="podcast", title=p.name,
                            subtitle=f"{p.episode_count} episodes",
                            icon_url=p.image_url, link=f"/podcaster/{p.name}",
                        ))
                        if len(results) >= limit:
                            break
                return results
            return await asyncio.wait_for(_search(), timeout=2.0)
        except (asyncio.TimeoutError, Exception) as e:
            logger.warning(f"Podcast search failed: {e}")
            return []

    async def search_episodes(self, query: str, limit: int = 5) -> List[SearchResultItem]:
        """Search episodes by title or podcast name"""
        try:
            async def _search():
                all_episodes = await self.get_recent_episodes(limit=200)
                q = query.lower()
                results = []
                for ep in all_episodes:
                    title = ep.episode_title or ""
                    podcast = ep.podcast_name or ""
                    if q in title.lower() or q in podcast.lower():
                        icon_url = None
                        if ep.spotify_images and isinstance(ep.spotify_images, list) and len(ep.spotify_images) > 0:
                            icon_url = ep.spotify_images[0]
                        elif ep.summary_image_url:
                            icon_url = ep.summary_image_url
                        results.append(SearchResultItem(
                            id=f"episode-{ep.id}", type="episode",
                            title=title or f"Episode {ep.episode_number}",
                            subtitle=podcast, icon_url=icon_url,
                            link=f"/podcaster/{podcast}",
                        ))
                        if len(results) >= limit:
                            break
                return results
            return await asyncio.wait_for(_search(), timeout=2.0)
        except (asyncio.TimeoutError, Exception) as e:
            logger.warning(f"Episode search failed: {e}")
            return []

    async def search_tags(self, query: str, limit: int = 5) -> List[SearchResultItem]:
        """Search tags by name"""
        try:
            async def _search():
                try:
                    all_tags = await self.get_all_tags()
                except Exception:
                    all_tags = []
                q = query.lower()
                results = []
                for tag in all_tags:
                    if q in tag.get("name", "").lower():
                        results.append(SearchResultItem(
                            id=f"tag-{tag.get('id')}", type="tag",
                            title=tag["name"],
                            subtitle=f"{tag.get('episode_count')} episodes",
                            link=f"/tag/{tag['name']}",
                        ))
                        if len(results) >= limit:
                            break
                return results
            return await asyncio.wait_for(_search(), timeout=2.0)
        except (asyncio.TimeoutError, Exception) as e:
            logger.warning(f"Tag search failed: {e}")
            return []

    # ── Summary mutations ────────────────────────────────────────────

    async def save_modified_summary(
        self, podcast_name: str, episode_id: str,
        content: str, modified_by: Optional[str] = None,
    ) -> Episode:
        """Save modified summary to GCS and update Firestore"""
        from fastapi import HTTPException

        episode_dict = self.firestore_service.get_document("episodes", episode_id)
        if not episode_dict:
            raise HTTPException(status_code=404, detail=f"Episode {episode_id} not found")
        if episode_dict.get('podcast_name') != podcast_name:
            raise HTTPException(status_code=404, detail=f"Episode {episode_id} not found for podcast {podcast_name}")

        bucket_name = None
        for url_field in ['summary_url', 'transcript_url', 'mp3_url']:
            if episode_dict.get(url_field):
                parsed = self.gcs.parse_gs_url(episode_dict[url_field])
                if parsed:
                    bucket_name = parsed[0]
                    break
        if not bucket_name:
            bucket_name = os.getenv("GCS_BUCKET", "tinboker-podcast-data")

        blob_path = f"{podcast_name}/modified_summary/{episode_id}_summary.md"
        try:
            await self.gcs.upload_content(bucket_name, blob_path, content)
            modified_at = int(datetime.now().timestamp() * 1000)
            update_data = {'modified_summary_url': f"gs://{bucket_name}/{blob_path}", 'modified_at': modified_at}
            if modified_by:
                update_data['modified_by'] = modified_by

            await asyncio.to_thread(
                self.firestore_service.set_document, "episodes", episode_id, update_data, True,
            )
            await self._invalidate_episode_cache(podcast_name, episode_id)
            return await self.get_episode_by_id(podcast_name, episode_id, apply_scope=False)
        except Exception as e:
            logger.error(f"Failed to save modified summary: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to save modified summary: {str(e)}")

    async def delete_modified_summary(self, podcast_name: str, episode_id: str) -> bool:
        """Delete modified summary from GCS and Firestore"""
        from fastapi import HTTPException

        episode_dict = self.firestore_service.get_document("episodes", episode_id)
        if not episode_dict:
            raise HTTPException(status_code=404, detail=f"Episode {episode_id} not found")
        if episode_dict.get('podcast_name') != podcast_name:
            raise HTTPException(status_code=404, detail=f"Episode {episode_id} not found for podcast {podcast_name}")

        modified_url = episode_dict.get('modified_summary_url')
        if not modified_url:
            return True

        try:
            parsed = self.gcs.parse_gs_url(modified_url)
            if parsed:
                await self.gcs.delete_blob(*parsed)

            from google.cloud.firestore import DELETE_FIELD
            await asyncio.to_thread(
                self.firestore_service.set_document, "episodes", episode_id,
                {'modified_summary_url': DELETE_FIELD, 'modified_summary_content': DELETE_FIELD,
                 'modified_by': DELETE_FIELD, 'modified_at': DELETE_FIELD},
                True,
            )
            await self._invalidate_episode_cache(podcast_name, episode_id)
            return True
        except Exception as e:
            logger.error(f"Failed to delete modified summary: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to delete modified summary: {str(e)}")

    async def _invalidate_episode_cache(self, podcast_name: str, episode_id: str):
        """Invalidate all caches related to an episode"""
        await cache_delete(f"podcast:{podcast_name}:episode:{episode_id}")
        await cache_delete_pattern(f"podcast:{podcast_name}:episode:{episode_id}:*")
        await cache_delete_pattern(f"episode:{episode_id}:*")
        await cache_delete_pattern(f"podcast:{podcast_name}:episodes:*")
        await cache_delete_pattern("episodes:recent:*")


async def poll_regeneration_status(podcast_name: str, episode_id: str):
    """Background task to poll regeneration status API and clear cache when done"""
    api_url = settings.netcup_api_url
    api_key = settings.podcast_api_key
    if not api_key:
        logger.error(f"PODCAST_API_KEY not configured, cannot poll status for {episode_id}")
        return

    max_attempts = 120
    async with httpx.AsyncClient() as client:
        for attempt in range(max_attempts):
            try:
                response = await client.get(
                    f"{api_url}/api/episodes/status/{episode_id}",
                    headers={"X-API-Key": api_key}, timeout=10.0,
                )
                response.raise_for_status()
                status = response.json().get("status")

                if status == "completed":
                    await cache_delete(f"podcast:{podcast_name}:episode:{episode_id}")
                    await cache_delete_pattern(f"podcast:{podcast_name}:episodes:*")
                    await cache_delete_pattern("episodes:recent:*")
                    logger.info(f"Regeneration completed for {podcast_name}/{episode_id}")
                    return
                elif status == "failed":
                    logger.error(f"Regeneration failed for {podcast_name}/{episode_id}: {response.json().get('error')}")
                    return
                if attempt % 12 == 0:
                    logger.info(f"Regeneration running for {podcast_name}/{episode_id} (attempt {attempt + 1}/{max_attempts})")
                await asyncio.sleep(5)
            except (httpx.HTTPStatusError, httpx.RequestError, Exception) as e:
                logger.warning(f"Error polling status for {episode_id}: {e}")
                await asyncio.sleep(5)

    logger.warning(f"Regeneration polling timed out for {podcast_name}/{episode_id}")
