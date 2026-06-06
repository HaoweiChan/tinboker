# GCS Storage Integration Design

**Date**: January 15, 2025  
**Version**: 1.0  
**Author**: System Design Documentation

## Overview

This document describes the current design of the Podcast Downloader pipeline's Google Cloud Storage (GCS) integration. The system has been refactored to store intermediate files (MP3, transcripts, summaries, SVG images) in Google Cloud Storage and store only URLs in Firestore, rather than storing full content directly in Firestore documents.

## Architecture

### High-Level Flow

```
Download MP3 → Transcribe → Generate Summary & SVG → Upload to GCS → Store URLs in Firestore
```

### Previous Design (Before GCS Integration)

- **Files**: Stored locally in `./data/downloads/`, `./data/transcripts/`, etc.
- **Firestore**: Stored full content (transcript text, summary markdown, SVG XML) directly in documents
- **Limitations**: 
  - Firestore 1MB document size limit
  - Large storage costs in Firestore
  - Difficult to access files programmatically

### Current Design (With GCS Integration)

- **Files**: Stored in Google Cloud Storage with organized structure
- **Firestore**: Stores only GCS URLs and metadata
- **Benefits**:
  - No Firestore document size limits
  - Lower Firestore storage costs
  - Easy file access via URLs
  - Better separation of concerns

## Google Cloud Storage Structure

### File Organization

Files are organized in GCS using the following structure:

```
{base_path}/
  ├── mp3/
  │   └── {podcast_name_hash}/
  │       └── {episode_id}.mp3
  ├── transcripts/
  │   └── {podcast_name_hash}/
  │       └── {episode_id}.txt
  ├── summaries/
  │   └── {podcast_name_hash}/
  │       └── {episode_id}.md
  └── images/
      └── {podcast_name_hash}/
          └── {episode_id}.svg
```

### Path Components

- **`{base_path}`**: Base path prefix from `GCS_BASE_PATH` environment variable (e.g., `podcasts`)
- **`{type}`**: File type directory (`mp3`, `transcripts`, `summaries`, `images`)
- **`{podcast_name_hash}`**: 12-character hash of podcast name (for URL safety with non-ASCII characters)
- **`{episode_id}`**: Episode ID that matches the Firestore document ID
- **Extension**: File extension (`.mp3`, `.txt`, `.md`, `.svg`)

### Example Paths

For a podcast named "游庭皓的財經皓角" with episode ID `f595f5aba046_5f686d50ce61210b`:

```
podcasts/mp3/f595f5aba046/f595f5aba046_5f686d50ce61210b.mp3
podcasts/transcripts/f595f5aba046/f595f5aba046_5f686d50ce61210b.txt
podcasts/summaries/f595f5aba046/f595f5aba046_5f686d50ce61210b.md
podcasts/images/f595f5aba046/f595f5aba046_5f686d50ce61210b.svg
```

## Firestore Data Structure

### Document Structure

Each episode is stored as a separate document in the `episodes` collection. The document contains:

```typescript
{
  // Identifiers
  episode_id: string              // Same as document ID
  podcast_name: string             // Name of the podcast
  episode_title: string            // Episode title
  episode_number: number | null     // Episode number from API (if available)
  
  // GCS URLs (required)
  mp3_url: string                  // GCS URL: gs://bucket/path/to/file.mp3
  transcript_url: string            // GCS URL: gs://bucket/path/to/file.txt
  summary_url: string               // GCS URL: gs://bucket/path/to/file.md
  summary_image_url: string         // GCS URL: gs://bucket/path/to/file.svg
  
  // Public HTTPS URLs (optional)
  mp3_public_url: string | null     // Public URL: https://storage.googleapis.com/...
  transcript_public_url: string | null
  summary_public_url: string | null
  summary_image_public_url: string | null
  
  // Metadata
  related_tickers: string[]         // Array of ticker symbols
  created_time: timestamp          // When episode was processed/uploaded
  number_click: number             // Click count (default: 0)
  num_likes: number                 // Like count (default: 0)
}
```

### Document ID Format

The document ID (and `episode_id` field) is generated using:

1. **Primary method**: `{podcast_name_hash}_{episode_title_hash}`
   - Podcast name is hashed (12 chars) for URL safety
   - Episode title is hashed (16 chars) for consistent length
   - Example: `f595f5aba046_5f686d50ce61210b`

2. **Fallback methods**:
   - If `episode_number` available: `{podcast_name_hash}_ep{episode_number}`
   - If title missing: `{podcast_name_hash}_{timestamp_hash}`

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
  "num_likes": 0
}
```

## Pipeline Flow

### Streaming Mode (Default)

Streaming mode is optimized for cron jobs and processes episodes with temporary files:

1. **Download**: Download MP3 to temporary file
2. **Transcribe**: Transcribe audio → returns text (in memory)
3. **Generate Summary**: Generate summary + SVG → returns content (in memory)
4. **Upload to GCS**: 
   - Save content to temporary files
   - Upload MP3, transcript, summary, and SVG to GCS
   - Get GCS URLs and public URLs
5. **Store in Firestore**: Create `PodcastEpisode` with URLs, upload to Firestore
6. **Cleanup**: Keep temp files (per user preference)

### File-Based Mode

File-based mode processes existing local files:

1. **Download**: Download MP3 to local file (`./data/downloads/`)
2. **Transcribe**: Save transcript to local file (`./data/transcripts/`)
3. **Generate Summary**: Save summary and SVG to local files (`./data/summary_content/`, `./data/images/`)
4. **Upload to GCS**: Upload all local files to GCS, get URLs
5. **Store in Firestore**: Create `PodcastEpisode` with URLs, upload to Firestore
6. **Cleanup**: Keep local files (per user preference)

## Key Components

### 1. GCSStorageService

**Location**: `src/gcs_storage_service.py`

**Responsibilities**:
- Initialize GCS client with credentials
- Upload files to GCS with organized structure
- Generate GCS URLs (`gs://`) and public HTTPS URLs
- Handle deduplication (skip existing files)
- Support both file path and content string uploads

**Key Methods**:
- `upload_episode_files()`: Upload all episode files (MP3, transcript, summary, SVG)
- `upload_file()`: Upload a single file from path
- `upload_file_from_string()`: Upload file content from string
- `generate_gcs_url()`: Generate `gs://` URL
- `generate_public_url()`: Generate public HTTPS URL

### 2. PodcastEpisode Model

**Location**: `src/models/podcast_models.py`

**Changes**:
- Replaced content fields with URL fields
- Added optional public URL fields
- Updated serialization methods

**Fields**:
- `mp3_url`, `transcript_url`, `summary_url`, `summary_image_url` (required)
- `mp3_public_url`, `transcript_public_url`, `summary_public_url`, `summary_image_public_url` (optional)

### 3. FirebaseService

**Location**: `src/upload_to_firebase.py`

**Changes**:
- `upload_podcast_data()` now accepts `GCSStorageService` and file paths/content
- Uploads files to GCS before storing in Firestore
- Stores URLs instead of content in Firestore

### 4. Main Pipeline

**Location**: `main.py`

**Changes**:
- Initializes `GCSStorageService` early in pipeline
- Passes GCS service to processing functions
- Uploads files to GCS before creating `PodcastEpisode` objects
- Handles both streaming and file-based modes

## URL Generation

### GCS URLs (`gs://`)

Format: `gs://{bucket_name}/{blob_path}`

Example: `gs://my-bucket/podcasts/mp3/f595f5aba046/f595f5aba046_5f686d50ce61210b.mp3`

- Used for programmatic access via GCS client libraries
- Requires authentication
- Standard format for GCS operations

### Public HTTPS URLs

Format: `https://storage.googleapis.com/{bucket_name}/{blob_path}`

Example: `https://storage.googleapis.com/my-bucket/podcasts/mp3/f595f5aba046/f595f5aba046_5f686d50ce61210b.mp3`

- Used for direct HTTP access
- Requires bucket or blob to be configured for public access
- Can be used in web browsers or HTTP clients

## Deduplication

The system implements deduplication at multiple levels:

1. **GCS Level**: 
   - Checks if file already exists in GCS
   - Compares file sizes
   - Skips upload if file exists with matching size

2. **Firestore Level**:
   - Checks for existing episodes by `episode_title` (primary)
   - Checks for existing episodes by `episode_number` (secondary)
   - Skips processing if episode already exists

## Environment Variables

Required environment variables:

```bash
# GCS Configuration
GCS_BUCKET_NAME=your-bucket-name
GCS_BASE_PATH=podcasts  # Optional, defaults to empty
GCS_PROJECT_ID=your-project-id
GCS_CREDENTIALS_PATH=/path/to/service-account-key.json
# OR
GCS_CREDENTIALS_JSON={"type":"service_account",...}

# Firestore Configuration
GCP_CREDENTIALS_PATH=/path/to/service-account-key.json
# OR
GCP_CREDENTIALS_JSON={"type":"service_account",...}
FIRESTORE_DATABASE_ID=your-database-id  # Optional, uses default if not set
```

## Design Decisions

### 1. Why Hash Podcast Names?

Podcast names may contain non-ASCII characters (e.g., Chinese, Japanese). Hashing ensures:
- URL-safe directory names
- Consistent length
- No filesystem compatibility issues

### 2. Why Use Episode ID in File Names?

Using the episode ID (which matches Firestore document ID) ensures:
- Easy correlation between Firestore documents and GCS files
- Unique file names
- Consistent naming across all file types

### 3. Why Store Both GCS and Public URLs?

- **GCS URLs**: For programmatic access via GCS client libraries
- **Public URLs**: For direct HTTP access (if bucket is public)
- Provides flexibility for different use cases

### 4. Why Organize by File Type?

Organizing files by type (`mp3/`, `transcripts/`, etc.) provides:
- Clear separation of concerns
- Easy to apply different access policies per type
- Better organization for browsing/managing files

### 5. Why Keep Local Files?

Per user preference, local files are kept after GCS upload:
- Backup in case of GCS issues
- Easier debugging
- Can be configured to delete if needed

## Migration Notes

- **No Backward Compatibility**: The new format stores URLs instead of content. Existing Firestore documents with full content remain unchanged.
- **New Episodes Only**: Only new episodes use the URL-based format.
- **Manual Migration**: If needed, existing episodes can be migrated by:
  1. Reading content from Firestore
  2. Uploading to GCS
  3. Updating Firestore document with URLs

## Future Considerations

1. **Signed URLs**: Could generate time-limited signed URLs for secure access
2. **CDN Integration**: Could integrate with CDN for faster file delivery
3. **File Versioning**: Could implement versioning for updated files
4. **Lifecycle Policies**: Could set up GCS lifecycle policies for automatic archival
5. **Compression**: Could compress files before upload to reduce storage costs

## Testing

The system has been tested with:
- Streaming mode (temp files)
- File-based mode (local files)
- Both GCS URL and public URL generation
- Deduplication logic
- Error handling (missing GCS service, missing files, etc.)

## References

- [Google Cloud Storage Documentation](https://cloud.google.com/storage/docs)
- [Firestore Documentation](https://cloud.google.com/firestore/docs)
- [GCS Storage Service Implementation](../src/gcs_storage_service.py)
- [Podcast Episode Model](../src/models/podcast_models.py)
- [Firebase Upload Service](../src/upload_to_firebase.py)

