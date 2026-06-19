"""
Podcast data models for Firestore integration.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional


@dataclass
class Sentence:
    """Represents a single sentence in a transcript with timing information."""
    index: int  # Sentence index (0-based)
    content: str  # Sentence text
    start: int  # Start time in milliseconds
    end: int  # End time in milliseconds


@dataclass
class PodcastEpisode:
    """Represents a single podcast episode with all its data."""
    
    # GCS URLs for episode files
    mp3_url: str  # GCS URL for MP3 file (gs://...)
    transcript_url: str  # GCS URL for transcript file (gs://...)
    summary_url: str  # GCS URL for summary markdown file (gs://...)
    summary_image_url: str  # GCS URL for SVG image file (gs://...)
    events_markdown_url: Optional[str] = None  # GCS URL for events markdown file (gs://...)
    sentences_markdown_url: Optional[str] = None  # GCS URL for sentences markdown file (gs://...)
    pptx_url: Optional[str] = None  # GCS URL for PPTX presentation file (gs://...)
    marp_markdown_url: Optional[str] = None  # GCS URL for marp markdown file (gs://...)
    ticker_insights_url: Optional[str] = None  # GCS URL for ticker insights JSON file (gs://...)
    ticker_marp_markdown_url: Optional[str] = None  # GCS URL for ticker marp markdown file (gs://...)
    
    # Optional public HTTPS URLs
    mp3_public_url: Optional[str] = None  # Public HTTPS URL for MP3
    transcript_public_url: Optional[str] = None  # Public HTTPS URL for transcript
    summary_public_url: Optional[str] = None  # Public HTTPS URL for summary
    summary_image_public_url: Optional[str] = None  # Public HTTPS URL for SVG image
    events_markdown_public_url: Optional[str] = None  # Public HTTPS URL for events markdown
    sentences_markdown_public_url: Optional[str] = None  # Public HTTPS URL for sentences markdown
    pptx_public_url: Optional[str] = None  # Public HTTPS URL for PPTX presentation
    marp_markdown_public_url: Optional[str] = None  # Public HTTPS URL for marp markdown
    ticker_insights_public_url: Optional[str] = None  # Public HTTPS URL for ticker insights
    ticker_marp_markdown_public_url: Optional[str] = None  # Public HTTPS URL for ticker marp markdown
    
    # Metadata
    related_tickers: List[str] = field(default_factory=list)  # List of ticker symbols
    key_insights: List[str] = field(default_factory=list)  # 3–8 plain-text zh-TW takeaways
    social_cards: List[Dict] = field(default_factory=list)  # AlphaMemo-style cards (cover + per theme)
    sector_exposures: List[Dict] = field(default_factory=list)  # Broad sector/theme exposure metadata
    unresolved_market_trends: List[Dict] = field(default_factory=list)  # Demand-driven curation candidates
    sector_exposure_ids: List[str] = field(default_factory=list)
    sector_ids: List[str] = field(default_factory=list)
    theme_ids: List[str] = field(default_factory=list)
    unresolved_market_trend_ids: List[str] = field(default_factory=list)
    created_time: datetime = field(default_factory=datetime.now)  # Timestamp
    number_click: int = 0  # Number of clicks
    num_likes: int = 0  # Number of likes
    episode_title: Optional[str] = None  # Episode title
    podcast_name: Optional[str] = None  # Podcast name
    episode_number: Optional[int] = None  # Episode number from API (for stable deduplication)
    
    # Spotify metadata (optional)
    spotify_embed_url: Optional[str] = None  # Spotify embed URL
    spotify_id: Optional[str] = None  # Spotify episode ID
    spotify_url: Optional[str] = None  # Spotify episode URL
    spotify_release_date: Optional[str] = None  # Release date from Spotify (YYYY-MM-DD)
    spotify_description: Optional[str] = None  # Episode description from Spotify
    spotify_duration_ms: Optional[int] = None  # Episode duration in milliseconds
    spotify_images: List[str] = field(default_factory=list)  # List of image URLs from Spotify

    # Spec § 2.3 #1: Unix ms timestamp for the episode's true publish time.
    # Frontends should prefer this over the timezone-fragile string + ms parsing
    # the spec replaced.
    released_at_ms: Optional[int] = None
    retracted_at: Optional[int] = None

    # Feed ``datePublished`` (the podcasttomp3 API value) already converted to
    # Unix ms. This is the *reliable* publish time and the primary source for
    # ``released_at_ms``. It is an input only — never persisted as its own field
    # (see ``to_firestore_dict``); it feeds ``released_at_ms``.
    feed_date_published_ms: Optional[int] = None

    @staticmethod
    def normalize_spotify_release_date(value: object) -> Optional[str]:
        """Coerce Spotify release metadata to the contract's ``YYYY-MM-DD`` string."""
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.date().isoformat()
        if isinstance(value, (int, float)):
            timestamp = float(value)
            if timestamp > 10_000_000_000:
                timestamp = timestamp / 1000
            return datetime.fromtimestamp(timestamp, tz=timezone.utc).date().isoformat()
        if not isinstance(value, str):
            return None
        raw = value.strip()
        if not raw:
            return None
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
            return raw
        if re.fullmatch(r"\d{4}/\d{2}/\d{2}", raw):
            return raw.replace("/", "-")
        if re.fullmatch(r"\d{4}-\d{2}", raw):
            return f"{raw}-01"
        if re.fullmatch(r"\d{4}", raw):
            return f"{raw}-01-01"
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            return dt.date().isoformat()
        except ValueError:
            return None

    def _compute_released_at_ms(self) -> Optional[int]:
        """Resolve the spec § 2.3 #1 ``released_at_ms`` value.

        Preference order (most → least reliable):
          1. an explicitly-set ``released_at_ms`` (lets a caller override),
          2. the feed ``datePublished`` (``feed_date_published_ms``) — the true
             publish time carried from the source API,
          3. ``spotify_release_date`` (YYYY-MM-DD, UTC midnight),
          4. ``created_time`` (ingestion time — last resort; clusters on the
             backfill run, so only used when nothing better exists).
        """
        if self.released_at_ms is not None:
            return self.released_at_ms
        if self.feed_date_published_ms is not None:
            return self.feed_date_published_ms
        normalized_release_date = self.normalize_spotify_release_date(self.spotify_release_date)
        if normalized_release_date:
            try:
                dt = datetime.strptime(normalized_release_date, "%Y-%m-%d")
                return int(dt.replace(tzinfo=timezone.utc).timestamp() * 1000)
            except ValueError:
                pass
        if isinstance(self.created_time, datetime):
            dt = self.created_time
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return int(dt.timestamp() * 1000)
        return None

    def to_firestore_dict(self) -> Dict:
        """
        Convert PodcastEpisode to Firestore document format.

        Returns:
            Dictionary ready for Firestore storage
        """
        result = {
            'mp3_url': self.mp3_url,
            'transcript_url': self.transcript_url,
            'summary_url': self.summary_url,
            'summary_image_url': self.summary_image_url,
            'related_tickers': self.related_tickers,
            'created_time': self.created_time.isoformat() if isinstance(self.created_time, datetime) else self.created_time,
            'number_click': self.number_click,
            'num_likes': self.num_likes,
            'episode_title': self.episode_title,
            'podcast_name': self.podcast_name,
            'episode_number': self.episode_number,
            'retracted_at': self.retracted_at,
        }
        
        # Only write key_insights when we actually have them — on an update()
        # this keeps the write merge-safe (an empty extraction won't clobber a
        # previously-populated value).
        if self.key_insights:
            result['key_insights'] = self.key_insights

        # Same merge-safe rule for the social cards (cover + per-theme).
        if self.social_cards:
            result['social_cards'] = self.social_cards

        result['sector_exposures'] = self.sector_exposures
        result['unresolved_market_trends'] = self.unresolved_market_trends
        result['sector_exposure_ids'] = self.sector_exposure_ids
        result['sector_ids'] = self.sector_ids
        result['theme_ids'] = self.theme_ids
        result['unresolved_market_trend_ids'] = self.unresolved_market_trend_ids

        # Add public URLs if they exist
        if self.mp3_public_url:
            result['mp3_public_url'] = self.mp3_public_url
        if self.transcript_public_url:
            result['transcript_public_url'] = self.transcript_public_url
        if self.summary_public_url:
            result['summary_public_url'] = self.summary_public_url
        if self.summary_image_public_url:
            result['summary_image_public_url'] = self.summary_image_public_url
        if self.events_markdown_url:
            result['events_markdown_url'] = self.events_markdown_url
        if self.events_markdown_public_url:
            result['events_markdown_public_url'] = self.events_markdown_public_url
        if self.sentences_markdown_url:
            result['sentences_markdown_url'] = self.sentences_markdown_url
        if self.sentences_markdown_public_url:
            result['sentences_markdown_public_url'] = self.sentences_markdown_public_url
        if self.pptx_url:
            result['pptx_url'] = self.pptx_url
        if self.pptx_public_url:
            result['pptx_public_url'] = self.pptx_public_url
        if self.marp_markdown_url:
            result['marp_markdown_url'] = self.marp_markdown_url
        if self.marp_markdown_public_url:
            result['marp_markdown_public_url'] = self.marp_markdown_public_url
        if self.ticker_insights_url:
            result['ticker_insights_url'] = self.ticker_insights_url
        if self.ticker_insights_public_url:
            result['ticker_insights_public_url'] = self.ticker_insights_public_url
        if self.ticker_marp_markdown_url:
            result['ticker_marp_markdown_url'] = self.ticker_marp_markdown_url
        if self.ticker_marp_markdown_public_url:
            result['ticker_marp_markdown_public_url'] = self.ticker_marp_markdown_public_url
        
        # Add Spotify metadata if they exist
        if self.spotify_embed_url:
            result['spotify_embed_url'] = self.spotify_embed_url
        if self.spotify_id:
            result['spotify_id'] = self.spotify_id
        if self.spotify_url:
            result['spotify_url'] = self.spotify_url
        normalized_release_date = self.normalize_spotify_release_date(self.spotify_release_date)
        if normalized_release_date:
            # Spec § 2.3 #5: persist as string YYYY-MM-DD regardless of input shape.
            result['spotify_release_date'] = normalized_release_date
        if self.spotify_description:
            result['spotify_description'] = self.spotify_description
        if self.spotify_duration_ms:
            result['spotify_duration_ms'] = self.spotify_duration_ms
        if self.spotify_images:
            result['spotify_images'] = self.spotify_images

        # Spec § 2.3 #1: release timestamp as Unix ms for sort/display.
        released_ms = self._compute_released_at_ms()
        if released_ms is not None:
            result['released_at_ms'] = released_ms

        return result
    
    @classmethod
    def from_firestore_dict(cls, data: Dict) -> 'PodcastEpisode':
        """
        Create PodcastEpisode from Firestore document.
        
        Args:
            data: Dictionary from Firestore document
            
        Returns:
            PodcastEpisode instance
        """
        # Parse datetime if it's a string
        created_time = data.get('created_time')
        if isinstance(created_time, str):
            created_time = datetime.fromisoformat(created_time)
        elif not isinstance(created_time, datetime):
            created_time = datetime.now()
        
        return cls(
            mp3_url=data.get('mp3_url', ''),
            transcript_url=data.get('transcript_url', ''),
            summary_url=data.get('summary_url', ''),
            summary_image_url=data.get('summary_image_url', ''),
            mp3_public_url=data.get('mp3_public_url'),
            transcript_public_url=data.get('transcript_public_url'),
            summary_public_url=data.get('summary_public_url'),
            summary_image_public_url=data.get('summary_image_public_url'),
            events_markdown_url=data.get('events_markdown_url'),
            events_markdown_public_url=data.get('events_markdown_public_url'),
            sentences_markdown_url=data.get('sentences_markdown_url'),
            sentences_markdown_public_url=data.get('sentences_markdown_public_url'),
            pptx_url=data.get('pptx_url'),
            pptx_public_url=data.get('pptx_public_url'),
            marp_markdown_url=data.get('marp_markdown_url'),
            marp_markdown_public_url=data.get('marp_markdown_public_url'),
            ticker_insights_url=data.get('ticker_insights_url') or data.get('ticker_recommendations_url'),
            ticker_insights_public_url=data.get('ticker_insights_public_url') or data.get('ticker_recommendations_public_url'),
            ticker_marp_markdown_url=data.get('ticker_marp_markdown_url'),
            ticker_marp_markdown_public_url=data.get('ticker_marp_markdown_public_url'),
            related_tickers=data.get('related_tickers', []),
            key_insights=data.get('key_insights', []),
            social_cards=data.get('social_cards', []),
            sector_exposures=data.get('sector_exposures', []),
            unresolved_market_trends=data.get('unresolved_market_trends', []),
            sector_exposure_ids=data.get('sector_exposure_ids', []),
            sector_ids=data.get('sector_ids', []),
            theme_ids=data.get('theme_ids', []),
            unresolved_market_trend_ids=data.get('unresolved_market_trend_ids', []),
            created_time=created_time,
            number_click=data.get('number_click', 0),
            num_likes=data.get('num_likes', 0),
            episode_title=data.get('episode_title'),
            podcast_name=data.get('podcast_name'),
            episode_number=data.get('episode_number'),
            spotify_embed_url=data.get('spotify_embed_url'),
            spotify_id=data.get('spotify_id'),
            spotify_url=data.get('spotify_url'),
            spotify_release_date=data.get('spotify_release_date'),
            spotify_description=data.get('spotify_description'),
            spotify_duration_ms=data.get('spotify_duration_ms'),
            spotify_images=data.get('spotify_images', []),
            released_at_ms=data.get('released_at_ms'),
            retracted_at=data.get('retracted_at'),
        )


class PodcastCollection:
    """
    Represents the Firestore structure: {'name1': List[PodcastEpisode], 'name2': List[PodcastEpisode], ...}
    Note: The 'podcast' wrapper has been removed to avoid duplication in the path podcasts/podcast.
    """
    
    def __init__(self):
        """Initialize an empty podcast collection."""
        self.podcasts: Dict[str, List[PodcastEpisode]] = {}
    
    def add_episode(self, podcast_name: str, episode: PodcastEpisode) -> None:
        """
        Add episode to a podcast's list.
        
        Args:
            podcast_name: Name of the podcast
            episode: PodcastEpisode to add
        """
        if podcast_name not in self.podcasts:
            self.podcasts[podcast_name] = []
        
        # Set podcast_name if not already set
        if not episode.podcast_name:
            episode.podcast_name = podcast_name
        
        self.podcasts[podcast_name].append(episode)
    
    def get_episodes(self, podcast_name: str) -> List[PodcastEpisode]:
        """
        Get all episodes for a podcast.
        
        Args:
            podcast_name: Name of the podcast
            
        Returns:
            List of PodcastEpisode objects
        """
        return self.podcasts.get(podcast_name, [])
    
    def to_firestore_dict(self) -> Dict:
        """
        Convert to Firestore document format.
        
        Returns:
            Dictionary with structure: {'name1': [episode_dicts], 'name2': [episode_dicts], ...}
            Note: Removed 'podcast' wrapper to avoid duplication in path podcasts/podcast.
        """
        result = {}
        
        for podcast_name, episodes in self.podcasts.items():
            result[podcast_name] = [
                episode.to_firestore_dict() for episode in episodes
            ]
        
        return result
    
    @classmethod
    def from_firestore_dict(cls, data: Dict) -> 'PodcastCollection':
        """
        Create from Firestore document.
        
        Args:
            data: Dictionary from Firestore with structure {podcast_name: [episodes], ...}
            Also supports legacy format {'podcast': {podcast_name: [episodes], ...}} for backward compatibility.
            
        Returns:
            PodcastCollection instance
        """
        collection = cls()
        
        # Support both new format (direct) and legacy format (with 'podcast' wrapper)
        if 'podcast' in data and isinstance(data['podcast'], dict):
            # Legacy format: {'podcast': {podcast_name: [episodes], ...}}
            podcast_data = data['podcast']
        else:
            # New format: {podcast_name: [episodes], ...}
            podcast_data = data
        
        for podcast_name, episodes_list in podcast_data.items():
            if isinstance(episodes_list, list):
                for episode_dict in episodes_list:
                    episode = PodcastEpisode.from_firestore_dict(episode_dict)
                    collection.add_episode(podcast_name, episode)
        
        return collection
