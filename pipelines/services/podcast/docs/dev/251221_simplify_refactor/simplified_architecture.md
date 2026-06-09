# Simplified Architecture Design

## Overview

The refactored architecture uses a **step-based pipeline pattern** where each processing step is independent, testable, and can be skipped or reused as needed. This eliminates the complexity of having separate modes and duplicate logic.

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    Main Pipeline Function                    │
│                  (run_pipeline)                             │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│              Step 0: Initialize Services                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │   Firebase   │  │     STT      │  │     GCS      │      │
│  │   Service    │  │   Service    │  │   Service    │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└─────────────────────────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│              Load Config & Fetch Episodes                     │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
         ┌─────────────────────────────┐
         │   For Each Episode          │
         └─────────────┬───────────────┘
                       │
        ┌──────────────┼──────────────┐
        │              │               │
        ▼              ▼               ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│   Step 1:    │ │   Step 2:    │ │   Step 3:    │
│   Download   │ │  Transcribe  │ │  Summarize   │
└──────┬───────┘ └──────┬───────┘ └──────┬───────┘
       │                │                 │
       └────────────────┼─────────────────┘
                        │
                        ▼
              ┌──────────────────┐
              │   Step 4:        │
              │   Spotify        │
              │   Metadata       │
              └────────┬─────────┘
                       │
        ┌──────────────┼──────────────┐
        │              │               │
        ▼              ▼               ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│   Step 4:    │ │   Step 5:    │ │   Step 6:    │
│   Upload     │ │   Upload     │ │   Validate   │
│   to GCS     │ │   to          │ │              │
│              │ │   Firestore   │ │              │
└──────────────┘ └──────────────┘ └──────────────┘
```

## Data Flow

```
Episode Data (from API)
    │
    └─> Step 1: Download MP3 + Fetch Spotify Metadata
            ├─> MP3 File Path
            └─> Spotify Metadata (including created_time)
                    │
                    ├─> Step 2: Transcribe → Transcript Text
                    │       │
                    │       └─> Step 3: Summarize → Summary + SVG
                    │               │
                    │               └─> Step 4: Upload to GCS → GCS URLs
                    │                       │
                    │                       └─> Step 5: Upload to Firestore → Episode Document
                    │                               (merges Spotify metadata)
                    │
                    └─> Step 4: Upload to GCS (uses created_time for episode ID)
```

## Overview

The refactored architecture uses a **step-based pipeline pattern** where each processing step is independent, testable, and can be skipped or reused as needed. This eliminates the complexity of having separate modes and duplicate logic.

## Architecture Principles

1. **Single Responsibility**: Each step/function has one clear purpose
2. **Dependency Injection**: Services are injected, not created inside functions
3. **Fail Fast**: Early validation and clear error messages
4. **Idempotency**: Steps can be safely retried
5. **Testability**: Each component can be tested in isolation

## Component Structure

```
main.py (orchestrator)
├── PipelineConfig (configuration)
├── PipelineContext (shared state)
├── EpisodeProcessor (main coordinator)
└── Processing Steps (independent functions)
    ├── Step 0: Service Initialization
    ├── Step 1: Download MP3 + Fetch Spotify Metadata
    ├── Step 2: Transcribe
    ├── Step 3: Summarize
    ├── Step 4: Upload to GCS
    ├── Step 5: Upload to Firestore
    └── Step 6: Validate
```

## Core Components

### 1. PipelineConfig

**Purpose**: Centralized configuration for the entire pipeline

```python
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
    stt_service_name: str = "assemblyai"  # "deepgram" or "assemblyai"
    
    # Rerun flags (more intuitive than "skip")
    # If set, the pipeline will rerun from that step (and download required inputs)
    rerun_from: Optional[str] = None  # "transcribe", "summarize", "upload", or None (full pipeline)
    
    # Legacy: reuse existing transcript (for backward compatibility)
    reuse_existing_transcript: bool = False  # If True, reuse transcript from GCS for existing episodes
    
    # Mode
    use_file_mode: bool = False  # If True, use file-based mode
    
    # File paths (for file mode)
    downloads_dir: Path = Path("./data/downloads")
    transcripts_dir: Path = Path("./data/transcripts")
    summaries_dir: Path = Path("./data/summary_content")
    images_dir: Path = Path("./data/images")
    
    # Temp directory (for streaming mode)
    temp_dir: Optional[Path] = None
```

### 2. PipelineContext

**Purpose**: Shared state and services across all steps

```python
@dataclass
class PipelineContext:
    """Shared context for pipeline execution."""
    
    # Services (initialized once, reused)
    firebase_service: Optional[FirebaseService] = None
    stt_service: Optional[SpeechToTextService] = None
    gcs_service: Optional[GCSStorageService] = None
    summarize_service: Optional[SummarizeService] = None
    
    # Episode state (updated as pipeline progresses)
    episode_data: Optional[Dict] = None
    episode_id: Optional[str] = None
    mp3_path: Optional[Path] = None
    transcript_text: Optional[str] = None
    summary_result: Optional[Dict] = None
    spotify_metadata: Optional[Dict] = None
    gcs_urls: Optional[Dict] = None
    episode: Optional[PodcastEpisode] = None
    
    # Metadata
    podcast_name: str = ""
    language: str = "en"  # "en" or "zh"
    created_time: Optional[datetime] = None
    
    # Validation results (updated during Step 6: Validate)
    validation_results: Dict[str, bool] = field(default_factory=dict)
    # Keys: "mp3_exists", "transcript_exists", "summary_exists", 
    #       "gcs_urls_valid", "firestore_document_exists", "gcs_files_accessible"
```

### 3. Processing Steps

Each step is a pure function that:
- Takes `config`, `context`, and step-specific inputs
- Returns step-specific outputs
- Can check if it needs to run (idempotency)
- Handles its own errors

#### Step 0: Initialize Services

```python
def initialize_services(config: PipelineConfig) -> PipelineContext:
    """
    Initialize all required services based on config.
    
    Returns:
        PipelineContext with initialized services
    """
    context = PipelineContext()
    
    # Initialize Firebase (if upload enabled)
    if not config.skip_upload:
        context.firebase_service = FirebaseService()
    
    # Initialize STT (if transcribe enabled)
    if not config.skip_transcribe:
        if config.stt_service_name == "deepgram":
            context.stt_service = DeepgramService()
        else:
            context.stt_service = AssemblyAIService()
    
    # Initialize GCS (if upload enabled)
    if not config.skip_upload:
        context.gcs_service = GCSStorageService()
    
    # Initialize Summarize (always available)
    context.summarize_service = SummarizeService()
    
    return context
```

#### Step 1: Download MP3 + Fetch Spotify Metadata

```python
def download_episode(
    config: PipelineConfig,
    context: PipelineContext,
    episode_data: Dict
) -> Optional[Path]:
    """
    Download episode MP3 file and fetch Spotify metadata.
    
    Both operations are independent and can be done in parallel.
    Spotify metadata is fetched here because:
    1. We have episode_title from the start (no dependencies)
    2. created_time from Spotify is needed for Step 4 (episode ID generation)
    3. Both are "data gathering" operations
    
    Args:
        config: Pipeline configuration
        context: Pipeline context
        episode_data: Episode data from API
        
    Returns:
        Path to downloaded MP3 file, or None if skipped/failed
    """
    # Part 1: Download MP3
    # Always download if rerun_from is "transcribe" or earlier, or if mp3_path doesn't exist
    should_download = (
        config.rerun_from in [None, "transcribe"] or
        not context.mp3_path or
        not context.mp3_path.exists()
    )
    
    if should_download:
        # Check if already downloaded (idempotency)
        if context.mp3_path and context.mp3_path.exists():
            mp3_path = context.mp3_path
        else:
            # Get download URL
            episode_url = episode_data.get('episodeUrl')
            if not episode_url:
                raise ValueError("No download URL in episode data")
            
            # Download based on mode
            if config.use_file_mode:
                # File mode: download to persistent directory
                mp3_path = download_to_file(
                    episode_url,
                    episode_data.get('title', 'episode'),
                    config.downloads_dir / context.podcast_name
                )
            else:
                # Streaming mode: download to temp file
                mp3_path = download_file_to_temp(
                    episode_url,
                    episode_data.get('title', 'episode'),
                    config.temp_dir
                )
            
            context.mp3_path = mp3_path
    else:
        mp3_path = context.mp3_path
    
    # Part 2: Fetch Spotify metadata (independent of download)
    if config.spotify_show_link and not context.spotify_metadata:
        try:
            from src.spotify_podcast.metadata_helper import get_spotify_metadata
            metadata = get_spotify_metadata(
                config.spotify_show_link,
                episode_data.get('title')
            )
            context.spotify_metadata = metadata
            
            # Use Spotify release_date as created_time if available
            # (needed for Step 4: episode ID generation)
            if metadata and metadata.get('release_datetime'):
                context.created_time = metadata['release_datetime']
        except Exception as e:
            print(f"  ⚠ Warning: Error fetching Spotify metadata: {e}")
            # Continue without metadata - it's optional
    
    return mp3_path
```

#### Step 2: Transcribe Episode

```python
def transcribe_episode(
    config: PipelineConfig,
    context: PipelineContext,
    episode_data: Dict
) -> Optional[str]:
    """
    Transcribe episode audio to text.
    
    Args:
        config: Pipeline configuration
        context: Pipeline context
        episode_data: Episode data from API
        
    Returns:
        Transcript text, or None if skipped/failed
    """
    # Determine if we should transcribe
    # Skip if rerun_from is "summarize" or later (we'll download transcript instead)
    should_transcribe = (
        config.rerun_from in [None, "transcribe"] or
        not context.transcript_text
    )
    
    if not should_transcribe:
        # For rerun_from="summarize", download transcript from GCS
        if config.rerun_from == "summarize" and context.firebase_service:
            # Download transcript from existing episode
            existing = context.firebase_service.get_episode_by_fields(
                podcast_name=context.podcast_name,
                episode_title=episode_data.get('title'),
                episode_number=episode_data.get('episodeNumber')
            )
            if existing and existing.get('transcript_url'):
                transcript_text = context.gcs_service.download_text_by_gcs_url(
                    existing['transcript_url']
                )
                context.transcript_text = transcript_text
                return transcript_text
        return None
    
    # Check if transcript already exists (idempotency)
    if context.transcript_text:
        return context.transcript_text
    
    # Check if we can reuse existing transcript (legacy support)
    if config.reuse_existing_transcript and context.firebase_service:
        existing = context.firebase_service.get_episode_by_fields(
            podcast_name=context.podcast_name,
            episode_title=episode_data.get('title'),
            episode_number=episode_data.get('episodeNumber')
        )
        if existing and existing.get('transcript_url'):
            # Download transcript from GCS
            transcript_text = context.gcs_service.download_text_by_gcs_url(
                existing['transcript_url']
            )
            context.transcript_text = transcript_text
            return transcript_text
    
    # Need to transcribe
    if not context.mp3_path:
        raise ValueError("MP3 file not available for transcription")
    
    if not context.stt_service:
        raise ValueError("STT service not initialized")
    
    # Transcribe
    if config.use_file_mode:
        # File mode: save to file
        transcript_path = transcribe_audio_file(
            str(context.mp3_path),
            output_base_dir=str(config.transcripts_dir),
            service=context.stt_service,
            language=context.language
        )
        context.transcript_text = Path(transcript_path).read_text()
    else:
        # Streaming mode: return text directly
        context.transcript_text = transcribe_audio_file(
            str(context.mp3_path),
            service=context.stt_service,
            language=context.language,
            return_text_only=True
        )
    
    return context.transcript_text
```

#### Step 3: Generate Summary

```python
def generate_summary(
    config: PipelineConfig,
    context: PipelineContext,
    episode_data: Dict
) -> Optional[Dict]:
    """
    Generate summary, SVG, and tickers from transcript.
    
    Args:
        config: Pipeline configuration
        context: Pipeline context
        episode_data: Episode data from API
        
    Returns:
        Summary result dict with 'summary_text', 'svg_content', 'related_tickers'
    """
    # Determine if we should summarize
    # Skip if rerun_from is "upload" or later
    should_summarize = (
        config.rerun_from in [None, "transcribe", "summarize"] or
        not context.summary_result
    )
    
    if not should_summarize:
        return None
    
    # Check if summary already exists (idempotency)
    if context.summary_result:
        return context.summary_result
    
    # Need transcript
    if not context.transcript_text:
        raise ValueError("Transcript not available for summarization")
    
    # Generate summary
    summary_result = context.summarize_service.generate_summary_from_text(
        context.transcript_text,
        podcast_name=context.podcast_name,
        episode_title=episode_data.get('title')
    )
    
    context.summary_result = summary_result
    return summary_result
```

#### Step 4: Upload to GCS

```python
def upload_to_gcs(
    config: PipelineConfig,
    context: PipelineContext,
    episode_data: Dict
) -> Optional[Dict]:
    """
    Upload episode files to Google Cloud Storage.
    
    Args:
        config: Pipeline configuration
        context: Pipeline context
        episode_data: Episode data from API
        
    Returns:
        Dict with GCS URLs, or None if skipped/failed
    """
    # Determine if we should upload
    # Skip if rerun_from is "validate" or if upload is explicitly disabled
    should_upload = (
        config.rerun_from in [None, "transcribe", "summarize", "upload"] or
        config.rerun_from is None
    )
    
    if not should_upload:
        return None
    
    # Check if already uploaded (idempotency)
    if context.gcs_urls:
        return context.gcs_urls
    
    # Need GCS service
    if not context.gcs_service:
        raise ValueError("GCS service not initialized")
    
    # Need episode ID
    if not context.episode_id:
        # Generate episode ID
        context.episode_id = generate_episode_id(
            context.firebase_service,
            context.podcast_name,
            episode_data,
            context.summary_result
        )
    
    # Upload files
    gcs_urls = context.gcs_service.upload_episode_files(
        episode_id=context.episode_id,
        podcast_name=context.podcast_name,
        mp3_path=context.mp3_path,
        transcript_content=context.transcript_text,
        summary_content=context.summary_result.get('summary_text') if context.summary_result else None,
        svg_content=context.summary_result.get('svg_content') if context.summary_result else None,
        skip_existing=True
    )
    
    context.gcs_urls = gcs_urls
    return gcs_urls
```

#### Step 5: Upload to Firestore

```python
def upload_to_firestore(
    config: PipelineConfig,
    context: PipelineContext,
    episode_data: Dict
) -> bool:
    """
    Upload episode data to Firestore.
    
    Args:
        config: Pipeline configuration
        context: Pipeline context
        episode_data: Episode data from API
        
    Returns:
        True if successful, False otherwise
    """
    # Determine if we should upload to Firestore
    # Skip if rerun_from is "validate"
    should_upload = (
        config.rerun_from in [None, "transcribe", "summarize", "upload"] or
        config.rerun_from is None
    )
    
    if not should_upload:
        return False
    
    # Need Firebase service
    if not context.firebase_service:
        raise ValueError("Firebase service not initialized")
    
    # Create PodcastEpisode object
    episode = create_episode_object(
        context=context,
        episode_data=episode_data,
        gcs_urls=context.gcs_urls,
        spotify_metadata=context.spotify_metadata,
        summary_result=context.summary_result
    )
    
    # Upload to Firestore
    context.firebase_service.upload_podcast_data(
        podcast_name=context.podcast_name,
        episode=episode,
        gcs_service=None  # Already uploaded above
    )
    
    context.episode = episode
    return True
```

#### Step 6: Validate

```python
def validate_episode(
    config: PipelineConfig,
    context: PipelineContext,
    episode_data: Dict
) -> bool:
    """
    Validate that episode was processed correctly.
    
    Args:
        config: Pipeline configuration
        context: Pipeline context
        episode_data: Episode data from API
        
    Returns:
        True if validation passes, False otherwise
    """
    # Optional step - can be skipped
    if config.skip_upload:
        return True  # Nothing to validate
    
    # Validate GCS URLs exist
    if context.gcs_urls:
        # Check that files are accessible
        # (Implementation depends on GCS service capabilities)
        pass
    
    # Validate Firestore document exists
    if context.firebase_service and context.episode_id:
        exists = context.firebase_service.episode_exists(
            context.podcast_name,
            episode_data.get('title'),
            episode_data.get('episodeNumber')
        )
        if not exists:
            print(f"  ⚠ Warning: Episode not found in Firestore after upload")
            return False
    
    return True
```

### 4. EpisodeProcessor

**Purpose**: Main coordinator that orchestrates all steps

```python
class EpisodeProcessor:
    """Main processor for podcast episodes."""
    
    def __init__(self, config: PipelineConfig, context: PipelineContext):
        self.config = config
        self.context = context
    
    def process_episode(self, episode_data: Dict) -> bool:
        """
        Process a single episode through all steps.
        
        Args:
            episode_data: Episode data from API
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Set episode data in context
            self.context.episode_data = episode_data
            self.context.podcast_name = self.config.podcast_name
            self.context.language = determine_language(self.config.podcast_name)
            
            # Check if episode already exists (deduplication)
            if self._should_skip_episode(episode_data):
                return True  # Skip is successful
            
            # Execute steps in order
            # Step 1: Download MP3 + Fetch Spotify Metadata
            download_episode(self.config, self.context, episode_data)
            
            # Step 2: Transcribe
            transcribe_episode(self.config, self.context, episode_data)
            
            # Step 3: Summarize
            generate_summary(self.config, self.context, episode_data)
            
            # Step 4: Upload to GCS
            upload_to_gcs(self.config, self.context, episode_data)
            
            # Step 5: Upload to Firestore
            upload_to_firestore(self.config, self.context, episode_data)
            
            # Step 6: Validate
            validate_episode(self.config, self.context, episode_data)
            
            return True
            
        except Exception as e:
            print(f"  ✗ Error processing episode: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _should_skip_episode(self, episode_data: Dict) -> bool:
        """Check if episode should be skipped (already exists)."""
        if not self.context.firebase_service:
            return False
        
        # Check if episode exists
        exists = self.context.firebase_service.episode_exists(
            self.config.podcast_name,
            episode_data.get('title'),
            episode_data.get('episodeNumber')
        )
        
        if exists:
            # If reuse_transcript, we still want to process (regenerate summary)
            if self.config.reuse_existing_transcript:
                return False
            return True
        
        return False
```

### 5. Main Pipeline Function

**Purpose**: High-level orchestration

```python
def run_pipeline(config: PipelineConfig) -> None:
    """
    Run the podcast processing pipeline.
    
    Args:
        config: Pipeline configuration
    """
    # Step 0: Initialize services
    context = initialize_services(config)
    
    # Load podcast configs
    podcasts = load_podcasts_config(config.config_file)
    
    # Process each podcast
    for podcast_config in podcasts:
        # Create config for this podcast
        podcast_config_obj = PipelineConfig(
            **config.__dict__,
            podcast_name=podcast_config.get('name'),
            podcast_link=podcast_config.get('link'),
            spotify_show_link=podcast_config.get('spotify_show_link'),
            episode_limit=podcast_config.get('limit', 2)
        )
        
        # Create processor
        processor = EpisodeProcessor(podcast_config_obj, context)
        
        # Fetch episodes
        podcast_id = extract_podcast_id(podcast_config_obj.podcast_link)
        episodes = fetch_episodes(podcast_id)
        
        # Apply limit
        if podcast_config_obj.episode_limit:
            episodes = episodes[:podcast_config_obj.episode_limit]
        
        # Process each episode
        for episode_data in episodes:
            processor.process_episode(episode_data)
```

## Benefits of This Architecture

1. **Unified Mode**: File-based mode is just a config flag, not separate code
2. **Consistent Skip Logic**: Skip flags work the same way everywhere
3. **Testable Steps**: Each step can be tested independently
4. **Clear Dependencies**: Services are injected, not created inside functions
5. **Idempotent**: Steps check if work is already done
6. **Easy to Extend**: Add new steps by creating new functions
7. **Better Error Handling**: Each step handles its own errors

## Migration Strategy

1. **Phase 1**: Create new step functions alongside existing code
2. **Phase 2**: Create EpisodeProcessor and test with one episode
3. **Phase 3**: Migrate streaming mode to use new architecture
4. **Phase 4**: Migrate file-based mode to use new architecture
5. **Phase 5**: Remove old code

## Helper Functions

### Utility Functions

```python
def determine_language(podcast_name: str) -> str:
    """Determine language code based on podcast name."""
    chinese_indicators = ['股癌', '財經', '財女', '珍妮']
    for indicator in chinese_indicators:
        if indicator in podcast_name:
            return "zh"
    return "en"

def generate_episode_id(
    firebase_service: FirebaseService,
    podcast_name: str,
    episode_data: Dict,
    summary_result: Optional[Dict] = None
) -> str:
    """Generate stable episode ID."""
    from src.models.podcast_models import PodcastEpisode
    from datetime import datetime
    
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

def create_episode_object(
    context: PipelineContext,
    episode_data: Dict,
    gcs_urls: Dict,
    spotify_metadata: Optional[Dict],
    summary_result: Optional[Dict]
) -> PodcastEpisode:
    """Create PodcastEpisode object from processed data."""
    from src.models.podcast_models import PodcastEpisode
    from datetime import datetime
    
    # Determine created_time
    created_time = context.created_time
    if not created_time:
        if spotify_metadata and spotify_metadata.get('release_datetime'):
            created_time = spotify_metadata['release_datetime']
        else:
            created_time = datetime.now()
    
    return PodcastEpisode(
        mp3_url=gcs_urls.get('mp3_url', ''),
        transcript_url=gcs_urls.get('transcript_url', ''),
        summary_url=gcs_urls.get('summary_url', ''),
        summary_image_url=gcs_urls.get('summary_image_url', ''),
        mp3_public_url=gcs_urls.get('mp3_public_url'),
        transcript_public_url=gcs_urls.get('transcript_public_url'),
        summary_public_url=gcs_urls.get('summary_public_url'),
        summary_image_public_url=gcs_urls.get('summary_image_public_url'),
        related_tickers=summary_result.get('related_tickers', []) if summary_result else [],
        created_time=created_time,
        number_click=0,
        num_likes=0,
        episode_title=episode_data.get('title', ''),
        podcast_name=context.podcast_name,
        episode_number=episode_data.get('episodeNumber'),
        # Spotify metadata
        spotify_embed_url=spotify_metadata.get('embed_url') if spotify_metadata else None,
        spotify_id=spotify_metadata.get('spotify_id') if spotify_metadata else None,
        spotify_url=spotify_metadata.get('spotify_url') if spotify_metadata else None,
        spotify_release_date=spotify_metadata.get('release_date') if spotify_metadata else None,
        spotify_description=spotify_metadata.get('description') if spotify_metadata else None,
        spotify_duration_ms=spotify_metadata.get('duration_ms') if spotify_metadata else None,
        spotify_images=spotify_metadata.get('images', []) if spotify_metadata else []
    )
```

## Error Handling Strategy

### Step-Level Error Handling

Each step should handle errors gracefully:

```python
def safe_step_execution(step_func, *args, **kwargs):
    """Wrapper for safe step execution."""
    try:
        return step_func(*args, **kwargs)
    except ValueError as e:
        # Configuration/input errors - log and skip step
        print(f"  ⚠ Warning: {e}")
        return None
    except Exception as e:
        # Unexpected errors - log and continue
        print(f"  ✗ Error in {step_func.__name__}: {e}")
        import traceback
        traceback.print_exc()
        return None
```

### Pipeline-Level Error Handling

```python
def process_episode(self, episode_data: Dict) -> bool:
    """Process episode with error handling."""
    try:
        # ... steps ...
        return True
    except Exception as e:
        print(f"  ✗ Fatal error processing episode: {e}")
        import traceback
        traceback.print_exc()
        return False
```

## Skip Flag Logic

### Unified Skip Logic

All skip flags work consistently:

```python
def should_execute_step(step_name: str, config: PipelineConfig, context: PipelineContext) -> bool:
    """Determine if a step should execute."""
    
    # Map step names to skip flags
    skip_flags = {
        'download': config.skip_download,
        'transcribe': config.skip_transcribe,
        'summarize': config.skip_summarize,
        'upload': config.skip_upload,
    }
    
    # Check skip flag
    if skip_flags.get(step_name, False):
        return False
    
    # Special case: transcribe can be skipped if reusing existing transcript
    if step_name == 'transcribe' and config.reuse_existing_transcript:
        # Check if transcript exists in context
        if context.transcript_text:
            return False  # Already have transcript, skip
    
    return True
```

## File Structure

```
src/
├── pipeline/
│   ├── __init__.py
│   ├── config.py          # PipelineConfig
│   ├── context.py         # PipelineContext
│   ├── processor.py       # EpisodeProcessor
│   ├── utils.py           # Helper functions
│   └── steps/
│       ├── __init__.py
│       ├── initialize.py  # Step 0
│       ├── download.py    # Step 1 (Download + Spotify metadata)
│       ├── transcribe.py  # Step 2
│       ├── summarize.py   # Step 3
│       ├── gcs_upload.py   # Step 4
│       ├── firestore.py    # Step 5
│       └── validate.py     # Step 6
└── main.py                # Simplified orchestrator
```

## Summary of Key Changes

### 1. Rerun Logic (Replaces Skip Flags)

**Old approach (skip flags):**
- `--skip-download`: Skip download step
- `--skip-transcribe`: Skip transcribe step
- `--skip-summarize`: Skip summarize step
- `--skip-upload`: Skip upload step

**New approach (rerun logic):**
- `rerun_from=None`: Full pipeline (default)
- `rerun_from="transcribe"`: Download MP3, then rerun from transcribe onwards
- `rerun_from="summarize"`: Download transcript from GCS, then rerun from summarize onwards
- `rerun_from="upload"`: Rerun only upload steps (assumes previous steps done)
- `rerun_from="validate"`: Only validate existing episode

**Benefits:**
- ✅ More intuitive: "rerun from transcribe" is clearer than "skip download"
- ✅ Explicit dependencies: Makes it clear what inputs are needed
- ✅ Flexible: Can rerun any part of the pipeline
- ✅ Idempotent: Safe to rerun from any point

### 2. Validation Results in PipelineContext

**Added to PipelineContext:**
```python
validation_results: Dict[str, bool] = field(default_factory=dict)
```

**Validation checks stored:**
- `mp3_exists`: MP3 file exists and is accessible
- `transcript_exists`: Transcript text is available and non-empty
- `summary_exists`: Summary and SVG are available
- `gcs_urls_valid`: All required GCS URLs are present
- `gcs_files_accessible`: GCS files can be accessed (if service supports it)
- `firestore_document_exists`: Episode document exists in Firestore

**Benefits:**
- ✅ Track validation state across the pipeline
- ✅ Can inspect validation results after processing
- ✅ Useful for debugging and monitoring
- ✅ Can be used to determine if rerun is needed

## Testing Strategy

### Unit Tests

Each step function can be tested independently:

```python
def test_download_step():
    """Test download step in isolation."""
    config = PipelineConfig(...)
    context = PipelineContext()
    episode_data = {...}
    
    result = download_episode(config, context, episode_data)
    assert result is not None
    assert context.mp3_path.exists()
```

### Integration Tests

Test the full pipeline:

```python
def test_full_pipeline():
    """Test complete pipeline execution."""
    config = PipelineConfig(...)
    context = initialize_services(config)
    processor = EpisodeProcessor(config, context)
    
    episode_data = {...}
    result = processor.process_episode(episode_data)
    assert result is True
```

### Mock Services

Use mocks for external services:

```python
def test_with_mocks():
    """Test with mocked services."""
    mock_firebase = MockFirebaseService()
    mock_gcs = MockGCSStorageService()
    
    context = PipelineContext(
        firebase_service=mock_firebase,
        gcs_service=mock_gcs
    )
    # ... test ...
```

