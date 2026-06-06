# Source Code Organization

This directory contains the core source code for the podcast processing pipeline.

## Architecture Overview

### Pipeline Architecture (`pipeline/`)
The refactored step-based pipeline architecture:
- **`pipeline/steps/`** - Individual pipeline step functions (download, transcribe, summarize, upload, validate)
- **`pipeline/config.py`** - Pipeline configuration dataclass
- **`pipeline/context.py`** - Shared pipeline context
- **`pipeline/processor.py`** - Main episode processor orchestrator
- **`pipeline/utils.py`** - Pipeline utility functions

### Services (`service/`)
Service classes and utilities used by the pipeline steps:

- **`service/gcs_storage_service.py`** - `GCSStorageService` class for episode-specific GCS uploads
  - Used by: `pipeline/steps/gcs_upload.py`
  - Purpose: Upload episode files (MP3, transcript, summary, SVG) with structured paths

- **`service/upload_to_firebase.py`** - `FirebaseService` class for Firestore operations
  - Used by: `pipeline/steps/firestore.py`, `pipeline/steps/validate.py`
  - Purpose: Upload episode metadata to Firestore, query existing episodes

- **`service/speech_to_text.py`** - STT service class (`WhisperService`)
  - Used by: `pipeline/steps/transcribe.py`
  - Purpose: Transcribe audio files to text

- **`service/download_podcasts.py`** - Download utility functions
  - Used by: `pipeline/steps/download.py`, `main.py`
  - Purpose: Fetch episodes from API, download MP3 files

## File Purpose Summary

| File | Type | Used By | Purpose |
|------|------|---------|---------|
| `pipeline/steps/*.py` | Pipeline steps | `processor.py` | Step functions for pipeline execution |
| `service/gcs_storage_service.py` | Service class | Pipeline steps | Episode-specific GCS uploads |
| `service/upload_to_firebase.py` | Service class | Pipeline steps | Firestore operations |
| `service/speech_to_text.py` | Service classes | Pipeline steps | Speech-to-text transcription |
| `service/download_podcasts.py` | Utility functions | Pipeline steps, main.py | Download episodes and MP3s |

