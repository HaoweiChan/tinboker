#!/usr/bin/env python3
"""
Podcast Downloader Script

This script reads a JSON file with podcast information and downloads all episodes.
"""

import json
import re
import sys
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Optional

import requests


def extract_podcast_id(url: str) -> str:
    """Extract podcast ID from podcasttomp3.com URL."""
    # Pattern: https://podcasttomp3.com/podcasts/v2/{id}
    match = re.search(r'/podcasts/v2/(\d+)', url)
    if match:
        podcast_id = match.group(1)
        if podcast_id and podcast_id.strip():
            return podcast_id
    raise ValueError(f"Could not extract valid podcast ID from URL: {url}")


def fetch_episodes(podcast_id: str) -> List[Dict]:
    """Fetch all episodes for a podcast from the API."""
    api_url = f"https://podcasttomp3.com/api/episodes?id={podcast_id}"
    
    try:
        response = requests.get(api_url, timeout=30)
        response.raise_for_status()
        episodes = response.json()
        return episodes
    except requests.exceptions.RequestException as e:
        print(f"Error fetching episodes: {e}")
        return []


def sanitize_filename(filename: str) -> str:
    """Sanitize filename to remove invalid characters."""
    # Remove or replace invalid characters for filenames
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, '_')
    # Remove leading/trailing spaces and dots
    filename = filename.strip(' .')
    # Limit length
    if len(filename) > 200:
        filename = filename[:200]
    return filename


def download_file(url: str, filepath: Path, episode_title: str, max_retries: int = 3, check_existing: bool = True) -> bool:
    """
    Download a file from URL to filepath.
    
    Args:
        url: URL to download from
        filepath: Path where file should be saved
        episode_title: Episode title for logging
        max_retries: Maximum number of retry attempts
        check_existing: If True, check if file already exists and skip download
        
    Returns:
        True if download successful or file already exists, False otherwise
    """
    # Check if file already exists and has reasonable size (> 1MB for podcasts)
    if check_existing and filepath.exists():
        file_size = filepath.stat().st_size
        # Podcasts are typically > 1MB, so use that as threshold
        if file_size > 1024 * 1024:  # More than 1MB, assume it's a valid download
            print(f"  ✓ Already exists: {filepath.name} ({file_size / 1024 / 1024:.1f} MB)")
            return True
        else:
            # File exists but is too small, might be corrupted or incomplete
            print(f"  ⚠ File exists but is too small ({file_size / 1024:.1f} KB), re-downloading...")
            filepath.unlink()  # Delete the small file
    
    # Create parent directory if it doesn't exist
    filepath.parent.mkdir(parents=True, exist_ok=True)
    
    for attempt in range(max_retries):
        try:
            if attempt > 0:
                print(f"  ↻ Retry attempt {attempt + 1}/{max_retries}...")
            else:
                print(f"  ↓ Downloading: {filepath.name}")
            
            # Download with streaming for large files, allow redirects
            response = requests.get(url, stream=True, timeout=120, allow_redirects=True)
            response.raise_for_status()
            
            # Get file size if available
            total_size = int(response.headers.get('content-length', 0))
            
            # Write file in chunks
            downloaded = 0
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            percent = (downloaded / total_size) * 100
                            print(f"\r    Progress: {percent:.1f}% ({downloaded / 1024 / 1024:.1f} MB)", end='', flush=True)
            
            print()  # New line after progress
            
            # Verify download completed - check if file size matches expected size
            final_size = filepath.stat().st_size
            if total_size > 0 and abs(final_size - total_size) > 1024:  # Allow 1KB difference
                print(f"  ⚠ Warning: File size mismatch (expected {total_size / 1024 / 1024:.1f} MB, got {final_size / 1024 / 1024:.1f} MB)")
                if attempt < max_retries - 1:
                    filepath.unlink()
                    continue
                else:
                    print(f"  ✗ Download incomplete after {max_retries} attempts")
                    return False
            
            # Also check if file is suspiciously small (< 1MB for a podcast)
            if final_size < 1024 * 1024:
                print(f"  ⚠ Warning: File is very small ({final_size / 1024:.1f} KB), might be incomplete")
                if attempt < max_retries - 1:
                    filepath.unlink()
                    continue
            
            print(f"  ✓ Downloaded: {filepath.name} ({final_size / 1024 / 1024:.1f} MB)")
            return True
        
        except requests.exceptions.RequestException as e:
            print(f"  ✗ Error downloading {episode_title}: {e}")
            if filepath.exists():
                filepath.unlink()  # Remove partial file
            if attempt < max_retries - 1:
                time.sleep(2)  # Wait before retry
                continue
            return False
        except Exception as e:
            print(f"  ✗ Unexpected error: {e}")
            if filepath.exists():
                filepath.unlink()  # Remove partial file
            if attempt < max_retries - 1:
                time.sleep(2)  # Wait before retry
                continue
            return False
    
    return False


def download_file_to_temp(url: str, episode_title: str, temp_dir: Optional[Path] = None, max_retries: int = 3) -> Optional[Path]:
    """
    Download a file from URL to a temporary file.
    
    Args:
        url: URL to download from
        episode_title: Episode title for logging
        temp_dir: Optional directory for temp file (uses system temp if None)
        max_retries: Maximum number of retry attempts
        
    Returns:
        Path to temporary file if successful, None otherwise
        Caller is responsible for deleting the temp file
    """
    if temp_dir:
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_file = tempfile.NamedTemporaryFile(
            dir=temp_dir,
            suffix='.mp3',
            delete=False
        )
    else:
        temp_file = tempfile.NamedTemporaryFile(
            suffix='.mp3',
            delete=False
        )
    
    temp_path = Path(temp_file.name)
    temp_file.close()
    
    try:
        success = download_file(url, temp_path, episode_title, max_retries, check_existing=False)
        if success:
            return temp_path
        else:
            # Clean up failed download
            if temp_path.exists():
                temp_path.unlink()
            return None
    except Exception:
        # Clean up on error
        if temp_path.exists():
            temp_path.unlink()
        raise


def download_podcast(name: str, link: str, base_dir: Path = Path("./data/downloads"), limit: int = None) -> None:
    """Download all episodes for a podcast.
    
    Args:
        name: Podcast name
        link: Podcast URL
        base_dir: Base directory for downloads
        limit: Optional limit on number of episodes to download (None = no limit)
    """
    print(f"\n{'='*60}")
    print(f"Processing: {name}")
    print(f"URL: {link}")
    if limit:
        print(f"Limit: {limit} episodes")
    print(f"{'='*60}")
    
    # Extract podcast ID
    try:
        podcast_id = extract_podcast_id(link)
        if not podcast_id or podcast_id.strip() == '':
            print(f"✗ Error: Invalid podcast ID extracted from URL: {link}")
            return
        print(f"Podcast ID: {podcast_id}")
    except ValueError as e:
        print(f"✗ Error: {e}")
        return
    
    # Fetch episodes
    print("Fetching episode list...")
    episodes = fetch_episodes(podcast_id)
    
    if not episodes:
        print("✗ No episodes found or error fetching episodes")
        return
    
    print(f"Found {len(episodes)} episodes")
    
    # Apply limit if specified
    if limit and limit > 0:
        episodes = episodes[:limit]
        print(f"Limited to {len(episodes)} episodes")
    
    # Create download directory
    download_dir = base_dir / sanitize_filename(name)
    download_dir.mkdir(parents=True, exist_ok=True)
    print(f"Download directory: {download_dir}")
    
    # Download each episode
    successful = 0
    failed = 0
    
    for i, episode in enumerate(episodes, 1):
        episode_title = episode.get('title', f'Episode {i}')
        episode_url = episode.get('episodeUrl')
        episode_number = episode.get('episodeNumber')
        
        # Handle None or missing episode number
        if episode_number is None:
            episode_number = i
        
        if not episode_url:
            print(f"  ✗ Episode {i}: No download URL found")
            failed += 1
            continue
        
        # Create filename
        safe_title = sanitize_filename(episode_title)
        filename = f"{episode_number:04d}_{safe_title}.mp3"
        filepath = download_dir / filename
        
        print(f"\n[{i}/{len(episodes)}] {episode_title}")
        
        if download_file(episode_url, filepath, episode_title):
            successful += 1
        else:
            failed += 1
    
    # Summary
    print(f"\n{'='*60}")
    print(f"Download Summary for {name}:")
    print(f"  Successful: {successful}")
    print(f"  Failed: {failed}")
    print(f"  Total: {len(episodes)}")
    print(f"{'='*60}\n")


def main():
    """Main function."""
    # Check for JSON file argument
    if len(sys.argv) < 2:
        print("Usage: python download_podcasts.py <podcasts.json>")
        print("\nExample podcasts.json:")
        print(json.dumps([
            {
                "name": "Gooaye 股癌",
                "link": "https://podcasttomp3.com/podcasts/v2/358931",
                "limit": 10
            }
        ], indent=2))
        sys.exit(1)
    
    json_file = Path(sys.argv[1])
    
    if not json_file.exists():
        print(f"Error: File not found: {json_file}")
        sys.exit(1)
    
    # Load JSON file
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            podcasts = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON file: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error reading file: {e}")
        sys.exit(1)
    
    # Validate structure
    if not isinstance(podcasts, list):
        print("Error: JSON file must contain a list of podcast objects")
        sys.exit(1)
    
    # Process each podcast
    for podcast in podcasts:
        if not isinstance(podcast, dict):
            print("Warning: Skipping invalid podcast entry (not an object)")
            continue
        
        name = podcast.get('name')
        link = podcast.get('link')
        limit = podcast.get('limit')  # Optional limit
        
        if not name or not link:
            print("Warning: Skipping podcast entry (missing 'name' or 'link')")
            continue
        
        # Validate limit if provided
        if limit is not None:
            try:
                limit = int(limit)
                if limit <= 0:
                    print(f"Warning: Invalid limit ({limit}) for {name}, ignoring limit")
                    limit = None
            except (ValueError, TypeError):
                print(f"Warning: Invalid limit value for {name}, ignoring limit")
                limit = None
        
        download_podcast(name, link, limit=limit)
    
    print("\n" + "="*60)
    print("All downloads completed!")
    print("="*60)


if __name__ == "__main__":
    main()

