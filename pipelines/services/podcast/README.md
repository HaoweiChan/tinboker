# Podcast Downloader

A Python pipeline to download podcast episodes, transcribe them to text, generate summaries, and upload to Google Cloud Firestore.

## Overview

The system uses a **step-based pipeline architecture** that processes episodes through independent, testable steps. Files are stored in **Google Cloud Storage (GCS)** with only URLs stored in Firestore, reducing document size and storage costs.

**For detailed architecture documentation, see:** [`docs/dev/251221_simplify_refactor/simplified_architecture.md`](docs/dev/251221_simplify_refactor/simplified_architecture.md)

## Architecture

The pipeline uses a simplified step-based architecture:

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
│   MP3 +      │ │              │ │              │
│   Spotify    │ │              │ │              │
└──────┬───────┘ └──────┬───────┘ └──────┬───────┘
       │                │                 │
       └────────────────┼─────────────────┘
                        │
                        ▼
              ┌──────────────────┐
              │   Step 4:        │
              │   Upload to GCS  │
              └────────┬─────────┘
                       │
        ┌──────────────┼──────────────┐
        │              │               │
        ▼              ▼               ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│   Step 5:    │ │   Step 6:    │ │               │
│   Upload to  │ │   Validate   │ │               │
│   Firestore  │ │              │ │               │
└──────────────┘ └──────────────┘ └──────────────┘
```

### Pipeline Steps

1. **Step 0: Initialize Services** - Initializes Firebase, STT, GCS, and Summarize services
2. **Step 1: Download MP3 + Fetch Spotify Metadata** - Downloads episode MP3 and fetches Spotify metadata (if available)
3. **Step 2: Transcribe** - Transcribes audio to text using Deepgram or AssemblyAI
4. **Step 3: Summarize** - Generates summary, SVG image, and extracts ticker symbols
5. **Step 4: Upload to GCS** - Uploads MP3, transcript, summary, and SVG to Google Cloud Storage
6. **Step 5: Upload to Firestore** - Stores episode metadata and GCS URLs in Firestore
7. **Step 6: Validate** - Validates that all processing completed successfully

## Project Structure

```
podcast_downloader/
├── src/                    # Source code modules
│   ├── pipeline/          # Pipeline architecture
│   │   ├── config.py     # PipelineConfig dataclass
│   │   ├── context.py    # PipelineContext dataclass
│   │   ├── processor.py  # EpisodeProcessor class
│   │   ├── utils.py      # Helper functions
│   │   └── steps/        # Processing steps
│   │       ├── initialize.py
│   │       ├── download.py
│   │       ├── transcribe.py
│   │       ├── summarize.py
│   │       ├── gcs_upload.py
│   │       ├── firestore.py
│   │       └── validate.py
│   ├── download_podcasts.py
│   ├── speech_to_text.py
│   ├── summarize/
│   ├── upload_to_firebase.py
│   ├── gcs_storage_service.py
│   └── models/            # Data models
├── data/                   # Data directories (file-based mode)
│   ├── downloads/         # Downloaded MP3 files
│   ├── transcripts/       # Transcribed text files
│   ├── summary_content/   # Generated summaries (markdown)
│   └── images/            # Generated summary images (SVG)
├── tests/                  # Test files
├── main.py                # Main pipeline coordinator
├── podcasts_tw.json  # Podcast configuration
└── requirements.txt       # Python dependencies
```

## Setup

1. Install dependencies:

**Using pip:**
```bash
pip install -r requirements.txt
```

**Using uv (recommended - faster):**
```bash
# Create a virtual environment first
uv venv

# Activate it
source .venv/bin/activate  # On Linux/WSL/Mac

# Install requirements
uv pip install -r requirements.txt

# Or install directly to venv without activating:
uv venv
uv pip install --python .venv -r requirements.txt
```

2. Configure environment variables:

Create a `.env` file in the project root with the following variables:

```bash
# Speech-to-Text API Keys (at least one required)
DEEPGRAM_API_KEY=your_deepgram_api_key
ASSEMBLYAI_API_KEY=your_assemblyai_api_key

# Google Cloud Storage (REQUIRED for upload step)
GCS_BUCKET_NAME=your-bucket-name
GCS_BASE_PATH=podcasts  # Optional, defaults to empty
GCS_PROJECT_ID=your-project-id
GCS_CREDENTIALS_PATH=/path/to/service-account-key.json
# OR use JSON string directly:
# GCS_CREDENTIALS_JSON={"type":"service_account","project_id":"...","private_key":"..."}

# Google Cloud Firestore (REQUIRED for upload step)
GCP_CREDENTIALS_PATH=/path/to/service-account-key.json
# OR use JSON string directly:
# GCP_CREDENTIALS_JSON={"type":"service_account","project_id":"...","private_key":"..."}

# Firestore Database ID (OPTIONAL - uses default database if not specified)
# FIRESTORE_DATABASE_ID=graphfolio-db

# Content-Builder LLM Configuration (REQUIRED for summarization)
# At least one LLM provider API key is required
# Google Gemini (recommended)
GOOGLE_API_KEY=your_google_api_key
# OR OpenAI
OPENAI_API_KEY=your_openai_api_key
# OR Anthropic
ANTHROPIC_API_KEY=your_anthropic_api_key
```

**Note**: 
- See `docs/firebase-credentials.md` for detailed Firestore setup instructions.
- See `docs/cloud-storage-env-vars.md` for detailed GCS setup instructions.

3. Configure Content-Builder LLM models (optional):

The Content-Builder library uses LLM models for generating summaries. You can configure the models and settings in `configs/default.yaml`:

```yaml
# LLM settings
llm:
  default_provider: gemini  # gemini | openai | anthropic | google
  extractor_model: gemini-2.0-flash
  researcher_model: gemini-2.0-flash
  writer_model: gemini-2.0-flash
  segmentation_model: gemini-2.0-flash
  temperatures:
    extractor: 0.1      # Deterministic extraction
    researcher: 0.0      # Factual retrieval
    writer: 0.4          # Some creativity in phrasing
    segmentation: 0.0    # Deterministic segmentation
```

**Supported Models:**
- **Gemini**: `gemini-2.0-flash`, `gemini-2.5-flash`, `gemini-2.5-pro`
- **OpenAI**: `gpt-4o`, `gpt-5-mini`
- **Anthropic**: `claude-3.7-sonnet`

**Getting API Keys:**
- **Google Gemini**: Get your API key from [Google AI Studio](https://makersuite.google.com/app/apikey)
- **OpenAI**: Get your API key from [OpenAI Platform](https://platform.openai.com/api-keys)
- **Anthropic**: Get your API key from [Anthropic Console](https://console.anthropic.com/)

The default configuration uses Gemini models. If you want to use a different provider, set the `default_provider` in `configs/default.yaml` and ensure the corresponding API key is set in your `.env` file.

4. Configure podcasts to download:

Edit `podcasts_tw.json` with your podcast list:
```json
[
  {
    "name": "Gooaye 股癌",
    "link": "https://podcasttomp3.com/podcasts/v2/358931",
    "limit": 10,
    "spotify_show_link": "https://open.spotify.com/show/..."
  },
  {
    "name": "Another Podcast",
    "link": "https://podcasttomp3.com/podcasts/v2/123456"
  }
]
```

**Fields:**
- `name`: Podcast name (required)
- `link`: Podcast download link (required)
- `limit`: Optional. Limits number of episodes to process (default: 2)
- `spotify_show_link`: Optional. Spotify show link for fetching additional metadata

## Usage

### Basic Usage

Run the complete pipeline (download → transcribe → summarize → upload):

```bash
python main.py
```

### Command-Line Options

```bash
# Use a different config file
python main.py --config my_podcasts.json

# Rerun from specific step (new rerun logic)
python main.py --rerun-from download     # Download MP3 and rerun all steps, treating each episode as new (re-uploads all files including MP3)
python main.py --rerun-from transcribe  # Download MP3, then rerun from transcribe onwards
python main.py --rerun-from summarize   # Download transcript from GCS, then rerun from summarize onwards
python main.py --rerun-from upload      # Rerun only upload steps (assumes previous steps done)
python main.py --rerun-from validate     # Only validate existing episode

# Choose speech-to-text service
python main.py --service deepgram        # Use Deepgram (default: assemblyai)
python main.py --service assemblyai     # Use AssemblyAI

# Fill limit mode: Skip processed episodes and process exactly 'limit' non-processed ones
python main.py --fill-limit
python main.py --fill-limit --transcript-service groq
```

### Rerun Logic

The pipeline uses a **rerun logic** that's more intuitive than skip flags:

- **`--rerun-from transcribe`**: Downloads MP3 file, then reruns from transcribe onwards
  - Useful when you want to retranscribe with a different service or settings
  
- **`--rerun-from summarize`**: Downloads transcript from GCS, then reruns from summarize onwards
  - Useful when you want to regenerate summaries without retranscribing
  
- **`--rerun-from upload`**: Reruns only upload steps (assumes previous steps are done)
  - Useful when you want to re-upload files to GCS or update Firestore
  
- **`--rerun-from validate`**: Only validates existing episode
  - Useful for checking if an episode was processed correctly

- **`--fill-limit`**: Skips already-processed episodes and processes exactly `limit` number of non-processed episodes
  - Fetches episodes from API and checks each against Firestore
  - Filters out episodes that are already fully processed (have all required GCS URLs: mp3_url, transcript_url, summary_url, summary_image_url)
  - Processes exactly the number specified in `limit` field in `podcasts_tw.json`
  - Fetches 3x the limit from API to ensure enough candidates are available
  - Useful for cron jobs or automated processing where you want to ensure a certain number of new episodes are processed

**Benefits:**
- More intuitive: "rerun from transcribe" is clearer than "skip download"
- Explicit dependencies: Makes it clear what inputs are needed
- Flexible: Can rerun any part of the pipeline
- Idempotent: Safe to rerun from any point

### Processing Modes

#### Streaming Mode (Default)

Optimized for running as a daily cron job:

**Features:**
- **Deduplication**: Checks Firestore before processing to avoid reprocessing existing episodes
- **Temp file processing**: Downloads MP3s to temporary files, processes in memory, then cleans up
- **Efficient**: Only processes new episodes, skips ones already in Firestore
- **Idempotent**: Safe to run multiple times without duplicating work

**Usage:**
```bash
# Streaming mode (default)
python main.py
```

**How it works:**
1. Fetches latest N episodes from API (based on `limit` in config)
2. Queries Firestore for existing episodes
3. Filters out episodes that already exist
4. For each new episode:
   - Downloads MP3 to temp file
   - Transcribes from temp file → returns text (in memory)
   - Generates summary from text → returns summary + SVG (in memory)
   - Uploads files to Google Cloud Storage
   - Stores GCS URLs in Firestore
   - Keeps temp files (per configuration)

#### File-Based Mode

Saves intermediate files to disk for debugging or manual inspection:

**Usage:**
```bash
# File-based mode
python main.py --file-mode
```

**Output locations:**
- Downloads: `./data/downloads/{podcast_name}/{episode_title}.mp3`
- Transcripts: `./data/transcripts/{podcast_name}/{episode_title}.txt`
- Summaries: `./data/summary_content/{podcast_name}/{episode_title}.md`
- Images: `./data/images/{podcast_name}/{episode_title}.svg`

### Deploying as Cron Service

**On Render:**

1. Create a new **Cron Job** service on Render
2. Set the command: `python main.py`
3. Set schedule: `0 0 * * *` (daily at midnight UTC)
4. Set environment variables (same as `.env` file)
5. The service will automatically:
   - Check Firestore for existing episodes
   - Only process new episodes
   - Clean up temp files after processing

**Note:** Streaming mode is the default. Use `--file-mode` only if you need to save files to disk for debugging or other purposes.

## Features

### Download
- Downloads episodes from podcast API
- Optional limit on number of episodes to download
- Shows download progress
- Skips already downloaded files (> 1MB)
- Automatically re-downloads incomplete files (< 1MB)
- Retry logic for failed downloads
- Handles errors gracefully
- Sanitizes filenames for filesystem compatibility
- Fetches Spotify metadata (if `spotify_show_link` is provided)

### Transcription
- Supports multiple speech-to-text services (Deepgram, AssemblyAI)
- Automatic language detection (Chinese/Mandarin vs English)
- Preserves directory structure from downloads to transcripts (file mode)
- Skips already transcribed files
- Supports punctuation and text formatting (especially for Chinese)
- Can download existing transcripts from GCS when rerunning from summarize

### Summarization
- Generates markdown summaries from transcripts
- Creates SVG visualization images
- Extracts related ticker symbols
- Saves summaries and images to organized directories (file mode)
- Uses Content-Builder library with configurable LLM models

### Upload to Firestore
- Uploads episode files (MP3, transcript, summary, SVG) to Google Cloud Storage
- Stores GCS URLs in Firestore (not full content)
- Each episode stored as a separate document (avoids 1MB document limit)
- Stores: GCS URLs, metadata, related tickers, Spotify metadata
- Efficient querying by podcast name and time
- **Deduplication**: Uses `episode_title` (primary) and `episode_number` (secondary) for stable matching with API episodes

### Validation
- Validates that MP3 file exists
- Validates that transcript is available and non-empty
- Validates that summary and SVG are available
- Validates that all GCS URLs are present
- Validates that Firestore document exists
- Stores validation results in `PipelineContext` for inspection

## Firestore Data Structure

The application stores podcast episodes in Google Cloud Firestore with the following structure:

### Collection: `episodes`

Each episode is stored as a separate document to avoid Firestore's 1MB document size limit.

### Document ID Format

The document ID is generated using:
- **Primary method**: `{podcast_name_hash}_{episode_title_hash}`
  - Podcast name is hashed (12 chars) to handle non-ASCII characters (e.g., Chinese)
  - Episode title is hashed (16 chars) for consistent length
  - Example: `f595f5aba046_5f686d50ce61210b`
- **Fallback methods**:
  - If episode_number available: `{podcast_name_hash}_ep{episode_number}`
  - If title missing: `{podcast_name_hash}_{timestamp_hash}`

### Document Fields

Each episode document contains the following fields:

```typescript
{
  // Identifiers
  episode_id: string              // Same as document ID
  podcast_name: string             // Name of the podcast (e.g., "游庭皓的財經皓角")
  episode_title: string            // Episode title (e.g., "2025/12/10(三)11月出口再創高!")
  episode_number: number | null     // Episode number from API (if available)
  
  // GCS URLs (files stored in Google Cloud Storage)
  mp3_url: string                   // GCS URL for MP3 file (gs://...)
  transcript_url: string            // GCS URL for transcript file (gs://...)
  summary_url: string               // GCS URL for summary markdown file (gs://...)
  summary_image_url: string         // GCS URL for SVG image file (gs://...)
  
  // Optional public HTTPS URLs
  mp3_public_url: string | null     // Public HTTPS URL (if bucket is public)
  transcript_public_url: string | null
  summary_public_url: string | null
  summary_image_public_url: string | null
  
  // Metadata
  related_tickers: string[]         // Array of ticker symbols (e.g., ["AAPL", "MSFT"])
  created_time: timestamp           // When episode was processed/uploaded
  number_click: number              // Click count (default: 0)
  num_likes: number                 // Like count (default: 0)
  
  // Spotify metadata (optional)
  spotify_embed_url: string | null
  spotify_id: string | null
  spotify_url: string | null
  spotify_release_date: string | null
  spotify_description: string | null
  spotify_duration_ms: number | null
  spotify_images: string[]          // Array of image URLs
}
```

### Example Document

```json
{
  "episode_id": "f595f5aba046_5f686d50ce61210b",
  "podcast_name": "游庭皓的財經皓角",
  "episode_title": "2025/12/10(三)11月出口再創高!台灣景氣 真的那麼好?【早晨財經速解讀】",
  "episode_number": 503,
  "mp3_url": "gs://my-bucket/podcasts/mp3/f595f5aba046/f595f5aba046_5f686d50ce61210b.mp3",
  "transcript_url": "gs://my-bucket/podcasts/transcripts/f595f5aba046/f595f5aba046_5f686d50ce61210b.txt",
  "summary_url": "gs://my-bucket/podcasts/summaries/f595f5aba046/f595f5aba046_5f686d50ce61210b.md",
  "summary_image_url": "gs://my-bucket/podcasts/images/f595f5aba046/f595f5aba046_5f686d50ce61210b.svg",
  "mp3_public_url": "https://storage.googleapis.com/my-bucket/podcasts/mp3/f595f5aba046/f595f5aba046_5f686d50ce61210b.mp3",
  "transcript_public_url": "https://storage.googleapis.com/my-bucket/podcasts/transcripts/f595f5aba046/f595f5aba046_5f686d50ce61210b.txt",
  "summary_public_url": "https://storage.googleapis.com/my-bucket/podcasts/summaries/f595f5aba046/f595f5aba046_5f686d50ce61210b.md",
  "summary_image_public_url": "https://storage.googleapis.com/my-bucket/podcasts/images/f595f5aba046/f595f5aba046_5f686d50ce61210b.svg",
  "related_tickers": ["AAPL", "MSFT", "GOOGL"],
  "created_time": "2025-01-15T10:30:00Z",
  "number_click": 0,
  "num_likes": 0,
  "spotify_embed_url": "https://open.spotify.com/embed/episode/...",
  "spotify_id": "4rOoJ6Egrf8K2IrywzwOMk",
  "spotify_url": "https://open.spotify.com/episode/...",
  "spotify_release_date": "2025-01-15",
  "spotify_description": "Episode description...",
  "spotify_duration_ms": 3600000,
  "spotify_images": ["https://i.scdn.co/image/..."]
}
```

### Querying Episodes

**Get all episodes for a podcast:**
```python
episodes = firebase_service.get_podcast_episodes(
    podcast_name="游庭皓的財經皓角",
    limit=10,
    order_by="created_time",
    descending=True
)
```

**Get a specific episode by ID:**
```python
episode = firebase_service.get_episode_by_id("f595f5aba046_5f686d50ce61210b")
```

**Check if episode exists:**
```python
exists = firebase_service.episode_exists(
    podcast_name="游庭皓的財經皓角",
    episode_title="2025/12/10(三)11月出口再創高!",
    episode_number=503
)
```

### Deduplication

The pipeline uses two methods to prevent duplicate processing:

1. **Primary**: Match by `episode_title` (always available from API)
2. **Secondary**: Match by `episode_number` (if available)

Before processing, the pipeline:
1. Fetches latest N episodes from API
2. Queries Firestore for existing `episode_title` values
3. Filters out episodes that already exist
4. Only processes new episodes

This ensures idempotent operation - safe to run multiple times without creating duplicates.

## Testing

Run the test suite:

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test file
pytest tests/test_download_podcasts.py

# Run with verbose output
pytest -v
```

View coverage report:
```bash
# After running with coverage, open htmlcov/index.html in your browser
```

## Speech-to-Text Services

The pipeline supports multiple speech-to-text services:

- **AssemblyAI** (default): Good accuracy, supports Chinese with punctuation
- **Deepgram**: Fast processing, competitive pricing

See `docs/mp3-to-transcript.md` for detailed comparison and setup instructions.

## Architecture Benefits

The new step-based architecture provides:

1. **Unified Mode**: File-based mode is just a config flag, not separate code
2. **Consistent Rerun Logic**: Rerun flags work the same way everywhere
3. **Testable Steps**: Each step can be tested independently
4. **Clear Dependencies**: Services are injected, not created inside functions
5. **Idempotent**: Steps check if work is already done
6. **Easy to Extend**: Add new steps by creating new functions
7. **Better Error Handling**: Each step handles its own errors
8. **Validation Tracking**: Validation results stored in context for inspection

## Troubleshooting

### Common Issues

**Issue**: "Error initializing Firebase service"
- **Solution**: Check that `GCP_CREDENTIALS_PATH` or `GCP_CREDENTIALS_JSON` is set correctly in `.env`

**Issue**: "Error initializing GCS storage service"
- **Solution**: Check that `GCS_BUCKET_NAME`, `GCS_PROJECT_ID`, and `GCS_CREDENTIALS_PATH` are set correctly in `.env`

**Issue**: "No download URL in episode data"
- **Solution**: Check that the podcast link in `podcasts_tw.json` is valid and accessible

**Issue**: "Transcript not available for summarization"
- **Solution**: Ensure transcription step completed successfully. Check STT service API keys.

**Issue**: "Episode not found in Firestore after upload"
- **Solution**: Check validation results in `PipelineContext.validation_results` for detailed error information

## License

[Add your license information here]

