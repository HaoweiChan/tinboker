# Main.py Refactoring Plan

## Flow Charts

### Original Flow (Streaming Mode - Default)

```
START
  │
  ├─> 0. Service Check & Initialization
  │     ├─ FirebaseService (if not --skip-upload)
  │     ├─ STTService (if not --skip-transcribe)
  │     └─ GCSStorageService (if not --skip-upload)
  │
  ├─> 1. Load Config
  │     └─ Load podcasts_to_download.json
  │
  ├─> 2. For Each Podcast:
  │     ├─ Extract podcast ID from link
  │     ├─ Fetch episodes from API
  │     ├─ Apply limit (latest N episodes)
  │     └─ Check Firestore for existing episodes (deduplication)
  │
  └─> 3. For Each Episode:
        │
        ├─> Check if exists in Firestore?
        │   ├─ YES → Skip episode (unless --skip-transcript)
        │   └─ NO  → Continue
        │
        ├─> [Step 1] Download MP3 to temp file
        ├─> [Step 2] Transcribe MP3 → transcript text (in memory)
        ├─> [Step 3] Generate summary → summary + SVG (in memory)
        ├─> [Step 4] Fetch Spotify metadata (if available)
        ├─> [Step 5] Generate episode ID
        ├─> [Step 6] Upload files to GCS (MP3, transcript, summary, SVG)
        ├─> [Step 7] Create PodcastEpisode object with GCS URLs
        └─> [Step 8] Upload to Firestore

END
```

### Reuse Transcript Flow (--skip-transcript)

```
START
  │
  ├─> 0. Service Check & Initialization (same as original)
  ├─> 1. Load Config (same as original)
  └─> 2. For Each Podcast: (same as original)
        │
        └─> 3. For Each Episode:
              │
              ├─> Check if exists in Firestore?
              │   │
              │   ├─> NEW EPISODE
              │   │   └─> Full pipeline:
              │   │       ├─> Download MP3
              │   │       ├─> Transcribe MP3
              │   │       ├─> Generate Summary
              │   │       ├─> Fetch Spotify metadata
              │   │       ├─> Upload to GCS
              │   │       └─> Upload to Firestore
              │   │
              │   └─> EXISTING EPISODE
              │       └─> Reuse transcript flow:
              │           ├─> Download transcript from GCS (by transcript_url)
              │           ├─> Generate new summary from existing transcript
              │           ├─> Upload new summary + SVG to GCS
              │           ├─> Update PodcastEpisode object
              │           └─> Update Firestore document

END
```

### File-Based Mode Flow (--file-mode)

```
START
  │
  ├─> 0. Service Check (only if upload needed)
  ├─> 1. Load Config
  │
  ├─> [STEP 1] Download (if not --skip-download)
  │     └─> Download MP3s to ./data/downloads/
  │
  ├─> [STEP 2] Transcribe (if not --skip-transcribe)
  │     └─> Transcribe MP3s → ./data/transcripts/
  │
  ├─> [STEP 3] Summarize (if not --skip-summarize)
  │     └─> Generate summaries → ./data/summary_content/ + ./data/images/
  │
  └─> [STEP 4] Upload (if not --skip-upload)
        └─> For each MP3 file:
            ├─> Find corresponding transcript, summary, SVG
            ├─> Upload all files to GCS
            ├─> Create PodcastEpisode object
            └─> Upload to Firestore

END
```

## Current Flow Analysis

### Original Flow (Streaming Mode - Default)

```
0. Service Initialization
   ├─ Check Firebase service availability (if not --skip-upload)
   ├─ Check STT service availability (if not --skip-transcribe)
   └─ Check GCS service availability (if not --skip-upload)

1. Load Config
   └─ Load podcasts_to_download.json

2. For Each Podcast:
   ├─ Extract podcast ID from link
   ├─ Fetch episodes from API
   ├─ Apply limit (get latest N episodes)
   └─ Check Firestore for existing episodes (deduplication)

3. For Each Episode:
   ├─ Check if episode exists in Firestore (by title/number)
   │  └─ If exists → Skip (unless --skip-transcript)
   │
   ├─ [NEW EPISODE] Download MP3 to temp file
   ├─ [NEW EPISODE] Transcribe MP3 → transcript text (in memory)
   ├─ Generate summary from transcript → summary + SVG (in memory)
   ├─ Fetch Spotify metadata (if spotify_show_link provided)
   ├─ Generate episode ID
   ├─ Upload files to GCS (MP3, transcript, summary, SVG)
   ├─ Create PodcastEpisode object with GCS URLs
   └─ Upload to Firestore

4. Cleanup
   └─ Remove temp files (optional, currently kept)
```

### Reuse Transcript Flow (--skip-transcript)

```
0. Service Initialization (same as above)

1. Load Config (same as above)

2. For Each Podcast:
   ├─ Extract podcast ID from link
   ├─ Fetch episodes from API
   ├─ Apply limit
   └─ Check Firestore for existing episodes

3. For Each Episode:
   ├─ Check if episode exists in Firestore
   │  ├─ If NEW → Full pipeline (download → transcribe → summarize → upload)
   │  └─ If EXISTING → Reuse transcript flow:
   │     ├─ Download transcript from GCS (by transcript_url)
   │     ├─ Generate new summary from existing transcript
   │     ├─ Upload new summary + SVG to GCS
   │     ├─ Update PodcastEpisode object
   │     └─ Update Firestore document
   │
   └─ (Skip download/transcribe for existing episodes)
```

### File-Based Mode (--file-mode)

```
0. Service Initialization (only if needed for upload step)

1. Load Config

2. [STEP 1] Download (if not --skip-download)
   └─ Download MP3s to ./data/downloads/

3. [STEP 2] Transcribe (if not --skip-transcribe)
   └─ Transcribe MP3s from ./data/downloads/ → ./data/transcripts/

4. [STEP 3] Summarize (if not --skip-summarize)
   └─ Generate summaries from ./data/transcripts/ → ./data/summary_content/ + ./data/images/

5. [STEP 4] Upload (if not --skip-upload)
   ├─ For each MP3 file:
   │  ├─ Find corresponding transcript, summary, SVG
   │  ├─ Upload all files to GCS
   │  ├─ Create PodcastEpisode object
   │  └─ Upload to Firestore
   └─ (No deduplication in file mode)
```

### Skip Flag Scenarios

#### --skip-download
- **Streaming mode**: Episodes must be downloaded, so this flag is ignored
- **File mode**: Skips Step 1, expects MP3s already in ./data/downloads/

#### --skip-transcribe
- **Streaming mode**: Episodes must be transcribed, so this flag is ignored
- **File mode**: Skips Step 2, expects transcripts already in ./data/transcripts/

#### --skip-summarize
- **Streaming mode**: Skips summarization (but still needs transcript for upload)
- **File mode**: Skips Step 3, expects summaries already in ./data/summary_content/

#### --skip-upload
- **Streaming mode**: Skips Firestore/GCS upload, processes but doesn't save
- **File mode**: Skips Step 4, files remain on disk only

#### --skip-transcript (reuse existing transcripts)
- **Streaming mode only**: For existing episodes, reuse transcript from GCS
- **File mode**: Not applicable

## Proposed Simplified Flow

### Core Pipeline Steps

```
0. Initialize Services
   ├─ FirebaseService (if upload enabled)
   ├─ STTService (if transcribe enabled)
   └─ GCSStorageService (if upload enabled)

1. Load Config
   └─ Load podcasts_to_download.json

2. For Each Podcast:
   ├─ Extract podcast ID
   ├─ Fetch episodes from API
   ├─ Apply limit
   └─ Check existing episodes in Firestore (deduplication)

3. For Each Episode:
   ├─ Check if exists in Firestore/GCS
   │  └─ If exists → Skip (or reuse transcript if --skip-transcript)
   │
   ├─ [Step 1] Download MP3 (if needed)
   ├─ [Step 2] Transcribe MP3 (if needed)
   ├─ [Step 3] Generate Summary (if needed)
   ├─ [Step 4] Fetch Spotify Metadata (if available)
   ├─ [Step 5] Upload to GCS
   ├─ [Step 6] Upload to Firestore
   └─ [Step 7] Validate (optional - not currently implemented)
```

### Simplified Function Structure

```python
def process_episode(episode_data, config):
    """
    Single function to process one episode through all steps.
    Each step checks if it's needed and if data already exists.
    """
    # Step 1: Download (if needed)
    mp3_path = download_if_needed(episode_data)
    
    # Step 2: Transcribe (if needed)
    transcript = transcribe_if_needed(mp3_path, episode_data)
    
    # Step 3: Summarize (if needed)
    summary = summarize_if_needed(transcript, episode_data)
    
    # Step 4: Spotify metadata (if available)
    spotify_metadata = fetch_spotify_metadata_if_available(episode_data)
    
    # Step 5: Upload to GCS
    gcs_urls = upload_to_gcs(episode_data, mp3_path, transcript, summary)
    
    # Step 6: Upload to Firestore
    upload_to_firestore(episode_data, gcs_urls, spotify_metadata)
    
    # Step 7: Validate (optional)
    validate_upload(episode_data, gcs_urls)
```

## Complexity Issues

### Current Problems:

1. **Two separate modes** (streaming vs file-based) with duplicate logic
2. **Complex skip flag handling** - different behavior in different modes
3. **Mixed concerns** - deduplication, processing, and file management all in one function
4. **Duplicate episode processing logic** - `process_episode_streaming` vs `process_episode_with_existing_transcript`
5. **Inconsistent error handling** - some steps fail silently, others raise exceptions
6. **Hard to test** - tightly coupled functions with many dependencies

### Proposed Simplifications:

1. **Unified processing function** - one function handles all episode processing
2. **Step-based architecture** - each step is a separate, testable function
3. **Consistent skip logic** - skip flags work the same way regardless of mode
4. **Clear separation** - deduplication, processing, validation are separate concerns
5. **Better error handling** - consistent error handling across all steps
6. **Mode abstraction** - file-based mode becomes a wrapper around streaming mode

## Next Steps

1. ✅ Document current flows (this document)
2. ✅ Design simplified architecture (see `simplified_architecture.md`)
3. ⬜ Implement step-based processing functions
4. ⬜ Refactor main pipeline function
5. ⬜ Add validation step (Step 7)
6. ⬜ Update tests
7. ⬜ Update documentation

