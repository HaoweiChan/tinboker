"""Episode data transformation: Firestore dicts -> Episode models with GCS enrichment"""
import re
import asyncio
import logging
from typing import Optional, Collection
from datetime import datetime
from src.models.podcast import Episode
from src.services.gcs_content import GCSContentService


logger = logging.getLogger(__name__)

# Content fields that can be fetched from GCS
_GCS_CONTENT_FIELDS = [
    ('summary_content', 'summary_url', 'gcs'),
    ('transcript', 'transcript_url', 'gcs'),
    ('summary_image', 'summary_image_url', 'gcs'),
    ('events_markdown_content', 'events_markdown_url', 'gcs'),
    ('sentences_markdown_content', 'sentences_markdown_url', 'gcs'),
    ('marp_markdown_content', 'marp_markdown_url', 'gcs'),
    ('modified_summary_content', 'modified_summary_url', 'gcs'),
    ('ticker_marp_markdown_content', 'ticker_marp_markdown_url', 'any'),
    ('ticker_insights_content', 'ticker_insights_public_url', 'any'),
]


class EpisodeTransformer:
    """Converts raw Firestore dicts to Episode models, optionally enriching with GCS content"""

    def __init__(self, gcs_service: Optional[GCSContentService] = None):
        self.gcs = gcs_service or GCSContentService()

    @staticmethod
    def _normalize_legacy_insight_fields(episode_dict: dict) -> dict:
        """Map old episode artifact fields into the current ticker_insights names."""
        legacy_map = {
            'ticker_insights_url': 'ticker_recommendations_url',
            'ticker_insights_public_url': 'ticker_recommendations_public_url',
            'ticker_insights_content': 'ticker_recommendations_content',
        }
        for new_field, old_field in legacy_map.items():
            if not episode_dict.get(new_field) and episode_dict.get(old_field):
                episode_dict[new_field] = episode_dict[old_field]
        return episode_dict

    async def enrich_with_content(
        self,
        episode_dict: dict,
        content_fields: Optional[Collection[str]] = None,
    ) -> dict:
        """Fetch missing content fields from GCS/HTTP URLs in parallel.

        Only non-empty fetch results overwrite a field. An empty result means the
        fetch failed (the fetchers swallow all errors into ""), so we leave the field
        untouched rather than persisting a blank — see is_content_incomplete, which the
        caller uses to avoid caching a half-hydrated episode.
        """
        episode_dict = self._normalize_legacy_insight_fields(episode_dict)
        requested_fields = set(content_fields) if content_fields is not None else None
        fetch_tasks = []
        for content_field, url_field, fetch_type in _GCS_CONTENT_FIELDS:
            if requested_fields is not None and content_field not in requested_fields:
                continue
            if not episode_dict.get(content_field) and episode_dict.get(url_field):
                url = episode_dict[url_field]
                fetcher = self.gcs.fetch_gcs_content if fetch_type == 'gcs' else self.gcs.fetch_url_content
                fetch_tasks.append((content_field, fetcher(url)))

        if fetch_tasks:
            try:
                results = await asyncio.wait_for(
                    asyncio.gather(*[t for _, t in fetch_tasks], return_exceptions=True),
                    timeout=30.0,
                )
                for (field_name, _), result in zip(fetch_tasks, results):
                    # Skip Exceptions and empty strings: both signal a failed/transient
                    # fetch. Overwriting with "" is what poisoned cached episodes before.
                    if not isinstance(result, Exception) and result:
                        episode_dict[field_name] = result
            except (asyncio.TimeoutError, Exception):
                pass
        return episode_dict

    @staticmethod
    def is_content_incomplete(
        episode_dict: dict,
        content_fields: Optional[Collection[str]] = None,
    ) -> bool:
        """True if any GCS-backed field is still empty while its source URL is set.

        Signals a failed/partial hydration: the URL promises content but we have none.
        Callers use this to skip caching so the next request re-attempts the GCS read
        instead of pinning a blank result for the full TTL.
        """
        episode_dict = EpisodeTransformer._normalize_legacy_insight_fields(episode_dict)
        requested_fields = set(content_fields) if content_fields is not None else None
        return any(
            episode_dict.get(url_field) and not episode_dict.get(content_field)
            for content_field, url_field, _ in _GCS_CONTENT_FIELDS
            if requested_fields is None or content_field in requested_fields
        )

    @staticmethod
    def datetime_to_timestamp_ms(dt) -> int:
        """Convert datetime (or ISO string) to Unix timestamp in milliseconds"""
        if isinstance(dt, str):
            dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
        if isinstance(dt, datetime):
            return int(dt.timestamp() * 1000)
        return int(datetime.now().timestamp() * 1000)

    @staticmethod
    def _normalize_released_at_ms(value) -> Optional[int]:
        """Normalize a raw released_at_ms value to Unix milliseconds, or None.

        Unlike created_time, this never falls back to now(): a missing publish
        time stays None so callers can decide how to treat unknown-date episodes.
        Accepts int/float ms, a datetime, or an ISO-8601 string.
        """
        if value is None:
            return None
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return int(value)
        if isinstance(value, datetime):
            return int(value.timestamp() * 1000)
        if isinstance(value, str):
            s = value.strip()
            if not s:
                return None
            if s.isdigit():
                return int(s)
            try:
                return int(datetime.fromisoformat(s.replace('Z', '+00:00')).timestamp() * 1000)
            except ValueError:
                return None
        return None

    @staticmethod
    def extract_tags_from_text(text: str) -> set:
        """Extract tag IDs from markdown links like [Name](#tag:ID)"""
        if not text:
            return set()
        try:
            return set(re.findall(r"\[.*?\]\(#tag:(.*?)\)", text))
        except Exception:
            return set()

    async def to_episode(
        self,
        episode_dict: dict,
        enrich_content: bool = True,
        content_fields: Optional[Collection[str]] = None,
    ) -> Episode:
        """Convert a Firestore episode dict to an Episode model"""
        episode_dict = self._normalize_legacy_insight_fields(episode_dict)

        if enrich_content:
            episode_dict = await self.enrich_with_content(episode_dict, content_fields=content_fields)

        # Merge extracted + existing tags
        extracted = set()
        for field in ('summary_content', 'events_markdown_content', 'sentences_markdown_content'):
            extracted.update(self.extract_tags_from_text(episode_dict.get(field, '')))
        existing = set(episode_dict.get('tags', []) or [])
        all_tags = [t for t in existing.union(extracted) if t]

        created_time = episode_dict.get('created_time')
        if isinstance(created_time, str):
            created_time = datetime.fromisoformat(created_time.replace('Z', '+00:00'))
        elif not isinstance(created_time, datetime):
            created_time = datetime.now()

        released_at_ms = self._normalize_released_at_ms(episode_dict.get('released_at_ms'))

        return Episode(
            id=episode_dict.get('id') or episode_dict.get('episode_id', ''),
            podcast_name=episode_dict.get('podcast_name', ''),
            episode_title=episode_dict.get('episode_title'),
            episode_number=episode_dict.get('episode_number'),
            transcript=episode_dict.get('transcript', ''),
            summary_content=episode_dict.get('summary_content', ''),
            summary_image=episode_dict.get('summary_image', ''),
            related_tickers=episode_dict.get('related_tickers', []),
            tags=all_tags,
            created_time=self.datetime_to_timestamp_ms(created_time),
            released_at_ms=released_at_ms,
            number_click=episode_dict.get('number_click', 0),
            num_likes=episode_dict.get('num_likes', 0),
            key_insights=episode_dict.get('key_insights', []) or [],
            social_cards=episode_dict.get('social_cards', []) or [],
            raw_mp3=episode_dict.get('raw_mp3'),
            mp3_url=episode_dict.get('mp3_url'),
            transcript_url=episode_dict.get('transcript_url'),
            summary_url=episode_dict.get('summary_url'),
            summary_image_url=episode_dict.get('summary_image_url'),
            events_markdown_url=episode_dict.get('events_markdown_url'),
            sentences_markdown_url=episode_dict.get('sentences_markdown_url'),
            marp_markdown_url=episode_dict.get('marp_markdown_url'),
            mp3_public_url=episode_dict.get('mp3_public_url'),
            transcript_public_url=episode_dict.get('transcript_public_url'),
            summary_public_url=episode_dict.get('summary_public_url'),
            summary_image_public_url=episode_dict.get('summary_image_public_url'),
            events_markdown_public_url=episode_dict.get('events_markdown_public_url'),
            sentences_markdown_public_url=episode_dict.get('sentences_markdown_public_url'),
            marp_markdown_public_url=episode_dict.get('marp_markdown_public_url'),
            events_markdown_content=episode_dict.get('events_markdown_content'),
            sentences_markdown_content=episode_dict.get('sentences_markdown_content'),
            marp_markdown_content=episode_dict.get('marp_markdown_content'),
            spotify_embed_url=episode_dict.get('spotify_embed_url'),
            spotify_id=episode_dict.get('spotify_id'),
            spotify_url=episode_dict.get('spotify_url'),
            spotify_release_date=episode_dict.get('spotify_release_date'),
            spotify_description=episode_dict.get('spotify_description'),
            spotify_duration_ms=episode_dict.get('spotify_duration_ms'),
            spotify_images=episode_dict.get('spotify_images', []),
            modified_summary_url=episode_dict.get('modified_summary_url'),
            modified_summary_content=episode_dict.get('modified_summary_content'),
            modified_by=episode_dict.get('modified_by'),
            modified_at=episode_dict.get('modified_at'),
            ticker_marp_markdown_url=episode_dict.get('ticker_marp_markdown_url'),
            ticker_marp_markdown_public_url=episode_dict.get('ticker_marp_markdown_public_url'),
            ticker_marp_markdown_content=episode_dict.get('ticker_marp_markdown_content'),
            ticker_insights_url=episode_dict.get('ticker_insights_url'),
            ticker_insights_public_url=episode_dict.get('ticker_insights_public_url'),
            ticker_insights_content=episode_dict.get('ticker_insights_content'),
        )
