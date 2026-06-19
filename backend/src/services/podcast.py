"""Podcast service for managing podcast data from Firestore"""
import os
import json
import asyncio
import logging
from typing import Optional, List, Collection
from datetime import datetime
from urllib.parse import quote

from src.config import settings
from src.models.podcast import Podcast, Episode
from src.schemas.search import SearchResultItem
from src.tag_registry import trending_slugs
from src.database.postgres import get_session
from src.cache.redis_client import cache_get, cache_set, cache_delete, cache_delete_pattern
from src.cache.cache_config import CACHE_TTL
from src.cache.cdn_cache import purge_cdn_cache

# Per-env API host for Cloudflare edge purges (host-scoped so one env never clears
# another's cache). Mirrors the map in routers/admin_sources.py.
_API_HOST_BY_ENV = {
    "production": "api.tinboker.com",
    "staging": "staging-api.tinboker.com",
    "development": "dev-api.tinboker.com",
}
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
    "marp_markdown_content",
})

_CONTENT_TO_URL = {
    "summary_content": "summary_url",
    "events_markdown_content": "events_markdown_url",
    "sentences_markdown_content": "sentences_markdown_url",
    "modified_summary_content": "modified_summary_url",
    "transcript": "transcript_url",
    "summary_image": "summary_image_url",
    "marp_markdown_content": "marp_markdown_url",
    "ticker_marp_markdown_content": "ticker_marp_markdown_url",
    "ticker_recommendations_content": "ticker_recommendations_public_url",
}

def episode_content_incomplete(
    episode: Episode, content_fields: Optional[Collection[str]] = None,
) -> bool:
    """True if any requested content field has a source URL but empty content."""
    for content_field, url_field in _CONTENT_TO_URL.items():
        if content_fields is not None and content_field not in content_fields:
            continue
        if getattr(episode, url_field, None) and not getattr(episode, content_field, None):
            return True
    return False


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

    async def _purge_episode_cdn(self, episode_id: str, podcast_name: str) -> None:
        """Fire-and-forget CDN purge for an episode's detail URLs.

        Called after successfully hydrating GCS content (Redis cache miss) to evict
        any previously-cached incomplete (blank-content) response from Cloudflare.
        """
        env = getattr(settings, "environment", "development")
        host = _API_HOST_BY_ENV.get(env, "dev-api.tinboker.com")
        base = f"https://{host}"
        urls = [f"{base}/api/episodes/{quote(episode_id, safe='')}"]
        if podcast_name:
            urls.append(
                f"{base}/api/podcast/{quote(podcast_name, safe='')}"
                f"/episodes/{quote(episode_id, safe='')}"
            )
        try:
            await purge_cdn_cache(urls=urls)
        except Exception:
            logger.debug("CDN purge for episode %s failed (non-critical)", episode_id)

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
            # Publish order within a single podcast: episode_number is the reliable
            # monotonic release signal (higher = newer). Fall back to true publish
            # time only when an episode has no number. NEVER sort by created_time
            # here — that is ingestion time, so re-ingested old episodes float to
            # the top and interleave with recent ones.
            def _publish_key(x):
                return (x.episode_number if x.episode_number is not None else -1,
                        self._episode_release_ms(x))
            sort_keys = {
                "created_time": lambda x: x.created_time or 0,
                "episode_number": lambda x: x.episode_number if x.episode_number is not None else 0,
                "episode_title": lambda x: (x.episode_title or "").lower(),
                "spotify_release_date": _publish_key,
                "released_at_ms": _publish_key,
                "publish": _publish_key,
            }
            episodes = sorted(episodes, key=sort_keys.get(sort_by, _publish_key), reverse=reverse)
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
            if not self.transformer.is_content_incomplete(episode_dict, content_fields=content_fields):
                try:
                    await cache_set(cache_key, json.dumps(episode.dict(), default=str), CACHE_TTL["podcast_episode"])
                except Exception:
                    pass
                asyncio.create_task(self._purge_episode_cdn(episode_id, podcast_name))
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

    async def get_episode_audio_signed_url(
        self, podcast_name: str, episode_id: str
    ) -> Optional[str]:
        """Short-lived signed GCS URL for an episode's MP3, or None if unavailable.

        The mp3 blobs in graphfolio-articles are private (no public ACL), so the
        player streams them through a signed URL instead of mp3_public_url.
        """
        episode_dict = self.firestore_service.get_document("episodes", episode_id)
        if not episode_dict or episode_dict.get('podcast_name') != podcast_name:
            return None
        gs_url = episode_dict.get('mp3_url') or episode_dict.get('mp3_public_url')
        if not gs_url:
            return None
        return await self.gcs.generate_signed_url(gs_url)

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
            if not self.transformer.is_content_incomplete(episode_dict, content_fields=content_fields):
                try:
                    await cache_set(cache_key, json.dumps(episode.dict(), default=str), CACHE_TTL["podcast_episode"])
                except Exception:
                    pass
                asyncio.create_task(self._purge_episode_cdn(episode_id, episode.podcast_name))
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

            eids = [ref.get('episode_id') for ref in episode_refs if ref.get('episode_id')]
            dicts = await asyncio.to_thread(
                self.firestore_service.get_documents_batch, "episodes", eids,
            ) if eids else []
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

    @staticmethod
    def _get_topic_tags() -> list[str]:
        """Trending-tier tags from the DB-backed registry."""
        db = next(get_session())
        try:
            return trending_slugs(db)
        finally:
            db.close()

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

            counted = await asyncio.gather(*[_count(t) for t in self._get_topic_tags()])
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
        """Get episodes for a specific tag (batch-read for performance)."""
        try:
            allowed = await self._allowed_podcast_names()
            cutoff = self._recency_cutoff_ms()
            scoping_active = allowed is not None or cutoff is not None
            fetch_limit = max((limit + offset) * 5, 100) if scoping_active else (limit + offset)
            episode_refs = await asyncio.to_thread(
                self.firestore_service.get_subcollection_documents,
                collection="tags", parent_doc_id=tag.lower(),
                subcollection="episodes", order_by="created_time",
                direction="DESCENDING", limit=fetch_limit,
            )
            eids = [ref.get('episode_id') for ref in episode_refs if ref.get('episode_id')]
            dicts = await asyncio.to_thread(
                self.firestore_service.get_documents_batch, "episodes", eids,
            ) if eids else []
            episodes = await asyncio.gather(
                *[self.transformer.to_episode(d, enrich_content=enrich_content) for d in dicts]
            )
            episodes = self._scope_episodes(list(episodes), allowed, cutoff)
            return episodes[offset:offset + limit]
        except Exception as e:
            raise Exception(f"Failed to get episodes by tag: {e}") from e

    async def get_episodes_by_sector(
        self,
        exposure_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        """Get episodes where sector_exposure_ids array contains exposure_id.

        Returns a dict with exposure metadata (display_name, exposure_type,
        resolved_tickers aggregated across matched episodes) plus the episode list.
        All release-scoping and content-empty guards are applied identically to
        get_episodes_by_tag.
        """
        cache_key = f"sector:episodes:v1:{exposure_id}:{offset}:{limit}:{self._scope_tag()}"
        cached = await cache_get(cache_key)
        if cached:
            try:
                return json.loads(cached)
            except Exception:
                pass

        allowed = await self._allowed_podcast_names()
        cutoff = self._recency_cutoff_ms()
        scoping_active = allowed is not None or cutoff is not None
        # Over-fetch when scoping is active so we still hit limit after filtering
        fetch_limit = max((limit + offset) * 5, 100) if scoping_active else (limit + offset)

        try:
            dicts = await asyncio.to_thread(
                self.firestore_service.query_collection,
                "episodes",
                [("sector_exposure_ids", "array-contains", exposure_id)],
                None,       # no Firestore-side ordering — sort in Python to avoid composite index
                None,
                fetch_limit,
            )
        except Exception as e:
            raise Exception(f"Failed to query episodes by sector: {e}") from e

        # Sort by publish time descending in Python
        dicts.sort(key=lambda d: self._dict_release_ms(d), reverse=True)

        # Build Episode objects and apply release scope + content guard.
        # enrich_content=False keeps this a lean list view (no transcript/summary
        # GCS hydration) — same as get_episodes_by_tag, so the sector page payload
        # stays small and the page renders fast.
        episodes_raw = await asyncio.gather(
            *[self.transformer.to_episode(d, enrich_content=False) for d in dicts]
        )
        episodes = self._scope_episodes(list(episodes_raw), allowed, cutoff)

        # --- Derive metadata from ALL matched episodes (pre-scope) ---
        # Use episodes_raw, not the scoped list, so the friendly display_name and
        # representative tickers still render when every matched episode is filtered
        # out by the release scope (otherwise the page would show the raw exposure_id
        # as its title with no tickers).
        display_name = exposure_id
        exposure_type = "sector"
        seen_tickers: dict[str, dict] = {}  # ticker -> first-seen entry
        exposure_counts: dict[str, int] = {}  # display_name -> count, for majority vote

        for ep in episodes_raw:
            for entry in ep.sector_exposures:
                if entry.get("exposure_id") != exposure_id:
                    continue
                dn = entry.get("display_name") or exposure_id
                exposure_counts[dn] = exposure_counts.get(dn, 0) + 1
                et = entry.get("exposure_type") or "sector"
                # Use the type from the most-frequent display_name entry (updated below)
                # For now capture the first one seen; we overwrite with majority below
                for rt in entry.get("resolved_tickers") or []:
                    ticker = rt.get("ticker") or ""
                    if ticker and ticker not in seen_tickers:
                        seen_tickers[ticker] = {
                            "ticker": ticker,
                            "name": rt.get("name") or "",
                            "name_en": rt.get("name_en"),
                            "market": rt.get("market") or "",
                            "source": rt.get("source") or "",
                        }
                # Track exposure_type alongside display_name for the winner
                # Store as tuple (display_name, exposure_type) frequency
                key = (dn, et)
                exposure_counts[key] = exposure_counts.get(key, 0) + 1  # type: ignore[assignment]

        # Pick display_name/exposure_type from most-frequent (dn, et) pair
        best_key = max(
            [(k, v) for k, v in exposure_counts.items() if isinstance(k, tuple)],
            key=lambda x: x[1],
            default=(None, 0),
        )[0]
        if best_key:
            display_name, exposure_type = best_key

        resolved_tickers = list(seen_tickers.values())[:12]

        paged = episodes[offset:offset + limit]
        result = {
            "exposure_id": exposure_id,
            "display_name": display_name,
            "exposure_type": exposure_type,
            "resolved_tickers": resolved_tickers,
            "episodes": [ep.dict() for ep in paged],
            "total": len(episodes),
        }

        try:
            await cache_set(cache_key, json.dumps(result), CACHE_TTL["podcast_episodes"])
        except Exception:
            pass

        return result

    # ── Sector board constants ────────────────────────────────────────
    _BOARD_W_PRICE: float = 0.5
    _BOARD_W_MENTION: float = 0.5

    async def sector_member_tickers(self) -> list[str]:
        """Union of every sector/theme basket ticker across scoped episodes (no prices).

        The daily-close refresher uses this so price diffs are warm for ALL board
        constituents, not just individually-trending tickers. Scan-based + cached,
        mirroring list_sectors' scoping (retracted / allowlist / recency).
        """
        cache_key = f"sectors:tickers:v1:{self._scope_tag()}"
        cached = await cache_get(cache_key)
        if cached:
            try:
                return json.loads(cached)
            except Exception:
                pass
        allowed = await self._allowed_podcast_names()
        cutoff = self._recency_cutoff_ms()
        try:
            docs = await asyncio.to_thread(self.firestore_service.get_all_documents, "episodes")
        except Exception as e:
            logger.warning("sector_member_tickers scan failed: %s", e)
            return []
        seen: set = set()
        out: list[str] = []
        for doc in docs:
            if doc.get("retracted_at"):
                continue
            if allowed is not None and doc.get("podcast_name") not in allowed:
                continue
            if cutoff is not None and self._dict_release_ms(doc) < cutoff:
                continue
            for entry in doc.get("sector_exposures") or []:
                for rt in entry.get("resolved_tickers") or []:
                    t = str(rt.get("ticker") or "").strip().upper()
                    if t and t not in seen:
                        seen.add(t)
                        out.append(t)
        try:
            await cache_set(cache_key, json.dumps(out), CACHE_TTL["podcast_episodes"])
        except Exception:
            pass
        return out

    async def sector_board(self) -> list[dict]:
        """Return a ranked 'hot sectors' board with price performance.

        Each sector entry includes its constituent tickers' daily % change,
        an avg_change aggregate, and a blended hotness score (0..1) that
        weights price performance equally with episode-mention frequency.

        Applies the same release scoping as list_sectors (retracted_at,
        allowlist, recency cutoff).  Prices are fetched from the local
        stock_daily_closes table via get_eod_change_pct — no external API
        calls per request.

        Cache TTL matches podcast_episodes (10 min) so prices stay fresh.
        """
        cache_key = f"sectors:board:v2:{self._scope_tag()}"
        cached = await cache_get(cache_key)
        if cached:
            try:
                return json.loads(cached)
            except Exception:
                pass

        allowed = await self._allowed_podcast_names()
        cutoff = self._recency_cutoff_ms()

        try:
            docs = await asyncio.to_thread(
                self.firestore_service.get_all_documents, "episodes"
            )
        except Exception as e:
            raise Exception(f"Failed to scan episodes for sector board: {e}") from e

        # Tally per sector: episode count, first-seen meta, union of tickers (cap 12)
        counts: dict[str, int] = {}
        meta: dict[str, dict] = {}       # exposure_id -> {display_name, exposure_type}
        ticker_map: dict[str, dict[str, str]] = {}  # exposure_id -> {ticker: first-seen name}

        for doc in docs:
            if doc.get("retracted_at"):
                continue
            if allowed is not None and doc.get("podcast_name") not in allowed:
                continue
            if cutoff is not None and self._dict_release_ms(doc) < cutoff:
                continue
            for entry in doc.get("sector_exposures") or []:
                eid = entry.get("exposure_id") or ""
                if not eid:
                    continue
                counts[eid] = counts.get(eid, 0) + 1
                if eid not in meta:
                    meta[eid] = {
                        "display_name": entry.get("display_name") or eid,
                        "exposure_type": entry.get("exposure_type") or "sector",
                    }
                sector_tickers = ticker_map.setdefault(eid, {})
                for rt in entry.get("resolved_tickers") or []:
                    ticker = (rt.get("ticker") or "").strip()
                    if ticker and ticker not in sector_tickers and len(sector_tickers) < 12:
                        sector_tickers[ticker] = rt.get("name") or ""

        if not counts:
            try:
                await cache_set(cache_key, json.dumps([]), CACHE_TTL["podcast_episodes"])
            except Exception:
                pass
            return []

        # Gather all unique tickers and fetch EOD change% concurrently
        from src.services.stock_close_refresh import get_eod_change_pct
        from src.database.models import StockDailyClose

        all_tickers: list[str] = list({
            t for tickers in ticker_map.values() for t in tickers
        })
        pcts = await asyncio.gather(*[get_eod_change_pct(t) for t in all_tickers])
        ticker_pct: dict[str, Optional[float]] = dict(zip(all_tickers, pcts))

        # Batch-read daily closes for sparkline series (last 12 per ticker)
        _SERIES_LIMIT = 12
        _CHUNK_SIZE = 200

        def _batch_read_closes(tickers: list[str]) -> dict[str, list[float]]:
            """Sync: query StockDailyClose for all tickers, return ordered close lists."""
            result_map: dict[str, list[float]] = {}
            for session in get_session():
                try:
                    for chunk_start in range(0, len(tickers), _CHUNK_SIZE):
                        chunk = tickers[chunk_start: chunk_start + _CHUNK_SIZE]
                        rows = (
                            session.query(
                                StockDailyClose.ticker,
                                StockDailyClose.date,
                                StockDailyClose.close,
                            )
                            .filter(StockDailyClose.ticker.in_(chunk))
                            .order_by(StockDailyClose.ticker.asc(), StockDailyClose.date.asc())
                            .all()
                        )
                        for ticker, _date, close in rows:
                            result_map.setdefault(ticker, []).append(close)
                except Exception as exc:
                    logger.debug(f"sector_board: close series read failed: {exc}")
                break
            # Trim to last _SERIES_LIMIT points
            return {t: closes[-_SERIES_LIMIT:] for t, closes in result_map.items()}

        ticker_series: dict[str, list[float]] = {}
        if all_tickers:
            ticker_series = await asyncio.to_thread(_batch_read_closes, all_tickers)

        # Build per-sector members + avg_change
        sectors_raw: list[dict] = []
        for eid, count in counts.items():
            members_unsorted: list[dict] = []
            for ticker, name in ticker_map.get(eid, {}).items():
                closes = ticker_series.get(ticker, [])
                members_unsorted.append({
                    "ticker": ticker,
                    "name": name,
                    "change_percent": ticker_pct.get(ticker),
                    "series": closes if len(closes) >= 2 else [],
                })
            # Sort members: non-None change_percent DESC, then None last
            members = sorted(
                members_unsorted,
                key=lambda m: (m["change_percent"] is None, -(m["change_percent"] or 0.0)),
            )

            non_null = [m["change_percent"] for m in members if m["change_percent"] is not None]
            avg_change: Optional[float] = (sum(non_null) / len(non_null)) if non_null else None

            # Compute sector series: element-wise mean of rebased member series.
            # Rebase each member's closes to 100 at first point, then align to the
            # shortest length by taking the trailing K points, then average across members.
            member_rebased: list[list[float]] = []
            for m in members:
                s = m["series"]
                if len(s) >= 2:
                    base = s[0]
                    if base:
                        member_rebased.append([v / base * 100.0 for v in s])
            if member_rebased:
                min_len = min(len(r) for r in member_rebased)
                aligned = [r[-min_len:] for r in member_rebased]
                sector_series: list[float] = [
                    sum(col) / len(col) for col in zip(*aligned)
                ]
            else:
                sector_series = []

            sectors_raw.append({
                "exposure_id": eid,
                "display_name": meta[eid]["display_name"],
                "exposure_type": meta[eid]["exposure_type"],
                "episode_count": count,
                "avg_change": avg_change,
                "members": members,
                "series": sector_series,
            })

        # Min-max normalise avg_change and episode_count to 0..1, blend into hotness
        all_avgs = [s["avg_change"] for s in sectors_raw]
        all_counts = [s["episode_count"] for s in sectors_raw]

        min_avg = min((v for v in all_avgs if v is not None), default=0.0)
        max_avg = max((v for v in all_avgs if v is not None), default=0.0)
        min_cnt = min(all_counts)
        max_cnt = max(all_counts)

        def _norm_avg(v: Optional[float]) -> float:
            if v is None:
                return 0.0
            span = max_avg - min_avg
            if span == 0:
                return 0.5
            return (v - min_avg) / span

        def _norm_cnt(v: int) -> float:
            span = max_cnt - min_cnt
            if span == 0:
                return 0.5
            return (v - min_cnt) / span

        result: list[dict] = []
        for s in sectors_raw:
            hotness = (
                self._BOARD_W_PRICE * _norm_avg(s["avg_change"])
                + self._BOARD_W_MENTION * _norm_cnt(s["episode_count"])
            )
            result.append({**s, "hotness": hotness})

        result.sort(key=lambda x: x["hotness"], reverse=True)

        try:
            await cache_set(cache_key, json.dumps(result), CACHE_TTL["podcast_episodes"])
        except Exception:
            pass

        return result

    async def list_sectors(self) -> list[dict]:
        """Return all sector/theme exposures that appear in at least one episode, with counts.

        Scans every episode document in Firestore and tallies exposure_id occurrences
        across each doc's sector_exposures list, applying the same release scoping as
        get_episodes_by_sector (retracted, allowlist, recency cutoff).

        NOTE: this is a full-collection scan on cache miss.  A maintained counter doc
        (e.g. Firestore aggregation or pipeline-written summary) could eliminate the
        scan later — defer until traffic warrants it.

        Returns list of dicts sorted by count DESC then exposure_id ASC.
        """
        cache_key = f"sectors:list:v1:{self._scope_tag()}"
        cached = await cache_get(cache_key)
        if cached:
            try:
                return json.loads(cached)
            except Exception:
                pass

        allowed = await self._allowed_podcast_names()
        cutoff = self._recency_cutoff_ms()

        try:
            docs = await asyncio.to_thread(
                self.firestore_service.get_all_documents, "episodes"
            )
        except Exception as e:
            raise Exception(f"Failed to scan episodes for sectors: {e}") from e

        # Tally exposures across scoped episodes
        counts: dict[str, int] = {}
        meta: dict[str, dict] = {}  # exposure_id -> first-seen {display_name, exposure_type}

        for doc in docs:
            if doc.get("retracted_at"):
                continue
            if allowed is not None and doc.get("podcast_name") not in allowed:
                continue
            if cutoff is not None and self._dict_release_ms(doc) < cutoff:
                continue
            for entry in doc.get("sector_exposures") or []:
                eid = entry.get("exposure_id") or ""
                if not eid:
                    continue
                counts[eid] = counts.get(eid, 0) + 1
                if eid not in meta:
                    meta[eid] = {
                        "display_name": entry.get("display_name") or eid,
                        "exposure_type": entry.get("exposure_type") or "sector",
                    }

        result = sorted(
            [
                {
                    "exposure_id": eid,
                    "display_name": meta[eid]["display_name"],
                    "exposure_type": meta[eid]["exposure_type"],
                    "count": cnt,
                }
                for eid, cnt in counts.items()
            ],
            key=lambda x: (-x["count"], x["exposure_id"]),
        )

        try:
            await cache_set(cache_key, json.dumps(result), 1800)
        except Exception:
            pass

        return result

    async def get_trending_tags(self, weeks: int = 6, preview_count: int = 3) -> List[dict]:
        """Return curated tags with scoped counts, weekly sparkline data, and episode previews.
        Results are cached for 30 minutes. Tags with 0 scoped episodes are omitted."""
        cache_key = f"tags:trending:v1:{weeks}:{preview_count}:{self._scope_tag()}"
        cached = await cache_get(cache_key)
        if cached:
            try:
                return json.loads(cached)
            except Exception:
                pass
        allowed = await self._allowed_podcast_names()
        cutoff = self._recency_cutoff_ms()
        now_ms = int(datetime.now().timestamp() * 1000)
        week_ms = 7 * 24 * 3600 * 1000
        week_boundaries = [now_ms - i * week_ms for i in range(weeks + 1)]
        sem = asyncio.Semaphore(6)

        async def _process_tag(tid: str) -> Optional[dict]:
            async with sem:
                try:
                    refs = await asyncio.to_thread(
                        self.firestore_service.get_subcollection_documents,
                        collection="tags", parent_doc_id=tid,
                        subcollection="episodes", order_by="created_time",
                        direction="DESCENDING", limit=200,
                    )
                    eids = [r.get('episode_id') for r in refs if r.get('episode_id')]
                    if not eids:
                        return None
                    dicts = await asyncio.to_thread(
                        self.firestore_service.get_documents_batch, "episodes", eids,
                    )
                    scoped_dicts = []
                    for d in dicts:
                        if not self._dict_has_content(d):
                            continue
                        if allowed is not None and d.get('podcast_name') not in allowed:
                            continue
                        if cutoff is not None and self._dict_release_ms(d) < cutoff:
                            continue
                        scoped_dicts.append(d)
                    if not scoped_dicts:
                        return None
                    scoped_dicts.sort(key=lambda d: self._dict_release_ms(d), reverse=True)
                    weekly = [0] * weeks
                    for d in scoped_dicts:
                        t = self._dict_release_ms(d)
                        for w in range(weeks):
                            if t >= week_boundaries[w + 1]:
                                weekly[w] += 1
                                break
                    previews = []
                    for d in scoped_dicts[:preview_count]:
                        previews.append({
                            "id": d.get("id", ""),
                            "title": d.get("episode_title", ""),
                            "podcast_name": d.get("podcast_name", ""),
                            "released_at_ms": self._dict_release_ms(d),
                            "key_insights": (d.get("key_insights") or [])[:3],
                            "related_tickers": (d.get("related_tickers") or [])[:4],
                        })
                    return {
                        "id": tid, "name": tid,
                        "scoped_count": len(scoped_dicts),
                        "weekly_counts": weekly,
                        "recent_episodes": previews,
                    }
                except Exception:
                    logger.warning("Failed to process trending tag %s", tid, exc_info=True)
                    return None

        results = await asyncio.gather(*[_process_tag(t) for t in self._get_topic_tags()])
        tags = sorted([r for r in results if r], key=lambda x: x["scoped_count"], reverse=True)
        try:
            await cache_set(cache_key, json.dumps(tags), 1800)
        except Exception:
            pass
        return tags

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

    async def patch_episode_fields(
        self, podcast_name: str, episode_id: str,
        updates: dict,
    ) -> Episode:
        """Patch allowed fields directly in Firestore (dev debug editor)."""
        from fastapi import HTTPException
        allowed = {"summary_content", "key_insights", "related_tickers", "tags"}
        bad_keys = set(updates.keys()) - allowed
        if bad_keys:
            raise HTTPException(status_code=422, detail=f"Fields not patchable: {', '.join(sorted(bad_keys))}")
        if not updates:
            raise HTTPException(status_code=422, detail="No fields to update")
        episode_dict = self.firestore_service.get_document("episodes", episode_id)
        if not episode_dict:
            raise HTTPException(status_code=404, detail=f"Episode {episode_id} not found")
        if episode_dict.get("podcast_name") != podcast_name:
            raise HTTPException(status_code=404, detail=f"Episode {episode_id} not found for podcast {podcast_name}")
        try:
            await asyncio.to_thread(
                self.firestore_service.set_document, "episodes", episode_id, updates, True,
            )
            await self._invalidate_episode_cache(podcast_name, episode_id)
            # When related_tickers change (e.g. a content regen), the per-ticker
            # sentiment cards are served from a separate ticker_insights:* cache the
            # episode bust above does NOT cover — clear it too.
            if "related_tickers" in updates:
                await self._invalidate_ticker_insight_cache(podcast_name)
            # Refresh the Cloudflare edge for this env so the patched content shows
            # immediately instead of waiting out s-maxage (≤1h). Best-effort.
            await self._purge_api_host_cdn()
            return await self.get_episode_by_id(podcast_name, episode_id, apply_scope=False)
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to patch episode fields: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to patch episode: {str(e)}")

    async def get_episode_admin(
        self,
        episode_id: str,
        content_fields: Optional[Collection[str]] = EPISODE_DETAIL_CONTENT_FIELDS,
    ) -> Optional[Episode]:
        """Fetch an episode for admin tooling — no release-scope filtering.

        The public getters drop episodes outside the launch scope (language /
        recency); admin must see every episode, so this reads Firestore directly.
        """
        episode_dict = self.firestore_service.get_document("episodes", episode_id)
        if not episode_dict:
            return None
        return await self.transformer.to_episode(episode_dict, content_fields=content_fields)

    async def set_social_thread(self, episode_id: str, thread: dict) -> Episode:
        """Persist the human-tone Threads copy (post + comments) + bust caches."""
        from fastapi import HTTPException
        episode_dict = self.firestore_service.get_document("episodes", episode_id)
        if not episode_dict:
            raise HTTPException(status_code=404, detail=f"Episode {episode_id} not found")
        podcast_name = episode_dict.get("podcast_name", "")
        try:
            await asyncio.to_thread(
                self.firestore_service.set_document,
                "episodes", episode_id, {"social_thread": thread}, True,
            )
            await self._invalidate_episode_cache(podcast_name, episode_id)
            await self._purge_api_host_cdn()
            episode = await self.get_episode_admin(episode_id)
            if not episode:
                raise HTTPException(status_code=404, detail=f"Episode {episode_id} not found")
            return episode
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to set social_thread for {episode_id}: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to save social thread: {str(e)}")

    async def _invalidate_episode_cache(self, podcast_name: str, episode_id: str):
        """Invalidate all caches related to an episode"""
        await cache_delete(f"podcast:{podcast_name}:episode:{episode_id}")
        await cache_delete_pattern(f"podcast:{podcast_name}:episode:{episode_id}:*")
        await cache_delete_pattern(f"episode:{episode_id}:*")
        await cache_delete_pattern(f"podcast:{podcast_name}:episodes:*")
        await cache_delete_pattern("episodes:recent:*")

    async def _invalidate_ticker_insight_cache(self, podcast_name: str):
        """Bust the ticker-sentiment caches (by-ticker / by-podcaster / trending).

        These are keyed independently of the episode doc, so an episode edit that
        changes related_tickers / ticker sentiment must clear them explicitly or the
        detail-page sentiment cards stay stale for up to INSIGHT_TTL (2h).
        Best-effort: a cache hiccup must not fail the write.
        """
        for pattern in (
            "ticker_insights:by_ticker:*",
            f"ticker_insights:by_podcaster:{podcast_name}:*",
            "ticker_insights:trending:*",
        ):
            try:
                await cache_delete_pattern(pattern)
            except Exception as e:
                logger.warning("ticker insight cache invalidation failed for %s: %s", pattern, e)

    async def _purge_api_host_cdn(self):
        """Host-purge this env's API host at Cloudflare (the confirmed-working method
        on the tinboker zone). Host-scoped so a dev/staging edit never clears another
        env's edge cache; never purge_everything. Best-effort — logged, never raised."""
        host = _API_HOST_BY_ENV.get((settings.environment or "").lower())
        if not host:
            return
        try:
            await purge_cdn_cache(hosts=[host])
        except Exception as e:
            logger.warning("episode CDN purge failed for host %s: %s", host, e)


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
