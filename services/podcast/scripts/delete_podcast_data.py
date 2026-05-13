#!/usr/bin/env python3
"""
Script to delete all Firestore and GCS data for specific podcasts

This script will:
1. List all episodes for the specified podcasts
2. Show a summary of what will be deleted
3. Ask for confirmation
4. Delete all GCS files for those episodes
5. Delete all Firestore documents for those episodes

Usage:
    python scripts/delete_podcast_data.py

Safety Features:
- Dry-run mode by default (use --execute to actually delete)
- Shows summary before deletion
- Requires explicit confirmation
- Lists all files that will be deleted
"""

import argparse
import hashlib
import sys
from pathlib import Path
from typing import Dict, List, Optional

# Add parent directory to path to import modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.service.gcs_storage_service import GCSStorageService
from src.service.upload_to_firebase import FirebaseService


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


def get_podcast_hash(podcast_name: str) -> str:
    """Get 12-character hash for podcast name."""
    return hashlib.sha256(podcast_name.encode('utf-8')).hexdigest()[:12]


def list_all_gcs_files_for_podcast(
    gcs_service: GCSStorageService,
    podcast_name: str
) -> Dict[str, List[str]]:
    """
    List all GCS files for a podcast by scanning the bucket.
    
    Args:
        gcs_service: GCSStorageService instance
        podcast_name: Name of the podcast
        
    Returns:
        Dictionary mapping file_type -> list of blob paths
    """
    podcast_hash = get_podcast_hash(podcast_name)
    base_path = gcs_service.base_path.strip('/') if gcs_service.base_path else ''
    
    file_types = [
        'mp3', 'transcripts', 'summaries', 'images', 'presentations',
        'marp', 'ticker_recommendations', 'ticker_marp', 'events', 'sentences'
    ]
    
    files_by_type = {}
    
    for file_type in file_types:
        # Build prefix to search for
        if base_path:
            prefix = f"{base_path}/{file_type}/{podcast_hash}/"
        else:
            prefix = f"{file_type}/{podcast_hash}/"
        
        # List all blobs with this prefix
        blobs = list(gcs_service.bucket.list_blobs(prefix=prefix))
        files_by_type[file_type] = [blob.name for blob in blobs]
    
    return files_by_type


def delete_episode_files_from_gcs(
    gcs_service: GCSStorageService,
    episode: Dict,
    dry_run: bool = True
) -> Dict[str, bool]:
    """
    Delete all GCS files for an episode.
    
    Args:
        gcs_service: GCSStorageService instance
        episode: Episode dictionary with GCS URLs
        dry_run: If True, only show what would be deleted
        
    Returns:
        Dictionary with deletion status for each file type
    """
    episode.get('id', 'unknown')
    results = {
        'mp3': False,
        'transcript': False,
        'summary': False,
        'image': False,
        'pptx': False,
        'marp': False,
        'ticker_recommendations': False,
        'ticker_marp': False,
        'events': False,
        'sentences': False
    }
    
    # Map of URL field names to result keys
    url_fields = {
        'mp3_url': 'mp3',
        'transcript_url': 'transcript',
        'summary_url': 'summary',
        'summary_image_url': 'image',
        'pptx_url': 'pptx',
        'marp_markdown_url': 'marp',
        'ticker_recommendations_url': 'ticker_recommendations',
        'ticker_marp_markdown_url': 'ticker_marp',
        'events_markdown_url': 'events',
        'sentences_markdown_url': 'sentences'
    }
    
    for url_field, result_key in url_fields.items():
        gcs_url = episode.get(url_field)
        if not gcs_url:
            continue
        
        try:
            blob_path = parse_gcs_url(gcs_url)
            if not blob_path:
                continue
            
            blob = gcs_service.bucket.blob(blob_path)
            
            if dry_run:
                if blob.exists():
                    print(f"    [DRY RUN] Would delete {result_key}: {blob_path}")
                    results[result_key] = True
                else:
                    print(f"    [DRY RUN] File not found: {blob_path}")
            else:
                if blob.exists():
                    blob.delete()
                    print(f"    ✓ Deleted {result_key}: {blob_path}")
                    results[result_key] = True
                else:
                    print(f"    ⚠ File not found: {blob_path}")
        except Exception as e:
            print(f"    ✗ Error deleting {result_key} ({gcs_url}): {e}")
    
    return results


def delete_podcast_data(
    podcast_names: List[str],
    dry_run: bool = True,
    auto_confirm: bool = False
) -> None:
    """
    Delete all data for specified podcasts from Firestore and GCS.
    
    Args:
        podcast_names: List of podcast names to delete
        dry_run: If True, only show what would be deleted
        auto_confirm: If True, skip confirmation prompt
    """
    print("="*80)
    print("Delete Podcast Data")
    print("="*80)
    
    if dry_run:
        print("\n⚠ DRY RUN MODE - No data will be deleted")
        print("   Use --execute to actually delete data\n")
    else:
        print("\n⚠ DELETION MODE - Data will be permanently deleted\n")
    
    # Initialize services
    print("Initializing services...")
    try:
        firebase_service = FirebaseService()
        gcs_service = GCSStorageService()
        print("✓ Services initialized\n")
    except Exception as e:
        print(f"✗ Error initializing services: {e}")
        sys.exit(1)
    
    total_episodes = 0
    total_gcs_files = 0
    all_episodes = {}
    
    # Collect all episodes and GCS files for each podcast
    for podcast_name in podcast_names:
        print(f"\n{'='*80}")
        print(f"Podcast: {podcast_name}")
        print(f"{'='*80}")
        
        # Get episodes from Firestore
        try:
            # Try with ordering first, but fall back to unordered query if index is missing
            try:
                episodes = firebase_service.get_podcast_episodes(
                    podcast_name=podcast_name,
                    limit=None,
                    order_by="created_time",
                    descending=True
                )
            except Exception as index_error:
                if "index" in str(index_error).lower() or "400" in str(index_error):
                    # Index missing - use FirestoreService to query without ordering
                    print("  ⚠ Index missing, querying without ordering...")
                    from src.service.firestore_service import FirestoreService
                    firestore_service = FirestoreService()
                    episodes = firestore_service.query_collection(
                        collection="episodes",
                        filters=[("podcast_name", "==", podcast_name)],
                        order_by=None,  # No ordering to avoid index requirement
                        limit=None
                    )
                    # Sort by created_time in Python
                    episodes.sort(
                        key=lambda x: x.get('created_time', '') or '',
                        reverse=True
                    )
                else:
                    raise
            
            print(f"\nFound {len(episodes)} episodes in Firestore")
            all_episodes[podcast_name] = episodes
            total_episodes += len(episodes)
            
            if episodes:
                print("\nFirst 5 episodes:")
                for i, episode in enumerate(episodes[:5], 1):
                    print(f"  {i}. {episode.get('episode_title', 'Unknown')} (ID: {episode.get('id', 'Unknown')})")
            
        except Exception as e:
            print(f"✗ Error fetching episodes: {e}")
            continue
        
        # List GCS files
        try:
            print("\nScanning GCS for files...")
            gcs_files = list_all_gcs_files_for_podcast(gcs_service, podcast_name)
            
            podcast_file_count = sum(len(files) for files in gcs_files.values())
            total_gcs_files += podcast_file_count
            
            print(f"Found {podcast_file_count} files in GCS:")
            for file_type, files in gcs_files.items():
                if files:
                    print(f"  {file_type}: {len(files)} files")
            
        except Exception as e:
            print(f"✗ Error scanning GCS: {e}")
    
    # Summary
    print(f"\n{'='*80}")
    print("SUMMARY")
    print(f"{'='*80}")
    print(f"Podcasts to delete: {', '.join(podcast_names)}")
    print(f"Total episodes: {total_episodes}")
    print(f"Total GCS files: {total_gcs_files}")
    print(f"{'='*80}")
    
    if total_episodes == 0 and total_gcs_files == 0:
        print("\n✓ No data found to delete. Exiting.")
        return
    
    # Confirmation
    if not auto_confirm:
        if dry_run:
            print("\nThis is a DRY RUN. No data will be deleted.")
            print("To actually delete, run with --execute flag.")
        else:
            print("\n⚠ WARNING: This will PERMANENTLY DELETE:")
            print(f"  - {total_episodes} Firestore documents")
            print(f"  - ALL {total_gcs_files} GCS files (including orphaned files not in Firestore)")
            print("\nThis action CANNOT be undone!")
            
            response = input("\nType 'DELETE' to confirm: ")
            if response != 'DELETE':
                print("\nDeletion cancelled.")
                return
    
    # Delete data
    if dry_run:
        print("\n" + "="*80)
        print("DRY RUN - Showing what would be deleted")
        print("="*80)
    else:
        print("\n" + "="*80)
        print("DELETING DATA")
        print("="*80)
    
    deleted_episodes = 0
    deleted_files = 0
    errors = []
    all_gcs_files_by_podcast = {}
    
    # First, collect all GCS files for each podcast
    for podcast_name in podcast_names:
        try:
            gcs_files = list_all_gcs_files_for_podcast(gcs_service, podcast_name)
            all_gcs_files_by_podcast[podcast_name] = gcs_files
        except Exception as e:
            print(f"  ⚠ Error collecting GCS files for {podcast_name}: {e}")
            all_gcs_files_by_podcast[podcast_name] = {}
    
    # Delete Firestore documents and referenced GCS files
    for podcast_name in podcast_names:
        episodes = all_episodes.get(podcast_name, [])
        gcs_files = all_gcs_files_by_podcast.get(podcast_name, {})
        
        print(f"\nProcessing: {podcast_name}")
        print(f"  Episodes in Firestore: {len(episodes)}")
        
        # Track which GCS files we delete from Firestore references
        deleted_file_paths = set()
        
        # Delete Firestore documents and their referenced GCS files
        if episodes:
            for i, episode in enumerate(episodes, 1):
                episode_id = episode.get('id', 'unknown')
                episode_title = episode.get('episode_title', 'Unknown')
                
                print(f"\n  [{i}/{len(episodes)}] {episode_title}")
                print(f"      ID: {episode_id}")
                
                # Delete GCS files referenced in Firestore
                print("      Deleting GCS files from Firestore references...")
                file_results = delete_episode_files_from_gcs(
                    gcs_service,
                    episode,
                    dry_run=dry_run
                )
                
                # Track deleted files
                for url_field in ['mp3_url', 'transcript_url', 'summary_url', 'summary_image_url',
                                'pptx_url', 'marp_markdown_url', 'ticker_recommendations_url',
                                'ticker_marp_markdown_url', 'events_markdown_url', 'sentences_markdown_url']:
                    gcs_url = episode.get(url_field)
                    if gcs_url:
                        blob_path = parse_gcs_url(gcs_url)
                        if blob_path:
                            deleted_file_paths.add(blob_path)
                
                deleted_files += sum(1 for v in file_results.values() if v)
                
                # Delete Firestore document
                if not dry_run:
                    try:
                        firebase_service.db.collection("episodes").document(episode_id).delete()
                        print(f"      ✓ Deleted from Firestore: {episode_id}")
                        deleted_episodes += 1
                    except Exception as e:
                        error_msg = f"Error deleting Firestore document {episode_id}: {e}"
                        print(f"      ✗ {error_msg}")
                        errors.append(error_msg)
                else:
                    print(f"      [DRY RUN] Would delete from Firestore: {episode_id}")
                    deleted_episodes += 1
        else:
            print(f"  No episodes found in Firestore for {podcast_name}")
        
        # Delete any remaining orphaned GCS files (not referenced in Firestore)
        total_gcs_files = sum(len(files) for files in gcs_files.values())
        if total_gcs_files > 0:
            print(f"\n  Deleting ALL remaining GCS files ({total_gcs_files} files)...")
            orphaned_count = 0
            
            for file_type, file_paths in gcs_files.items():
                for file_path in file_paths:
                    if file_path not in deleted_file_paths:
                        # This file wasn't deleted yet, delete it now
                        try:
                            blob = gcs_service.bucket.blob(file_path)
                            if dry_run:
                                if blob.exists():
                                    print(f"    [DRY RUN] Would delete file: {file_path}")
                                    orphaned_count += 1
                            else:
                                if blob.exists():
                                    blob.delete()
                                    print(f"    ✓ Deleted file: {file_path}")
                                    orphaned_count += 1
                                    deleted_files += 1
                        except Exception as e:
                            error_msg = f"Error deleting file {file_path}: {e}"
                            print(f"    ✗ {error_msg}")
                            errors.append(error_msg)
            
            if orphaned_count > 0:
                print(f"  ✓ Deleted {orphaned_count} additional GCS files")
            else:
                print("  ✓ All GCS files already deleted")
        else:
            print("  ✓ No GCS files found")
    
    # Final summary
    print(f"\n{'='*80}")
    if dry_run:
        print("DRY RUN COMPLETE")
    else:
        print("DELETION COMPLETE")
    print(f"{'='*80}")
    print(f"Episodes processed: {deleted_episodes}")
    print(f"GCS files processed: {deleted_files}")
    
    if errors:
        print(f"\n⚠ Errors encountered: {len(errors)}")
        for error in errors[:10]:  # Show first 10 errors
            print(f"  - {error}")
        if len(errors) > 10:
            print(f"  ... and {len(errors) - 10} more errors")
    
    if dry_run:
        print("\n⚠ This was a DRY RUN. No data was actually deleted.")
        print("   Run with --execute to perform the deletion.")
    else:
        print("\n✓ Deletion completed.")


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Delete all Firestore and GCS data for specific podcasts",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run (default) - shows what would be deleted
'  python scripts/delete_podcast_data.py --podcaster "Planet Money"
  
  # Actually delete the data
  python scripts/delete_podcast_data.py --podcaster "Planet Money" --execute
  
  # Delete multiple podcasts (using --podcasts for backward compatibility)
  python scripts/delete_podcast_data.py --podcasts "Planet Money" "Optimal Finance Daily" --execute
        """
    )
    
    parser.add_argument(
        '--podcaster',
        type=str,
        help='Single podcast name to delete (e.g., "Planet Money")'
    )
    
    parser.add_argument(
        '--podcasts',
        nargs='+',
        help='Podcast names to delete (for multiple podcasts, backward compatibility)'
    )
    
    parser.add_argument(
        '--execute',
        action='store_true',
        help='Actually delete data (default is dry-run mode)'
    )
    
    parser.add_argument(
        '--yes',
        action='store_true',
        help='Skip confirmation prompt (use with caution!)'
    )
    
    args = parser.parse_args()
    
    # Determine which podcasts to delete
    if args.podcaster:
        # Single podcast specified
        podcast_names = [args.podcaster]
    elif args.podcasts:
        # Multiple podcasts specified (backward compatibility)
        podcast_names = args.podcasts
    else:
        # Default: both podcasts
        podcast_names = ["Planet Money", "Optimal Finance Daily"]
    
    delete_podcast_data(
        podcast_names=podcast_names,
        dry_run=not args.execute,
        auto_confirm=args.yes
    )


if __name__ == "__main__":
    main()
