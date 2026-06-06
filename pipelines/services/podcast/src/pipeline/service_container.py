"""
Service Container

This module defines the ServiceContainer dataclass for holding all reusable services.
Services are initialized once and shared across all episodes.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class ServiceContainer:
    """Container for reusable services shared across episodes."""
    
    # Services (initialized once, reused for all episodes)
    firebase_service: Optional[object] = None  # FirebaseService
    stt_service: Optional[object] = None  # SpeechToTextService
    gcs_service: Optional[object] = None  # GCSStorageService
    summarize_service: Optional[object] = None  # SummarizeService

