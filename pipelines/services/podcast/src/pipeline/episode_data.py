"""
Episode Data

This module defines the EpisodeData dataclass for episode-specific data.
A fresh instance is created for each episode, eliminating the need for clearing.
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from src.models.podcast_models import PodcastEpisode, Sentence


@dataclass
class EpisodeData:
    """Episode-specific data that's isolated per episode.
    
    A fresh instance is created for each episode, so there's no cross-episode
    contamination and no need for manual clearing.
    """
    
    # From API (immutable after creation)
    api_data: Dict  # Contains: title, episodeNumber, episodeUrl, etc.
    podcast_name: str
    language: str  # "en" or "zh"
    
    # Processing state (updated as pipeline progresses)
    episode_id: Optional[str] = None
    mp3_path: Optional[Path] = None
    transcript_text: Optional[str] = None
    transcript_words: Optional[List[Dict]] = None
    transcript_sentences: Optional[List[Sentence]] = None
    summary_result: Optional[Dict] = None
    spotify_metadata: Optional[Dict] = None
    gcs_urls: Optional[Dict] = None
    episode: Optional[PodcastEpisode] = None
    
    # Metadata
    created_time: Optional[datetime] = None
    
    # Tags and tickers (extracted from summary)
    tags: List[str] = field(default_factory=list)
    tickers: List[str] = field(default_factory=list)
    
    # Validation results (updated during Step 6: Validate)
    validation_results: Dict[str, bool] = field(default_factory=dict)
    # Keys: "mp3_exists", "transcript_exists", "summary_exists", 
    #       "gcs_urls_valid", "firestore_document_exists", "gcs_files_accessible"

