"""
Service modules for the podcast processing pipeline.

This package contains service classes and utilities used by the pipeline:
- download_podcasts: Download utilities for fetching episodes and MP3s
- gcs_storage_service: GCS storage service for episode file uploads
- speech_to_text: STT service implementation (Whisper/OpenAI)
- upload_to_firebase: Firebase/Firestore service for episode metadata
- sentence_generator: Service for generating sentences from word-level transcripts
"""

from .sentence_generator import SentenceGenerator

__all__ = [
    'SentenceGenerator',
]


