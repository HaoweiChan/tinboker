# Scripts

Utility scripts for managing the podcast downloader system.

## find_and_remove_duplicates.py

Finds and removes duplicate episodes from Firestore and GCS.

### Usage

```bash
python scripts/find_and_remove_duplicates.py
```

### What it does

1. **Fetches all episodes** from Firestore
2. **Identifies duplicates** based on:
   - Same `podcast_name` + `episode_title`
   - Same `podcast_name` + `episode_number` (if available)
3. **For each duplicate group**:
   - Displays all duplicate episodes with their details
   - Asks you which one to keep (1-N)
   - Confirms before deletion
   - Deletes the others from both Firestore and GCS

### Interactive Commands

- Enter a number (1-N) to select which episode to keep
- Enter `s` to skip the current duplicate group
- Enter `q` to quit the script
- Enter `yes` or `y` to confirm deletion

### Example Output

```
================================================================================
Duplicate Episode Finder and Remover
================================================================================

Initializing services...
✓ Services initialized

Fetching all episodes from Firestore...
✓ Found 150 episode(s) in Firestore

Analyzing episodes for duplicates...
⚠ Found 3 duplicate group(s)

================================================================================
Duplicate Group: Gooaye 股癌
================================================================================

Found 2 duplicate episode(s):

[1]
  ID: gooaye_ep123
  Podcast: Gooaye 股癌
  Title: Episode 123: Market Analysis
  Episode #: 123
  Created: 2025-01-15T10:30:00Z
  Files: MP3, Transcript, Summary, Image

[2]
  ID: gooaye_ep123_duplicate
  Podcast: Gooaye 股癌
  Title: Episode 123: Market Analysis
  Episode #: 123
  Created: 2025-01-16T11:00:00Z
  Files: MP3, Transcript, Summary, Image

Which episode should be KEPT? (1-2) or 's' to skip this group, or 'q' to quit: 1

✓ Keeping episode: gooaye_ep123
  Will delete 1 duplicate(s)

Confirm deletion? (yes/no): yes

Deleting episode: gooaye_ep123_duplicate
  Deleting files from GCS...
  ✓ Deleted mp3: podcasts/mp3/gooaye/gooaye_ep123_duplicate.mp3
  ✓ Deleted transcripts: podcasts/transcripts/gooaye/gooaye_ep123_duplicate.txt
  ✓ Deleted summaries: podcasts/summaries/gooaye/gooaye_ep123_duplicate.md
  ✓ Deleted images: podcasts/images/gooaye/gooaye_ep123_duplicate.svg
  Deleting from Firestore...
  ✓ Deleted from Firestore: gooaye_ep123_duplicate

✓ Completed. Kept 1, deleted 1.
```

### Requirements

- Environment variables configured (`.env` file):
  - `GCP_CREDENTIALS_PATH` or `GCP_CREDENTIALS_JSON`
  - `FIRESTORE_DATABASE_ID` (optional, uses default if not set)
  - `GCS_BUCKET_NAME`
  - `GCS_PROJECT_ID`
  - `GCS_CREDENTIALS_PATH` or `GCS_CREDENTIALS_JSON` (or uses GCP credentials)

### Safety Features

- **Confirmation required**: You must confirm before any deletion
- **Interactive selection**: You choose which episode to keep
- **Skip option**: You can skip any duplicate group
- **Quit anytime**: Press `q` to exit safely
- **Detailed logging**: Shows exactly what is being deleted

### Files Deleted

For each duplicate episode, the script deletes:
- MP3 file from GCS
- Transcript file from GCS
- Summary file from GCS
- Image (SVG) file from GCS
- Firestore document

### Notes

- The script only deletes files that exist in GCS (won't error if file is missing)
- Firestore document deletion happens after GCS file deletion
- If GCS deletion fails, Firestore deletion still proceeds (you may need to manually clean up orphaned files)

