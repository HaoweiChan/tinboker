"""
Podcast-related Pydantic models
"""
from pydantic import BaseModel, Field
from typing import Optional, List


class Episode(BaseModel):
    """Podcast episode model"""
    id: str = Field(..., description="Unique episode identifier")
    podcast_name: str = Field(..., description="Podcast name")
    episode_title: Optional[str] = Field(None, description="Episode title")
    episode_number: Optional[int] = Field(None, description="Episode number")
    transcript: Optional[str] = Field(None, description="Episode transcript")
    summary_content: Optional[str] = Field(None, description="Summary markdown content")
    summary_image: Optional[str] = Field(None, description="Summary SVG image")
    related_tickers: List[str] = Field(default_factory=list, description="Related stock tickers")
    tags: List[str] = Field(default_factory=list, description="Topic tags")
    created_time: int = Field(..., description="Creation/ingestion timestamp (Unix milliseconds)")
    released_at_ms: Optional[int] = Field(None, description="True episode publish time (Unix milliseconds), agents-written from the feed's datePublished. Falls back to created_time when absent.")
    number_click: int = Field(default=0, description="Number of clicks")
    num_likes: int = Field(default=0, description="Number of likes")
    key_insights: List[str] = Field(default_factory=list, description="Key insights for the episode")
    raw_mp3: Optional[str] = Field(None, description="Raw MP3 file path (local, not in Firebase)")
    
    # GCS URLs for episode files
    mp3_url: Optional[str] = Field(None, description="GCS URL for MP3 file (gs://...)")
    transcript_url: Optional[str] = Field(None, description="GCS URL for transcript file (gs://...)")
    summary_url: Optional[str] = Field(None, description="GCS URL for summary markdown file (gs://...)")
    summary_image_url: Optional[str] = Field(None, description="GCS URL for SVG image file (gs://...)")
    events_markdown_url: Optional[str] = Field(None, description="GCS URL for events markdown file (gs://...)")
    sentences_markdown_url: Optional[str] = Field(None, description="GCS URL for sentences markdown file (gs://...)")
    marp_markdown_url: Optional[str] = Field(None, description="GCS URL for Marp markdown file (gs://...)")
    
    # Optional public HTTPS URLs
    mp3_public_url: Optional[str] = Field(None, description="Public HTTPS URL for MP3")
    transcript_public_url: Optional[str] = Field(None, description="Public HTTPS URL for transcript")
    summary_public_url: Optional[str] = Field(None, description="Public HTTPS URL for summary")
    summary_image_public_url: Optional[str] = Field(None, description="Public HTTPS URL for SVG image")
    events_markdown_public_url: Optional[str] = Field(None, description="Public HTTPS URL for events markdown")
    sentences_markdown_public_url: Optional[str] = Field(None, description="Public HTTPS URL for sentences markdown")
    marp_markdown_public_url: Optional[str] = Field(None, description="Public HTTPS URL for Marp markdown")
    
    # Additional markdown content fields
    events_markdown_content: Optional[str] = Field(None, description="Events markdown content")
    sentences_markdown_content: Optional[str] = Field(None, description="Sentences markdown content")
    marp_markdown_content: Optional[str] = Field(None, description="Marp markdown content")
    
    # Ticker-specific fields
    ticker_marp_markdown_url: Optional[str] = Field(None, description="GCS URL for ticker-specific Marp markdown file (gs://...)")
    ticker_marp_markdown_public_url: Optional[str] = Field(None, description="Public HTTPS URL for ticker-specific Marp markdown")
    ticker_marp_markdown_content: Optional[str] = Field(None, description="Ticker-specific Marp markdown content")
    ticker_recommendations_public_url: Optional[str] = Field(None, description="Public HTTPS URL for ticker recommendations JSON")
    ticker_recommendations_content: Optional[str] = Field(None, description="Ticker recommendations JSON content (cached)")
    
    # Spotify metadata (optional)
    spotify_embed_url: Optional[str] = Field(None, description="Spotify embed URL")
    spotify_id: Optional[str] = Field(None, description="Spotify episode ID")
    spotify_url: Optional[str] = Field(None, description="Spotify episode URL")
    spotify_release_date: Optional[str] = Field(None, description="Release date from Spotify (YYYY-MM-DD)")
    spotify_description: Optional[str] = Field(None, description="Episode description from Spotify")
    spotify_duration_ms: Optional[int] = Field(None, description="Episode duration in milliseconds")
    spotify_images: List[str] = Field(default_factory=list, description="List of image URLs from Spotify")
    
    # Modified summary fields (stored in Firestore)
    modified_summary_url: Optional[str] = Field(None, description="GCS URL for modified summary markdown file (gs://...)")
    modified_summary_content: Optional[str] = Field(None, description="Modified summary markdown content")
    modified_by: Optional[str] = Field(None, description="User who modified the summary (email or ID)")
    modified_at: Optional[int] = Field(None, description="Timestamp when summary was modified (Unix milliseconds)")

    class Config:
        populate_by_name = True


class Podcast(BaseModel):
    """Podcast metadata model (aggregated from episodes)"""
    id: str = Field(..., description="Podcast identifier (podcast_name)")
    name: str = Field(..., description="Podcast name")
    episode_count: int = Field(default=0, description="Total number of episodes")
    created_at: Optional[int] = Field(None, description="First episode creation timestamp (Unix milliseconds)")
    updated_at: Optional[int] = Field(None, description="Most recent episode timestamp (Unix milliseconds)")
    image_url: Optional[str] = Field(None, description="Podcast cover image URL (from most recent episode)")

    class Config:
        populate_by_name = True

