#!/usr/bin/env python3
"""
Script to access all Firestore and GCS data for Planet Money and Optimal Finance Daily

Usage:
    python scripts/access_podcast_data.py

This script demonstrates how to:
1. Query Firestore for episodes by podcast name
2. Access episode metadata
3. Download files from GCS using the URLs stored in Firestore
"""

import sys
from pathlib import Path

# Add parent directory to path to import modules
sys.path.insert(0, str(Path(__file__).parent.parent))

import json
from typing import Dict, List

from src.service.gcs_storage_service import GCSStorageService
from src.service.upload_to_firebase import FirebaseService


def get_podcast_episodes(podcast_name: str) -> List[Dict]:
    """
    Get all episodes for a podcast from Firestore.
    
    Args:
        podcast_name: Name of the podcast (e.g., "Planet Money")
        
    Returns:
        List of episode dictionaries
    """
    firebase_service = FirebaseService()
    episodes = firebase_service.get_podcast_episodes(
        podcast_name=podcast_name,
        limit=None,  # Get all episodes
        order_by="created_time",
        descending=True  # Newest first
    )
    return episodes


def download_episode_files(
    episode: Dict,
    gcs_service: GCSStorageService,
    output_dir: Path,
    download_mp3: bool = False
) -> Dict[str, bool]:
    """
    Download all files for an episode from GCS.
    
    Args:
        episode: Episode dictionary from Firestore
        gcs_service: GCSStorageService instance
        output_dir: Directory to save files
        download_mp3: Whether to download MP3 files (can be large)
        
    Returns:
        Dictionary with download status for each file type
    """
    results = {
        'transcript': False,
        'summary': False,
        'svg': False,
        'mp3': False
    }
    
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
            results['transcript'] = True
            print(f"    ✓ Transcript ({len(transcript_data.get('text', ''))} chars)")
        except Exception as e:
            print(f"    ✗ Transcript failed: {e}")
    
    # Download summary
    if episode.get('summary_url'):
        try:
            summary_text = gcs_service.download_text_by_gcs_url(
                episode['summary_url']
            )
            summary_file = episode_dir / "summary.md"
            with open(summary_file, 'w', encoding='utf-8') as f:
                f.write(summary_text)
            results['summary'] = True
            print(f"    ✓ Summary ({len(summary_text)} chars)")
        except Exception as e:
            print(f"    ✗ Summary failed: {e}")
    
    # Download SVG image
    if episode.get('summary_image_url'):
        try:
            svg_content = gcs_service.download_text_by_gcs_url(
                episode['summary_image_url']
            )
            svg_file = episode_dir / "summary_image.svg"
            with open(svg_file, 'w', encoding='utf-8') as f:
                f.write(svg_content)
            results['svg'] = True
            print(f"    ✓ SVG image ({len(svg_content)} chars)")
        except Exception as e:
            print(f"    ✗ SVG failed: {e}")
    
    # Download MP3 (optional, can be large)
    if download_mp3 and episode.get('mp3_url'):
        try:
            mp3_file = episode_dir / "episode.mp3"
            gcs_service.download_file_by_gcs_url(
                episode['mp3_url'], mp3_file
            )
            results['mp3'] = True
            print("    ✓ MP3 audio")
        except Exception as e:
            print(f"    ✗ MP3 failed: {e}")
    
    return results


def print_episode_summary(episode: Dict):
    """Print a summary of an episode."""
    print(f"  Title: {episode.get('episode_title', 'Unknown')}")
    print(f"  ID: {episode.get('id', 'Unknown')}")
    print(f"  Episode #: {episode.get('episode_number', 'N/A')}")
    print(f"  Created: {episode.get('created_time', 'Unknown')}")
    print(f"  Tickers: {', '.join(episode.get('related_tickers', [])) or 'None'}")
    print("  URLs:")
    if episode.get('mp3_url'):
        print(f"    MP3: {episode['mp3_url']}")
    if episode.get('transcript_url'):
        print(f"    Transcript: {episode['transcript_url']}")
    if episode.get('summary_url'):
        print(f"    Summary: {episode['summary_url']}")
    if episode.get('summary_image_url'):
        print(f"    Image: {episode['summary_image_url']}")


def main():
    """Main function to access and display podcast data."""
    print("="*70)
    print("Accessing Firestore and GCS Data")
    print("="*70)
    
    # Initialize services
    print("\nInitializing services...")
    try:
        FirebaseService()
        gcs_service = GCSStorageService()
        print("✓ Services initialized")
    except Exception as e:
        print(f"✗ Failed to initialize services: {e}")
        print("\nMake sure you have:")
        print("  1. Set GCP_CREDENTIALS_PATH or GCP_CREDENTIALS_JSON in .env")
        print("  2. Set GCS_BUCKET_NAME in .env (if downloading files)")
        return
    
    podcasts = ["Planet Money", "Optimal Finance Daily"]
    
    for podcast_name in podcasts:
        print(f"\n{'='*70}")
        print(f"Podcast: {podcast_name}")
        print(f"{'='*70}")
        
        try:
            # Get all episodes from Firestore
            episodes = get_podcast_episodes(podcast_name)
            print(f"\nFound {len(episodes)} episodes")
            
            if not episodes:
                print(f"  No episodes found for '{podcast_name}'")
                print("  Make sure the podcast_name in Firestore matches exactly")
                continue
            
            # Display first 5 episodes
            print("\nFirst 5 episodes:")
            for i, episode in enumerate(episodes[:5], 1):
                print(f"\n  [{i}] {episode.get('episode_title', 'Unknown')}")
                print(f"      Created: {episode.get('created_time', 'Unknown')}")
                print(f"      Episode ID: {episode.get('id', 'Unknown')}")
            
            # Save metadata to JSON
            output_dir = Path(f"./output/{podcast_name.replace(' ', '_')}")
            output_dir.mkdir(parents=True, exist_ok=True)
            
            metadata_file = output_dir / "episodes_metadata.json"
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump(episodes, f, indent=2, default=str, ensure_ascii=False)
            print(f"\n✓ Saved metadata to: {metadata_file}")
            
            # Download files for first 3 episodes (as example)
            print("\nDownloading files for first 3 episodes (example)...")
            for i, episode in enumerate(episodes[:3], 1):
                print(f"\n  Episode {i}: {episode.get('episode_title', 'Unknown')}")
                download_episode_files(
                    episode,
                    gcs_service,
                    output_dir,
                    download_mp3=False  # Set to True to download MP3 files
                )
            
            print(f"\n✓ Completed processing {podcast_name}")
            print(f"  Output directory: {output_dir}")
            
        except Exception as e:
            print(f"✗ Error processing {podcast_name}: {e}")
            import traceback
            traceback.print_exc()
    
    print(f"\n{'='*70}")
    print("Done!")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
