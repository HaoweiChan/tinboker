"""
Pipeline configuration.

This module defines the PipelineConfig dataclass for configuring the podcast processing pipeline.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class PipelineConfig:
    """Configuration for the podcast processing pipeline."""
    
    # Input
    config_file: Path
    podcast_name: str
    podcast_link: str
    spotify_show_link: Optional[str] = None
    episode_limit: int = 2
    
    # Services
    stt_service_name: str = "whisper"  # "whisper", "openai", or "groq"
    stt_model: Optional[str] = None  # Model name for STT service (e.g., "whisper-large-v3", "whisper-large-v3-turbo" for Groq)
    
    # Rerun flags (more intuitive than "skip")
    # If set, the pipeline will rerun from that step (and download required inputs)
    rerun_from: Optional[str] = None  # "download", "transcribe", "summarize", "upload", "validate", "spotify-metadata", or None (full pipeline)
    
    # DEPRECATED: Legacy flag for backward compatibility only
    # Use rerun_from="summarize" instead to download transcript and regenerate summary
    reuse_existing_transcript: bool = False
    
    # Mode
    use_file_mode: bool = False  # If True, use file-based mode
    fill_limit: bool = False  # If True, skip processed episodes and process exactly limit non-processed ones
    
    # File paths (for file mode)
    downloads_dir: Path = Path("./data/downloads")
    transcripts_dir: Path = Path("./data/transcripts")
    summaries_dir: Path = Path("./data/summary_content")
    images_dir: Path = Path("./data/images")
    
    # Temp directory (for streaming mode)
    temp_dir: Optional[Path] = None



