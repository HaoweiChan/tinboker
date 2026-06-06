"""
Pipeline utility functions.

Helper functions used across pipeline steps.
"""

import re
from datetime import datetime, timezone
from typing import Dict, List, Optional

from src.models.podcast_models import PodcastEpisode, Sentence


def determine_language(podcast_name: str) -> str:
    """Determine language code based on podcast name."""
    chinese_indicators = ['股癌', '財經', '財女', '珍妮']
    for indicator in chinese_indicators:
        if indicator in podcast_name:
            return "zh"
    return "en"


def convert_sentences_to_markdown(sentences: List[Sentence]) -> str:
    """
    Convert sentences to markdown format with timestamps.
    
    Format: Each sentence on a new line with timestamp tag using (#time:milliseconds) structure.
    Example:
    歡迎收聽股癌 (#time:0)
    今天是平安夜 (#time:3000)
    
    Args:
        sentences: List of Sentence objects
        
    Returns:
        Markdown string with sentences and timestamps
    """
    markdown_lines = []
    for sentence in sentences:
        # Get sentence content (handle both Sentence objects and dicts)
        if isinstance(sentence, Sentence):
            content = sentence.content
            start_ms = sentence.start
        elif isinstance(sentence, dict):
            content = sentence.get('content', '')
            start_ms = sentence.get('start', 0)
        else:
            continue
        
        # Skip empty sentences
        if not content or not content.strip():
            continue
        
        # Format: sentence text (#time:milliseconds)
        markdown_lines.append(f"{content} (#time:{start_ms})")
    
    return "\n".join(markdown_lines)


def generate_episode_id(
    firebase_service,
    podcast_name: str,
    episode_data: Dict,
    summary_result: Optional[Dict] = None
) -> str:
    """Generate stable episode ID."""
    temp_episode = PodcastEpisode(
        mp3_url="",
        transcript_url="",
        summary_url="",
        summary_image_url="",
        related_tickers=summary_result.get('related_tickers', []) if summary_result else [],
        created_time=datetime.now(),
        episode_title=episode_data.get('title', ''),
        podcast_name=podcast_name,
        episode_number=episode_data.get('episodeNumber')
    )
    return firebase_service._generate_episode_id(podcast_name, temp_episode)


def extract_tags_from_markdown(markdown_text: str) -> List[str]:
    """
    Extract tags from markdown text by parsing #tag:TAG_NAME patterns.
    
    Args:
        markdown_text: Markdown content with tag links like [Display](#tag:TAG_NAME)
        
    Returns:
        List of unique tag names (normalized to lowercase with underscores)
    """
    if not markdown_text:
        return []
    
    # Pattern to match [Display](#tag:TAG_NAME) or just #tag:TAG_NAME
    pattern = r'#tag:([a-zA-Z0-9_]+)'
    matches = re.findall(pattern, markdown_text, re.IGNORECASE)
    
    # Normalize to lowercase and remove duplicates
    tags = list(set(tag.lower() for tag in matches))
    return sorted(tags)


def extract_tickers_from_markdown(markdown_text: str) -> List[str]:
    """
    Extract tickers from markdown text by parsing #ticker:SYMBOL patterns.
    
    Args:
        markdown_text: Markdown content with ticker links like [Display](#ticker:SYMBOL)
        
    Returns:
        List of unique ticker symbols (uppercase)
    """
    if not markdown_text:
        return []
    
    # Pattern to match [Display](#ticker:SYMBOL) or just #ticker:SYMBOL
    pattern = r'#ticker:([a-zA-Z0-9]+)'
    matches = re.findall(pattern, markdown_text, re.IGNORECASE)
    
    # Normalize to uppercase and remove duplicates
    tickers = list(set(ticker.upper() for ticker in matches))
    return sorted(tickers)


def extract_tags_and_tickers(summary_result: Dict) -> Dict[str, List[str]]:
    """
    Extract tags and tickers from summary result.
    
    Always parses the markdown summary_text for tag/ticker links as the primary source,
    then merges with structured 'tags' and 'related_tickers' arrays if they exist.
    This ensures we capture all tags/tickers from the markdown, even if structured
    format is incomplete.
    
    Args:
        summary_result: Dictionary with 'summary_text', 'tags', 'related_tickers', etc.
        
    Returns:
        Dictionary with 'tags' and 'tickers' lists
    """
    tags = []
    tickers = []
    
    # Always parse markdown first (primary source of truth)
    summary_text = summary_result.get('summary_text', '')
    if summary_text:
        tags = extract_tags_from_markdown(summary_text)
        tickers = extract_tickers_from_markdown(summary_text)
    
    # Merge with structured format if it exists (add any additional tags/tickers)
    if 'tags' in summary_result and isinstance(summary_result['tags'], list):
        structured_tags = [tag.lower() if isinstance(tag, str) else str(tag).lower() for tag in summary_result['tags']]
        # Merge: combine markdown tags with structured tags
        tags = sorted(list(set(tags + structured_tags)))
    
    if 'related_tickers' in summary_result and isinstance(summary_result['related_tickers'], list):
        structured_tickers = [ticker.upper() if isinstance(ticker, str) else str(ticker).upper() for ticker in summary_result['related_tickers']]
        # Only merge tickers that are actually present in the markdown text
        # This ensures validation will pass - all tickers in related_tickers must be in summary
        # Note: tickers from extract_tickers_from_markdown() are already uppercase, so we can use them directly
        tickers_set = set(t.upper() for t in tickers)  # Convert to set for O(1) lookup
        valid_structured_tickers = [t for t in structured_tickers if t in tickers_set]
        # Merge: combine markdown tickers with valid structured tickers (only those in markdown)
        tickers = sorted(list(set(tickers + valid_structured_tickers)))
    
    return {
        'tags': tags,
        'tickers': tickers
    }


def _date_published_to_ms(api_data: Dict) -> Optional[int]:
    """Parse the feed ``datePublished`` (ISO-8601) into Unix milliseconds.

    Reuses the orchestrator's ``_parse_episode_date`` (the single parser for the
    podcasttomp3 ``datePublished`` shape, e.g. ``2026-06-03T07:34:50.000Z``).
    Imported lazily to avoid a circular import: ``orchestrator`` imports the
    ``src.pipeline`` package, which imports this module.
    """
    if not isinstance(api_data, dict):
        return None
    from src.podcast.orchestrator import _parse_episode_date

    dt = _parse_episode_date(api_data.get('datePublished'))
    if dt is None:
        return None
    return int(dt.timestamp() * 1000)


def create_episode_object(
    episode_data,  # EpisodeData object
    gcs_urls: Dict,
    spotify_metadata: Optional[Dict],
    summary_result: Optional[Dict]
) -> PodcastEpisode:
    """Create PodcastEpisode object from processed data."""
    # The feed publish date (datePublished) is the only reliable publish time —
    # spotify_release_date is null for ~all zh-TW episodes and created_time is the
    # ingestion/backfill time. It is the PRIMARY source for released_at_ms.
    feed_date_published_ms = _date_published_to_ms(episode_data.api_data)

    # Determine created_time. NEVER overwrite an existing stored created_time:
    # mutating it re-fires `new_episode` notifications (handoff spec §6.3). Only
    # when there is no stored value AND no Spotify match do we fall back to the
    # feed publish date, then to now() as a last resort.
    created_time = episode_data.created_time
    if not created_time:
        if spotify_metadata and spotify_metadata.get('release_datetime'):
            created_time = spotify_metadata['release_datetime']
        elif feed_date_published_ms is not None:
            created_time = datetime.fromtimestamp(
                feed_date_published_ms / 1000, tz=timezone.utc
            )
        else:
            created_time = datetime.now()

    # Use episode_data.tickers (extracted from markdown + merged with structured) 
    # instead of summary_result.get('related_tickers') to ensure consistency
    # Always prefer episode_data.tickers if it exists (even if empty list) since it's been validated
    if hasattr(episode_data, 'tickers'):
        related_tickers = episode_data.tickers
    elif summary_result:
        related_tickers = summary_result.get('related_tickers', [])
    else:
        related_tickers = []
    
    return PodcastEpisode(
        mp3_url=gcs_urls.get('mp3_url', ''),
        transcript_url=gcs_urls.get('transcript_url', ''),
        summary_url=gcs_urls.get('summary_url', ''),
        summary_image_url=gcs_urls.get('summary_image_url', ''),
        mp3_public_url=gcs_urls.get('mp3_public_url'),
        transcript_public_url=gcs_urls.get('transcript_public_url'),
        summary_public_url=gcs_urls.get('summary_public_url'),
        summary_image_public_url=gcs_urls.get('summary_image_public_url'),
        events_markdown_url=gcs_urls.get('events_markdown_url'),
        events_markdown_public_url=gcs_urls.get('events_markdown_public_url'),
        sentences_markdown_url=gcs_urls.get('sentences_markdown_url'),
        sentences_markdown_public_url=gcs_urls.get('sentences_markdown_public_url'),
        pptx_url=gcs_urls.get('pptx_url'),
        pptx_public_url=gcs_urls.get('pptx_public_url'),
        marp_markdown_url=gcs_urls.get('marp_markdown_url'),
        marp_markdown_public_url=gcs_urls.get('marp_markdown_public_url'),
        ticker_recommendations_url=gcs_urls.get('ticker_recommendations_url'),
        ticker_recommendations_public_url=gcs_urls.get('ticker_recommendations_public_url'),
        ticker_marp_markdown_url=gcs_urls.get('ticker_marp_markdown_url'),
        ticker_marp_markdown_public_url=gcs_urls.get('ticker_marp_markdown_public_url'),
        related_tickers=related_tickers,
        key_insights=summary_result.get('key_insights', []) if summary_result else [],
        social_cards=summary_result.get('social_cards', []) if summary_result else [],
        created_time=created_time,
        feed_date_published_ms=feed_date_published_ms,
        number_click=0,
        num_likes=0,
        episode_title=episode_data.api_data.get('title', ''),
        podcast_name=episode_data.podcast_name,
        episode_number=episode_data.api_data.get('episodeNumber'),
        # Spotify metadata
        spotify_embed_url=spotify_metadata.get('embed_url') if spotify_metadata else None,
        spotify_id=spotify_metadata.get('spotify_id') if spotify_metadata else None,
        spotify_url=spotify_metadata.get('spotify_url') if spotify_metadata else None,
        spotify_release_date=spotify_metadata.get('release_date') if spotify_metadata else None,
        spotify_description=spotify_metadata.get('description') if spotify_metadata else None,
        spotify_duration_ms=spotify_metadata.get('duration_ms') if spotify_metadata else None,
        spotify_images=spotify_metadata.get('images', []) if spotify_metadata else []
    )

