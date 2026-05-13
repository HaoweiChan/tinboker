#!/usr/bin/env python3
"""
Script to find and remove duplicate episodes from Firestore and GCS.

This script:
1. Fetches all episodes from Firestore
2. Identifies duplicates based on:
   - Same podcast_name + episode_title
   - Same podcast_name + episode_number (if available)
3. For each duplicate group, asks the user which one to keep
4. Deletes the others from both Firestore and GCS
"""

import hashlib
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.service.firestore_service import FirestoreService
from src.service.gcs_storage_service import GCSStorageService


def parse_gcs_url(gcs_url: str) -> Optional[str]:
    """
    Parse a GCS URL (gs://bucket/path) and return the blob path.
    
    Args:
        gcs_url: GCS URL in format gs://bucket/path
        
    Returns:
        Blob path (path without bucket name) or None if invalid
    """
    if not gcs_url or not gcs_url.startswith('gs://'):
        return None
    
    # Remove gs:// prefix
    path = gcs_url[5:]
    
    # Find first / to separate bucket from path
    if '/' not in path:
        return None
    
    # Return path after bucket name
    return '/'.join(path.split('/')[1:])


def get_content_hash(content: str) -> str:
    """
    Generate a hash for content comparison.
    
    Args:
        content: Content string to hash
        
    Returns:
        SHA256 hash of normalized content
    """
    if not content:
        return ""
    # Normalize: strip whitespace, convert to lowercase for comparison
    normalized = content.strip().lower()
    return hashlib.sha256(normalized.encode('utf-8')).hexdigest()[:16]


def download_episode_content(gcs_service: GCSStorageService, episode: Dict) -> Dict[str, Optional[str]]:
    """
    Download summary and transcript content from GCS for an episode.
    
    Args:
        gcs_service: GCSStorageService instance
        episode: Episode dictionary with GCS URLs
        
    Returns:
        Dictionary with 'summary' and 'transcript' keys (None if unavailable)
    """
    content = {'summary': None, 'transcript': None}
    
    # Download summary
    summary_url = episode.get('summary_url')
    if summary_url:
        try:
            summary_text = gcs_service.download_text_by_gcs_url(summary_url)
            content['summary'] = summary_text
        except Exception as e:
            print(f"  ⚠ Warning: Could not download summary for {episode.get('id')}: {e}")
    
    # Download transcript
    transcript_url = episode.get('transcript_url')
    if transcript_url:
        try:
            transcript_data = gcs_service.download_transcript_by_gcs_url(transcript_url)
            if transcript_data and transcript_data.get('text'):
                content['transcript'] = transcript_data.get('text', '')
        except Exception as e:
            print(f"  ⚠ Warning: Could not download transcript for {episode.get('id')}: {e}")
    
    return content


def find_duplicates(episodes: List[Dict], gcs_service: GCSStorageService) -> Dict[str, List[Dict]]:
    """
    Find duplicate episodes based ONLY on summary content.
    
    Args:
        episodes: List of episode dictionaries from Firestore
        gcs_service: GCSStorageService for downloading summary content
        
    Returns:
        Dictionary mapping duplicate key to list of duplicate episodes
    """
    # Group by summary content hash
    by_summary_hash = defaultdict(list)
    
    print("Downloading summaries for comparison...")
    for i, episode in enumerate(episodes, 1):
        if i % 10 == 0:
            print(f"  Processed {i}/{len(episodes)} episodes...")
        
        summary_url = episode.get('summary_url')
        if summary_url:
            try:
                summary_text = gcs_service.download_text_by_gcs_url(summary_url)
                if summary_text:
                    summary_hash = get_content_hash(summary_text)
                    if summary_hash:
                        by_summary_hash[summary_hash].append(episode)
            except Exception:
                # Skip episodes without summaries or download errors
                continue
    
    print(f"  ✓ Processed all {len(episodes)} episodes\n")
    
    # Find duplicates (groups with more than 1 episode)
    duplicates = {}
    
    # Check summary content duplicates
    for summary_hash, group in by_summary_hash.items():
        if len(group) > 1:
            key = f"CONTENT:SUMMARY:{summary_hash}"
            duplicates[key] = group
    
    return duplicates


def format_episode_info(episode: Dict, summary_preview: Optional[str] = None) -> str:
    """
    Format episode information for display.
    
    Args:
        episode: Episode dictionary
        summary_preview: Optional first line of summary to display
    """
    episode_id = episode.get('id', 'N/A')
    podcast_name = episode.get('podcast_name', 'N/A')
    episode_title = episode.get('episode_title', 'N/A')
    episode_number = episode.get('episode_number')
    created_time = episode.get('created_time')
    
    info = f"  ID: {episode_id}\n"
    info += f"  Podcast: {podcast_name}\n"
    info += f"  Title: {episode_title}\n"
    if episode_number is not None:
        info += f"  Episode #: {episode_number}\n"
    if created_time:
        info += f"  Created: {created_time}\n"
    
    # Show which URLs are present
    urls = []
    if episode.get('mp3_url'):
        urls.append('MP3')
    if episode.get('transcript_url'):
        urls.append('Transcript')
    if episode.get('summary_url'):
        urls.append('Summary')
    if episode.get('summary_image_url'):
        urls.append('Image')
    
    info += f"  Files: {', '.join(urls) if urls else 'None'}\n"
    
    # Show summary preview if available
    if summary_preview:
        # Get first line (or first 100 chars if no newline)
        first_line = summary_preview.split('\n')[0].strip()
        if len(first_line) > 100:
            first_line = first_line[:100] + "..."
        info += f"  Summary preview: {first_line}\n"
    
    return info


def delete_episode_files(gcs_service: GCSStorageService, episode: Dict) -> bool:
    """
    Delete all files for an episode from GCS.
    
    Args:
        gcs_service: GCSStorageService instance
        episode: Episode dictionary with GCS URLs
        
    Returns:
        True if all files deleted successfully, False otherwise
    """
    episode_id = episode.get('id')
    if not episode_id:
        print("  ⚠ Warning: No episode ID, cannot delete files")
        return False
    
    urls_to_delete = [
        ('mp3_url', 'mp3'),
        ('transcript_url', 'transcripts'),
        ('summary_url', 'summaries'),
        ('summary_image_url', 'images'),
    ]
    
    deleted_count = 0
    error_count = 0
    
    for url_field, file_type in urls_to_delete:
        gcs_url = episode.get(url_field)
        if not gcs_url:
            continue
        
        try:
            # Parse GCS URL to get blob path
            blob_path = parse_gcs_url(gcs_url)
            if not blob_path:
                print(f"  ⚠ Warning: Invalid GCS URL format: {gcs_url}")
                error_count += 1
                continue
            
            # Delete blob
            blob = gcs_service.bucket.blob(blob_path)
            if blob.exists():
                blob.delete()
                print(f"  ✓ Deleted {file_type}: {blob_path}")
                deleted_count += 1
            else:
                print(f"  ⚠ Warning: File not found in GCS: {blob_path}")
        except Exception as e:
            print(f"  ✗ Error deleting {file_type} ({gcs_url}): {e}")
            error_count += 1
    
    return error_count == 0


def main():
    """Main function to find and remove duplicates."""
    print("=" * 80)
    print("Duplicate Episode Finder and Remover")
    print("=" * 80)
    print()
    
    # Initialize services
    try:
        print("Initializing services...")
        firestore_service = FirestoreService()
        gcs_service = GCSStorageService()
        print("✓ Services initialized\n")
    except Exception as e:
        print(f"✗ Error initializing services: {e}")
        sys.exit(1)
    
    # Fetch all episodes
    print("Fetching all episodes from Firestore...")
    try:
        episodes = firestore_service.get_all_documents('episodes')
        print(f"✓ Found {len(episodes)} episode(s) in Firestore\n")
    except Exception as e:
        print(f"✗ Error fetching episodes: {e}")
        sys.exit(1)
    
    if not episodes:
        print("No episodes found. Exiting.")
        sys.exit(0)
    
    # Find duplicates
    print("Analyzing episodes for duplicates based on summary content...")
    print("(This may take a while - downloading summaries from GCS)\n")
    
    duplicates = find_duplicates(episodes, gcs_service)
    
    if not duplicates:
        print("✓ No duplicates found! All episodes are unique.\n")
        sys.exit(0)
    
    print(f"⚠ Found {len(duplicates)} duplicate group(s)\n")
    
    # Process each duplicate group
    total_deleted = 0
    total_kept = 0
    
    for dup_key, dup_group in duplicates.items():
        print("=" * 80)
        # Format the duplicate key for display
        if dup_key.startswith("CONTENT:SUMMARY:"):
            hash_part = dup_key.replace("CONTENT:SUMMARY:", "")
            print(f"Duplicate Summary Content (hash: {hash_part})")
        else:
            print(f"Duplicate Group: {dup_key}")
        print("=" * 80)
        print(f"\nFound {len(dup_group)} duplicate episode(s):\n")
        
        # Download summaries for display
        print("Loading summary previews...")
        episode_summaries = {}
        for episode in dup_group:
            summary_url = episode.get('summary_url')
            if summary_url:
                try:
                    summary_text = gcs_service.download_text_by_gcs_url(summary_url)
                    episode_summaries[episode.get('id')] = summary_text
                except Exception as e:
                    print(f"  ⚠ Warning: Could not load summary for {episode.get('id')}: {e}")
                    episode_summaries[episode.get('id')] = None
            else:
                episode_summaries[episode.get('id')] = None
        
        # Display all duplicates with summary previews
        for i, episode in enumerate(dup_group, 1):
            episode_id = episode.get('id')
            summary_preview = episode_summaries.get(episode_id)
            print(f"[{i}]")
            print(format_episode_info(episode, summary_preview=summary_preview))
            print()
        
        # Ask user which one to keep
        while True:
            try:
                response = input(
                    f"Which episode should be KEPT? (1-{len(dup_group)}) "
                    f"or 'a' to keep newest (delete all others), "
                    f"'d' to delete ALL (keep none), "
                    f"'s' to skip this group, or 'q' to quit: "
                ).strip().lower()
                
                if response == 'q':
                    print("\nExiting...")
                    sys.exit(0)
                
                if response == 's':
                    print("Skipping this group...\n")
                    break
                
                # Delete all: delete all duplicates, keep none
                if response == 'd':
                    print(f"\n⚠ WARNING: This will delete ALL {len(dup_group)} episodes in this duplicate group!")
                    print("  No episodes will be kept.\n")
                    
                    # Confirm deletion
                    confirm = input("Confirm deletion of ALL episodes? (yes/no): ").strip().lower()
                    if confirm not in ['yes', 'y']:
                        print("Deletion cancelled.\n")
                        break
                    
                    # Delete all duplicates
                    for episode in dup_group:
                        episode_id = episode.get('id')
                        print(f"\nDeleting episode: {episode_id}")
                        
                        # Delete from GCS
                        print("  Deleting files from GCS...")
                        delete_episode_files(gcs_service, episode)
                        
                        # Delete from Firestore
                        print("  Deleting from Firestore...")
                        try:
                            firestore_service.delete_document('episodes', episode_id)
                            print(f"  ✓ Deleted from Firestore: {episode_id}")
                            total_deleted += 1
                        except Exception as e:
                            print(f"  ✗ Error deleting from Firestore: {e}")
                    
                    print(f"\n✓ Completed. Deleted all {len(dup_group)} episodes.\n")
                    break
                
                # Auto-select: keep newest (delete all others)
                if response == 'a':
                    # Sort by created_time (newest first)
                    sorted_group = sorted(
                        dup_group,
                        key=lambda e: e.get('created_time', ''),
                        reverse=True
                    )
                    episode_to_keep = sorted_group[0]
                    episodes_to_delete = sorted_group[1:]
                    
                    print(f"\n✓ Auto-selected newest episode: {episode_to_keep.get('id')}")
                    print(f"  Created: {episode_to_keep.get('created_time', 'N/A')}")
                    print(f"  Will delete {len(episodes_to_delete)} duplicate(s)\n")
                    
                    # Confirm deletion
                    confirm = input("Confirm deletion? (yes/no): ").strip().lower()
                    if confirm not in ['yes', 'y']:
                        print("Deletion cancelled.\n")
                        break
                    
                    # Delete duplicates
                    for episode in episodes_to_delete:
                        episode_id = episode.get('id')
                        print(f"\nDeleting episode: {episode_id}")
                        
                        # Delete from GCS
                        print("  Deleting files from GCS...")
                        delete_episode_files(gcs_service, episode)
                        
                        # Delete from Firestore
                        print("  Deleting from Firestore...")
                        try:
                            firestore_service.delete_document('episodes', episode_id)
                            print(f"  ✓ Deleted from Firestore: {episode_id}")
                            total_deleted += 1
                        except Exception as e:
                            print(f"  ✗ Error deleting from Firestore: {e}")
                    
                    total_kept += 1
                    print(f"\n✓ Completed. Kept 1, deleted {len(episodes_to_delete)}.\n")
                    break
                
                # Manual selection
                keep_index = int(response) - 1
                if 0 <= keep_index < len(dup_group):
                    episode_to_keep = dup_group[keep_index]
                    episodes_to_delete = [
                        ep for i, ep in enumerate(dup_group) if i != keep_index
                    ]
                    
                    print(f"\n✓ Keeping episode: {episode_to_keep.get('id')}")
                    print(f"  Will delete {len(episodes_to_delete)} duplicate(s)\n")
                    
                    # Confirm deletion
                    confirm = input("Confirm deletion? (yes/no): ").strip().lower()
                    if confirm not in ['yes', 'y']:
                        print("Deletion cancelled.\n")
                        break
                    
                    # Delete duplicates
                    for episode in episodes_to_delete:
                        episode_id = episode.get('id')
                        print(f"\nDeleting episode: {episode_id}")
                        
                        # Delete from GCS
                        print("  Deleting files from GCS...")
                        delete_episode_files(gcs_service, episode)
                        
                        # Delete from Firestore
                        print("  Deleting from Firestore...")
                        try:
                            firestore_service.delete_document('episodes', episode_id)
                            print(f"  ✓ Deleted from Firestore: {episode_id}")
                            total_deleted += 1
                        except Exception as e:
                            print(f"  ✗ Error deleting from Firestore: {e}")
                    
                    total_kept += 1
                    print(f"\n✓ Completed. Kept 1, deleted {len(episodes_to_delete)}.\n")
                    break
                else:
                    print(f"Invalid choice. Please enter a number between 1 and {len(dup_group)}, 'a' for auto-select, 'd' to delete all, 's' to skip, or 'q' to quit.")
            except ValueError:
                print("Invalid input. Please enter a number, 'a' for auto-select, 'd' to delete all, 's' to skip, or 'q' to quit.")
            except KeyboardInterrupt:
                print("\n\nInterrupted by user. Exiting...")
                sys.exit(0)
    
    # Summary
    print("=" * 80)
    print("Summary")
    print("=" * 80)
    print(f"Total duplicate groups processed: {len(duplicates)}")
    print(f"Episodes kept: {total_kept}")
    print(f"Episodes deleted: {total_deleted}")
    print()
    print("✓ Done!")


if __name__ == "__main__":
    main()

