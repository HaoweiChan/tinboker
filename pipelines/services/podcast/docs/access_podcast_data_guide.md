# Guide: Accessing Firestore and GCS Data for Planet Money and Optimal Finance Daily

This guide explains how to access all data stored in Firestore and Google Cloud Storage (GCS) for the podcasts "Planet Money" and "Optimal Finance Daily".

## Overview

The system stores podcast data in two places:
1. **Firestore**: Episode metadata and GCS URLs (collection: `episodes`)
2. **GCS**: Actual files (MP3, transcripts, summaries, images, etc.)

## Data Structure

### Firestore Structure

- **Collection**: `episodes`
- **Document ID Format**: `{podcast_name_hash}_{episode_title_hash}` or `{podcast_name_hash}_ep{episode_number}`
- **Document Fields**:
  - `podcast_name`: "Planet Money" or "Optimal Finance Daily"
  - `episode_title`: Episode title
  - `episode_number`: Episode number (if available)
  - `episode_id`: Same as document ID
  - `mp3_url`: GCS URL (gs://...)
  - `transcript_url`: GCS URL for transcript
  - `summary_url`: GCS URL for summary markdown
  - `summary_image_url`: GCS URL for SVG image
  - `related_tickers`: Array of ticker symbols
  - `created_time`: Timestamp
  - `number_click`: Click count
  - `num_likes`: Like count
  - `spotify_*`: Spotify metadata fields
  - Optional: `mp3_public_url`, `transcript_public_url`, etc.

### GCS Structure

Files are organized by podcast hash:
```
{base_path}/
  ├── mp3/
  │   └── {podcast_hash}/
  │       └── {episode_id}.mp3
  ├── transcripts/
  │   └── {podcast_hash}/
  │       └── {episode_id}.json (or .txt)
  ├── summaries/
  │   └── {podcast_hash}/
  │       └── {episode_id}.md
  ├── images/
  │   └── {podcast_hash}/
  │       └── {episode_id}.svg
  └── [other types: presentations/, marp/, ticker_recommendations/, etc.]
```

**Podcast Hashes** (12-character SHA256 hash):
- "Planet Money": `hashlib.sha256("Planet Money".encode('utf-8')).hexdigest()[:12]`
- "Optimal Finance Daily": `hashlib.sha256("Optimal Finance Daily".encode('utf-8')).hexdigest()[:12]`

## Method 1: Using FirebaseService (Recommended)

### Step 1: Initialize Services

```python
from src.service.upload_to_firebase import FirebaseService
from src.service.gcs_storage_service import GCSStorageService
import hashlib

# Initialize services
firebase_service = FirebaseService()
gcs_service = GCSStorageService()  # Optional, only if you need to download files
```

### Step 2: Query Episodes by Podcast Name

```python
# Get all episodes for Planet Money
planet_money_episodes = firebase_service.get_podcast_episodes(
    podcast_name="Planet Money",
    limit=None,  # None = get all episodes
    order_by="created_time",
    descending=True  # Newest first
)

# Get all episodes for Optimal Finance Daily
optimal_finance_episodes = firebase_service.get_podcast_episodes(
    podcast_name="Optimal Finance Daily",
    limit=None,
    order_by="created_time",
    descending=True
)

print(f"Planet Money: {len(planet_money_episodes)} episodes")
print(f"Optimal Finance Daily: {len(optimal_finance_episodes)} episodes")
```

### Step 3: Access Episode Data

Each episode is a dictionary with all the fields:

```python
for episode in planet_money_episodes:
    print(f"Episode: {episode['episode_title']}")
    print(f"  ID: {episode['id']}")
    print(f"  MP3 URL: {episode.get('mp3_url')}")
    print(f"  Transcript URL: {episode.get('transcript_url')}")
    print(f"  Summary URL: {episode.get('summary_url')}")
    print(f"  Image URL: {episode.get('summary_image_url')}")
    print(f"  Created: {episode.get('created_time')}")
    print(f"  Tickers: {episode.get('related_tickers', [])}")
    print()
```

### Step 4: Download Files from GCS

```python
from pathlib import Path

# Download transcript for an episode
episode = planet_money_episodes[0]
transcript_url = episode.get('transcript_url')

if transcript_url:
    # Method 1: Download as text (for JSON or text files)
    transcript_data = gcs_service.download_transcript_by_gcs_url(transcript_url)
    print(f"Transcript text: {transcript_data['text'][:200]}...")
    
    # Method 2: Download to file
    output_path = Path(f"./transcript_{episode['id']}.json")
    gcs_service.download_file_by_gcs_url(transcript_url, output_path)
    
# Download summary
summary_url = episode.get('summary_url')
if summary_url:
    summary_text = gcs_service.download_text_by_gcs_url(summary_url)
    print(f"Summary: {summary_text[:200]}...")

# Download MP3
mp3_url = episode.get('mp3_url')
if mp3_url:
    output_path = Path(f"./episode_{episode['id']}.mp3")
    gcs_service.download_file_by_gcs_url(mp3_url, output_path)
```

## Method 2: Using FirestoreService (Generic Service)

The `FirestoreService` provides more generic query capabilities:

```python
from src.service.firestore_service import FirestoreService

firestore_service = FirestoreService()

# Query episodes collection with filters
planet_money_episodes = firestore_service.query_collection(
    collection="episodes",
    filters=[("podcast_name", "==", "Planet Money")],
    order_by="created_time",
    direction="DESCENDING",
    limit=None
)

optimal_finance_episodes = firestore_service.query_collection(
    collection="episodes",
    filters=[("podcast_name", "==", "Optimal Finance Daily")],
    order_by="created_time",
    direction="DESCENDING",
    limit=None
)

# Get all episodes (then filter in Python)
all_episodes = firestore_service.get_all_documents("episodes")
planet_money = [e for e in all_episodes if e.get('podcast_name') == 'Planet Money']
optimal_finance = [e for e in all_episodes if e.get('podcast_name') == 'Optimal Finance Daily']
```

## Method 3: Direct GCS Access (List All Files)

To list all files in GCS for a specific podcast:

```python
from google.cloud import storage
import hashlib
import os

# Initialize GCS client
bucket_name = os.getenv("GCS_BUCKET_NAME")
base_path = os.getenv("GCS_BASE_PATH", "").strip('/')

# Calculate podcast hash
def get_podcast_hash(podcast_name: str) -> str:
    return hashlib.sha256(podcast_name.encode('utf-8')).hexdigest()[:12]

planet_money_hash = get_podcast_hash("Planet Money")
optimal_finance_hash = get_podcast_hash("Optimal Finance Daily")

# Initialize GCS client (using same credentials as GCSStorageService)
client = storage.Client()
bucket = client.bucket(bucket_name)

# List all files for Planet Money
file_types = ['mp3', 'transcripts', 'summaries', 'images', 'presentations', 'marp', 
              'ticker_recommendations', 'ticker_marp', 'events', 'sentences']

planet_money_files = {}
for file_type in file_types:
    prefix = f"{base_path}/{file_type}/{planet_money_hash}/" if base_path else f"{file_type}/{planet_money_hash}/"
    blobs = list(bucket.list_blobs(prefix=prefix))
    planet_money_files[file_type] = [blob.name for blob in blobs]
    print(f"Planet Money - {file_type}: {len(blobs)} files")

# Same for Optimal Finance Daily
optimal_finance_files = {}
for file_type in file_types:
    prefix = f"{base_path}/{file_type}/{optimal_finance_hash}/" if base_path else f"{file_type}/{optimal_finance_hash}/"
    blobs = list(bucket.list_blobs(prefix=prefix))
    optimal_finance_files[file_type] = [blob.name for blob in blobs]
    print(f"Optimal Finance Daily - {file_type}: {len(blobs)} files")
```

## Complete Example Script

Here's a complete script that retrieves and displays all data:

```python
#!/usr/bin/env python3
"""
Script to access all Firestore and GCS data for Planet Money and Optimal Finance Daily
"""

from src.service.upload_to_firebase import FirebaseService
from src.service.gcs_storage_service import GCSStorageService
from pathlib import Path
import json

def main():
    # Initialize services
    print("Initializing services...")
    firebase_service = FirebaseService()
    gcs_service = GCSStorageService()
    
    podcasts = ["Planet Money", "Optimal Finance Daily"]
    
    for podcast_name in podcasts:
        print(f"\n{'='*60}")
        print(f"Processing: {podcast_name}")
        print(f"{'='*60}")
        
        # Get all episodes from Firestore
        episodes = firebase_service.get_podcast_episodes(
            podcast_name=podcast_name,
            limit=None,
            order_by="created_time",
            descending=True
        )
        
        print(f"\nFound {len(episodes)} episodes")
        
        # Create output directory
        output_dir = Path(f"./output/{podcast_name.replace(' ', '_')}")
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Save episode metadata
        metadata_file = output_dir / "episodes_metadata.json"
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(episodes, f, indent=2, default=str, ensure_ascii=False)
        print(f"Saved metadata to: {metadata_file}")
        
        # Download files for first 3 episodes (as example)
        for i, episode in enumerate(episodes[:3]):
            print(f"\n  Episode {i+1}: {episode.get('episode_title', 'Unknown')}")
            episode_id = episode.get('id', 'unknown')
            episode_dir = output_dir / f"episode_{episode_id}"
            episode_dir.mkdir(exist_ok=True)
            
            # Download transcript
            if episode.get('transcript_url'):
                try:
                    transcript_data = gcs_service.download_transcript_by_gcs_url(
                        episode['transcript_url']
                    )
                    transcript_file = episode_dir / "transcript.json"
                    with open(transcript_file, 'w', encoding='utf-8') as f:
                        json.dump(transcript_data, f, indent=2, ensure_ascii=False)
                    print(f"    ✓ Downloaded transcript ({len(transcript_data.get('text', ''))} chars)")
                except Exception as e:
                    print(f"    ✗ Failed to download transcript: {e}")
            
            # Download summary
            if episode.get('summary_url'):
                try:
                    summary_text = gcs_service.download_text_by_gcs_url(
                        episode['summary_url']
                    )
                    summary_file = episode_dir / "summary.md"
                    with open(summary_file, 'w', encoding='utf-8') as f:
                        f.write(summary_text)
                    print(f"    ✓ Downloaded summary ({len(summary_text)} chars)")
                except Exception as e:
                    print(f"    ✗ Failed to download summary: {e}")
            
            # Download SVG image
            if episode.get('summary_image_url'):
                try:
                    svg_content = gcs_service.download_text_by_gcs_url(
                        episode['summary_image_url']
                    )
                    svg_file = episode_dir / "summary_image.svg"
                    with open(svg_file, 'w', encoding='utf-8') as f:
                        f.write(svg_content)
                    print(f"    ✓ Downloaded SVG image ({len(svg_content)} chars)")
                except Exception as e:
                    print(f"    ✗ Failed to download SVG: {e}")
            
            # Download MP3 (optional, can be large)
            # Uncomment if you want to download MP3 files
            # if episode.get('mp3_url'):
            #     try:
            #         mp3_file = episode_dir / "episode.mp3"
            #         gcs_service.download_file_by_gcs_url(
            #             episode['mp3_url'], mp3_file
            #         )
            #         print(f"    ✓ Downloaded MP3")
            #     except Exception as e:
            #         print(f"    ✗ Failed to download MP3: {e}")
        
        print(f"\n✓ Completed processing {podcast_name}")
        print(f"  Output directory: {output_dir}")

if __name__ == "__main__":
    main()
```

## Key Methods Reference

### FirebaseService Methods

- `get_podcast_episodes(podcast_name, limit=None, order_by="created_time", descending=True)`: Get all episodes for a podcast
- `get_episode_by_id(episode_id)`: Get a single episode by ID
- `get_all_episodes(order_by="created_time", descending=True)`: Get all episodes from all podcasts
- `get_episode_by_fields(podcast_name, episode_title, episode_number=None)`: Get episode by fields
- `get_all_podcasts()`: Get list of all unique podcast names

### GCSStorageService Methods

- `download_text_by_gcs_url(gcs_url, encoding="utf-8")`: Download text file (returns string)
- `download_transcript_by_gcs_url(gcs_url, encoding="utf-8")`: Download transcript (returns dict with 'text', 'sentences', 'words')
- `download_file_by_gcs_url(gcs_url, output_path)`: Download binary file (MP3, etc.) to file path
- `_get_podcast_hash(podcast_name)`: Get 12-character hash for podcast name

### FirestoreService Methods

- `query_collection(collection, filters=None, order_by=None, direction="DESCENDING", limit=None)`: Generic query
- `get_all_documents(collection)`: Get all documents from a collection
- `get_document(collection, doc_id)`: Get a single document by ID

## Environment Variables Required

Make sure these are set in your `.env` file:

```bash
# Firestore
GCP_CREDENTIALS_PATH=/path/to/service-account-key.json
# OR
GCP_CREDENTIALS_JSON={"type":"service_account",...}
FIRESTORE_DATABASE_ID=your-database-id  # Optional, defaults to "(default)"

# GCS
GCS_BUCKET_NAME=your-bucket-name
GCS_BASE_PATH=podcasts  # Optional
GCS_PROJECT_ID=your-project-id
```

## Notes

1. **Podcast Name Matching**: The `podcast_name` field in Firestore must match exactly: "Planet Money" or "Optimal Finance Daily" (case-sensitive).

2. **GCS URLs**: Episodes store GCS URLs in the format `gs://bucket/path/to/file`. Use `GCSStorageService` methods to download them.

3. **Public URLs**: Some episodes may have `*_public_url` fields with HTTPS URLs if the bucket is configured for public access.

4. **File Types**: The system stores multiple file types:
   - `mp3`: Audio files
   - `transcripts`: Transcripts (JSON or text)
   - `summaries`: Markdown summaries
   - `images`: SVG images
   - `presentations`: PPTX files
   - `marp`: Marp markdown files
   - `ticker_recommendations`: JSON ticker data
   - `events`: Events markdown
   - `sentences`: Sentences markdown

5. **Episode ID Format**: Episode IDs use the format `{podcast_hash}_{title_hash}` or `{podcast_hash}_ep{number}` for stable matching.
