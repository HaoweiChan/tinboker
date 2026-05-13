"""
Command-line interface for Spotify Podcast Parser.
"""

import argparse
import json
import os
import sys

from src.secrets_bootstrap import bootstrap

# Load secrets from GSM (idempotent — safe if already bootstrapped at entry point).
bootstrap()

from .auth import get_access_token  # noqa: E402
from .parser import SpotifyPodcastParser  # noqa: E402


def get_credentials():
    """
    Get credentials from environment variables.
    
    Returns:
        Tuple of (client_id, client_secret) or (None, None) if not found
    """
    client_id = os.getenv('SPOTIFY_ID') or os.getenv('SPOTIFY_CLIENT_ID')
    client_secret = (
        os.getenv('SPOTIFY_SECRET') or 
        os.getenv('SPOTIFY_SECRETE') or 
        os.getenv('SPOTIFY_CLIENT_SECRET')
    )
    return client_id, client_secret


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Fetch episode metadata from Spotify podcasts",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Using show URL with limit
  spotify-podcast "https://open.spotify.com/show/1zWxx5pKk0XBEzMupVC7UZ" --limit 10
  
  # Using show ID to get all episodes
  spotify-podcast 1zWxx5pKk0XBEzMupVC7UZ --all
  
  # Custom output file
  spotify-podcast 1zWxx5pKk0XBEzMupVC7UZ --limit 50 --output my_episodes.json
  
  # Override credentials
  spotify-podcast 1zWxx5pKk0XBEzMupVC7UZ --client-id YOUR_ID --client-secret YOUR_SECRET
        """
    )
    
    parser.add_argument(
        'show',
        help='Spotify show URL or show ID (e.g., https://open.spotify.com/show/1zWxx5pKk0XBEzMupVC7UZ or 1zWxx5pKk0XBEzMupVC7UZ)'
    )
    
    parser.add_argument(
        '--limit',
        type=int,
        default=50,
        help='Maximum number of episodes to fetch (default: 50, max: 50 per request)'
    )
    
    parser.add_argument(
        '--all',
        action='store_true',
        help='Fetch all episodes (overrides --limit)'
    )
    
    parser.add_argument(
        '--output',
        '-o',
        default='episodes.json',
        help='Output JSON file path (default: episodes.json)'
    )
    
    parser.add_argument(
        '--client-id',
        help='Spotify API client ID (overrides environment variables)'
    )
    
    parser.add_argument(
        '--client-secret',
        help='Spotify API client secret (overrides environment variables)'
    )
    
    args = parser.parse_args()
    
    # Get credentials
    client_id = args.client_id
    client_secret = args.client_secret
    
    if not client_id or not client_secret:
        env_client_id, env_client_secret = get_credentials()
        client_id = client_id or env_client_id
        client_secret = client_secret or env_client_secret
    
    if not client_id or not client_secret:
        print("Error: Spotify API credentials required.", file=sys.stderr)
        print("\nSet environment variables:", file=sys.stderr)
        print("  SPOTIFY_ID=your_client_id", file=sys.stderr)
        print("  SPOTIFY_SECRET=your_client_secret", file=sys.stderr)
        print("\nOr use --client-id and --client-secret flags", file=sys.stderr)
        print("\nGet credentials from: https://developer.spotify.com/dashboard", file=sys.stderr)
        sys.exit(1)
    
    # Get access token
    try:
        print("Authenticating with Spotify API...")
        access_token = get_access_token(client_id, client_secret)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Initialize parser
    podcast_parser = SpotifyPodcastParser(access_token=access_token)
    
    # Extract show ID
    show_id = podcast_parser.extract_show_id(args.show)
    if not show_id:
        print(f"Error: Invalid show URL or ID: {args.show}", file=sys.stderr)
        print("Expected format: https://open.spotify.com/show/ID or just the ID", file=sys.stderr)
        sys.exit(1)
    
    print(f"Show ID: {show_id}")
    
    # Get show info
    try:
        show_info = podcast_parser.get_show_info(show_id)
        if show_info:
            print(f"Show: {show_info.get('name', 'N/A')}")
            print(f"Publisher: {show_info.get('publisher', 'N/A')}")
    except ValueError as e:
        print(f"Warning: {e}", file=sys.stderr)
    
    # Get episodes
    print("\nFetching episodes...")
    try:
        if args.all:
            episodes = podcast_parser.get_all_episodes(show_id)
            print("Fetching all episodes...")
        else:
            result = podcast_parser.get_episodes(show_id, limit=args.limit, offset=0)
            episodes = result.get("items", []) if result else []
            total = result.get("total", len(episodes)) if result else len(episodes)
            print(f"Fetching {min(args.limit, total)} of {total} episodes...")
        
        if not episodes:
            print("No episodes found.", file=sys.stderr)
            sys.exit(1)
        
        # Save to JSON
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(episodes, f, indent=2, ensure_ascii=False)
        
        print(f"\n✓ Successfully fetched {len(episodes)} episodes")
        print(f"✓ Saved to {args.output}")
        
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

