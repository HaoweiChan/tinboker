"""
File Handler

Handles saving summary content to files.
"""

from pathlib import Path
from typing import Dict

from .service import SummarizeService


def save_summary(
    transcript_path: str,
    output_base_dir: str = "./data/summary_content"
) -> Dict:
    """
    Generate summary and save to files.
    
    Args:
        transcript_path: Path to transcript file
        output_base_dir: Base directory for summary markdown files
        
    Returns:
        Dictionary with:
            - summary_path: Path to saved markdown file
            - image_path: Path to saved SVG file
            - summary_content: Actual markdown content (string)
            - svg_content: Actual SVG content (string)
            - related_tickers: List of ticker symbols
    """
    transcript_path_obj = Path(transcript_path).resolve()
    
    if not transcript_path_obj.exists():
        raise FileNotFoundError(f"Transcript file not found: {transcript_path}")
    
    # Initialize service
    service = SummarizeService()
    
    # Read transcript and generate summary from text
    transcript_text = transcript_path_obj.read_text(encoding='utf-8')
    result = service.generate_summary_from_text(transcript_text)
    
    # Determine output paths (preserve directory structure like transcripts)
    # Example: data/downloads/podcast/episode.mp3 -> data/transcripts/podcast/episode.txt
    #          -> data/summary_content/podcast/episode.md
    #          -> data/images/podcast/episode.svg
    
    # Find "downloads" or "transcripts" in path to preserve structure
    parts = transcript_path_obj.parts
    summary_base = Path(output_base_dir)
    images_base = Path("./data/images")
    
    try:
        # Try to find "transcripts" first (since we're working with transcript files)
        if "transcripts" in parts:
            transcripts_idx = parts.index("transcripts")
            relative_parts = parts[transcripts_idx + 1:]
        elif "downloads" in parts:
            downloads_idx = parts.index("downloads")
            relative_parts = parts[downloads_idx + 1:]
        else:
            # Fallback: use parent directory name
            relative_parts = (transcript_path_obj.parent.name, transcript_path_obj.stem)
    except (ValueError, IndexError):
        # Fallback: use parent directory name
        relative_parts = (transcript_path_obj.parent.name, transcript_path_obj.stem)
    
    # Create summary markdown path
    summary_path = summary_base / Path(*relative_parts).with_suffix('.md')
    
    # Create SVG image path
    image_path = images_base / Path(*relative_parts).with_suffix('.svg')
    
    # Ensure directories exist
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    image_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Save files
    summary_path.write_text(result['summary_text'], encoding='utf-8')
    image_path.write_text(result['svg_content'], encoding='utf-8')
    
    return {
        'summary_path': str(summary_path),
        'image_path': str(image_path),
        'summary_content': result['summary_text'],
        'svg_content': result['svg_content'],
        'related_tickers': result['related_tickers']
    }
