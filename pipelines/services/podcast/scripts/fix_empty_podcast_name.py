#!/usr/bin/env python3
"""
Script to fix episodes with empty podcast_name field.

This script:
1. Finds all episodes with empty podcast_name
2. Attempts to identify the podcast from episode title/number
3. Updates the episode with the correct podcast_name

Usage:
    python scripts/fix_empty_podcast_name.py [--dry-run] [--interactive|-i]
    
Options:
    --dry-run        Show what would be changed without making changes
    --interactive    Prompt for manual podcast name input when auto-detection fails
    -i               Short form of --interactive
"""

import sys
from pathlib import Path
from typing import Dict, List, Optional

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.service.firestore_service import FirestoreService


def get_podcast_name_from_title(title: str, episode_number: Optional[int]) -> Optional[str]:
    """
    Try to identify podcast name from episode title or number.
    
    This is a heuristic - you may need to adjust based on your podcast naming patterns.
    """
    # Map of known patterns to podcast names
    # You can extend this based on your podcasts
    patterns = {
        '股癌': 'Gooaye 股癌',
        '財經皓角': '游庭皓的財經皓角',
        '財女': '財女Jenny',
        '珍妮': '財女Jenny',
        '早晨財經速解讀': '財經M平方',
        '財經時事放大鏡': '財經一路發',
        'After Meeting': 'Bloomberg Masters in Business Podcast',
        'Masters in Business': 'Bloomberg Masters in Business Podcast',
    }
    
    for pattern, podcast_name in patterns.items():
        if pattern in title:
            return podcast_name
    
    # Check for EP### format (typically Gooaye 股癌 for high numbers like 600+)
    if title.startswith('EP') and episode_number and episode_number >= 600:
        return 'Gooaye 股癌'
    
    # If we can't identify from title, return None
    return None


def match_episode_to_podcast(
    episode: Dict,
    all_episodes: List[Dict],
    podcasts_config: List[Dict]
) -> Optional[str]:
    """
    Try to match an episode to a podcast by comparing with episodes that have podcast_name set.
    
    Strategy:
    1. Find episodes with same episode_number and title pattern
    2. Use their podcast_name
    3. Or match by episode_number range/patterns
    """
    episode_number = episode.get('episode_number')
    episode_title = episode.get('episode_title', '')
    
    # Strategy 1: Find episodes with same episode_number that have podcast_name
    if episode_number:
        for other_ep in all_episodes:
            if (other_ep.get('episode_number') == episode_number and
                other_ep.get('podcast_name') and
                other_ep.get('id') != episode.get('id')):
                # Check if titles are similar (same podcast likely has similar title patterns)
                other_title = other_ep.get('episode_title', '')
                if episode_title.startswith('EP') and other_title.startswith('EP'):
                    return other_ep.get('podcast_name')
                # Also match if both have similar title structure
                if (episode_title.startswith('EP') == other_title.startswith('EP') or
                    ('早晨財經' in episode_title and '早晨財經' in other_title) or
                    ('財經時事' in episode_title and '財經時事' in other_title) or
                    ('After Meeting' in episode_title and 'After Meeting' in other_title)):
                    return other_ep.get('podcast_name')
    
    # Strategy 2: Match by title pattern similarity
    # Find episodes with similar title patterns that have podcast_name
    for other_ep in all_episodes:
        if (other_ep.get('podcast_name') and
            other_ep.get('id') != episode.get('id')):
            other_title = other_ep.get('episode_title', '')
            
            # Match EP### format
            if episode_title.startswith('EP') and other_title.startswith('EP'):
                # If episode numbers are close (within 10), likely same podcast
                if episode_number and other_ep.get('episode_number'):
                    if abs(episode_number - other_ep.get('episode_number')) <= 10:
                        return other_ep.get('podcast_name')
    
    return None


def find_episodes_with_empty_podcast_name(firestore_service: FirestoreService) -> tuple:
    """Find all episodes with empty podcast_name."""
    print("Searching for episodes with empty podcast_name...")
    
    all_episodes = firestore_service.get_all_documents('episodes')
    empty_podcast_episodes = []
    
    for episode in all_episodes:
        podcast_name = episode.get('podcast_name', '').strip()
        if not podcast_name:
            empty_podcast_episodes.append(episode)
    
    print(f"Found {len(empty_podcast_episodes)} episode(s) with empty podcast_name")
    return empty_podcast_episodes, all_episodes


def fix_episode_podcast_name(
    firestore_service: FirestoreService,
    episode: Dict,
    podcast_name: str,
    dry_run: bool = False
) -> bool:
    """Fix an episode's podcast_name."""
    episode_id = episode.get('id')
    episode_title = episode.get('episode_title', 'N/A')
    
    print(f"\nEpisode: {episode_id}")
    print(f"  Title: {episode_title}")
    print(f"  Current podcast_name: '{episode.get('podcast_name', '')}'")
    print(f"  New podcast_name: '{podcast_name}'")
    
    if dry_run:
        print("  [DRY RUN] Would update podcast_name")
        return True
    
    try:
        # Update the episode document using set_document with merge=True
        # This will update only the podcast_name field without overwriting other fields
        firestore_service.set_document('episodes', episode_id, {'podcast_name': podcast_name}, merge=True)
        print("  ✓ Updated podcast_name")
        return True
    except Exception as e:
        print(f"  ✗ Error updating: {e}")
        return False


def main():
    """Main function."""
    dry_run = '--dry-run' in sys.argv
    interactive = '--interactive' in sys.argv or '-i' in sys.argv
    
    if dry_run:
        print("🔍 DRY RUN MODE - No changes will be made\n")
    
    if interactive:
        print("🔧 INTERACTIVE MODE - You can manually input podcast names\n")
    
    try:
        firestore_service = FirestoreService()
    except Exception as e:
        print(f"✗ Error initializing Firestore service: {e}")
        sys.exit(1)
    
    # Load podcasts config for reference
    try:
        import json
        config_path = project_root / "podcasts_tw.json"
        with open(config_path, 'r', encoding='utf-8') as f:
            podcasts_config = json.load(f)
    except Exception as e:
        print(f"⚠ Warning: Could not load podcasts config: {e}")
        podcasts_config = []
    
    # Find episodes with empty podcast_name
    empty_episodes, all_episodes = find_episodes_with_empty_podcast_name(firestore_service)
    
    if not empty_episodes:
        print("✓ No episodes with empty podcast_name found")
        return
    
    # Try to fix each episode
    fixed_count = 0
    failed_count = 0
    skipped_count = 0
    
    # Get list of known podcast names for reference
    known_podcasts = [podcast.get('name') for podcast in podcasts_config if podcast.get('name')]
    if known_podcasts:
        print(f"\n📋 Known podcasts: {', '.join(known_podcasts)}")
    
    for episode in empty_episodes:
        episode_title = episode.get('episode_title', '')
        episode_number = episode.get('episode_number')
        episode_id = episode.get('id')
        
        # Try to identify podcast from title
        podcast_name = get_podcast_name_from_title(episode_title, episode_number)
        
        # If not found by title, try matching with other episodes
        if not podcast_name:
            podcast_name = match_episode_to_podcast(episode, all_episodes, podcasts_config)
        
        # If still not found and interactive mode, prompt user
        if not podcast_name:
            if interactive:
                print(f"\n{'='*80}")
                print("⚠ Could not automatically identify podcast for episode:")
                print(f"  ID: {episode_id}")
                print(f"  Title: {episode_title}")
                print(f"  Episode #: {episode_number}")
                print("\nOptions:")
                if known_podcasts:
                    print("  Known podcasts:")
                    for i, name in enumerate(known_podcasts, 1):
                        print(f"    {i}. {name}")
                print("  Enter podcast name manually, or 'skip' to skip this episode")
                
                while True:
                    user_input = input("\n  Podcast name (or 'skip'): ").strip()
                    
                    if user_input.lower() == 'skip':
                        print(f"  ⏭ Skipping episode {episode_id}")
                        skipped_count += 1
                        podcast_name = None
                        break
                    elif user_input:
                        podcast_name = user_input
                        print(f"  ✓ Using podcast name: {podcast_name}")
                        break
                    else:
                        print("  ⚠ Please enter a podcast name or 'skip'")
            else:
                print(f"\n⚠ Could not identify podcast for episode: {episode_id}")
                print(f"  Title: {episode_title}")
                print(f"  Episode #: {episode_number}")
                print("  Run with --interactive to manually set podcast_name")
                failed_count += 1
                continue
        
        if podcast_name:
            if fix_episode_podcast_name(firestore_service, episode, podcast_name, dry_run):
                fixed_count += 1
            else:
                failed_count += 1
        else:
            # This should only happen if user skipped in interactive mode
            continue
    
    print(f"\n{'='*80}")
    print("Summary:")
    print(f"  Fixed: {fixed_count}")
    print(f"  Failed/Unknown: {failed_count}")
    if skipped_count > 0:
        print(f"  Skipped: {skipped_count}")
    print(f"  Total: {len(empty_episodes)}")
    
    if dry_run:
        print("\n🔍 This was a DRY RUN - no changes were made")
        print("   Run without --dry-run to apply changes")
    
    if interactive:
        print("\n🔧 Interactive mode completed")


if __name__ == "__main__":
    main()

