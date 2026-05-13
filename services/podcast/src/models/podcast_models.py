"""
Podcast data models for Firestore integration.
"""

from dataclasses import dataclass, field
from datetime import datetime
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
    ticker_recommendations_url: Optional[str] = None  # GCS URL for ticker recommendations JSON file (gs://...)
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
    ticker_recommendations_public_url: Optional[str] = None  # Public HTTPS URL for ticker recommendations
    ticker_marp_markdown_public_url: Optional[str] = None  # Public HTTPS URL for ticker marp markdown
    
    # Metadata
    related_tickers: List[str] = field(default_factory=list)  # List of ticker symbols
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
        }
        
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
        if self.ticker_recommendations_url:
            result['ticker_recommendations_url'] = self.ticker_recommendations_url
        if self.ticker_recommendations_public_url:
            result['ticker_recommendations_public_url'] = self.ticker_recommendations_public_url
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
        if self.spotify_release_date:
            result['spotify_release_date'] = self.spotify_release_date
        if self.spotify_description:
            result['spotify_description'] = self.spotify_description
        if self.spotify_duration_ms:
            result['spotify_duration_ms'] = self.spotify_duration_ms
        if self.spotify_images:
            result['spotify_images'] = self.spotify_images
        
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
            ticker_recommendations_url=data.get('ticker_recommendations_url'),
            ticker_recommendations_public_url=data.get('ticker_recommendations_public_url'),
            ticker_marp_markdown_url=data.get('ticker_marp_markdown_url'),
            ticker_marp_markdown_public_url=data.get('ticker_marp_markdown_public_url'),
            related_tickers=data.get('related_tickers', []),
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

