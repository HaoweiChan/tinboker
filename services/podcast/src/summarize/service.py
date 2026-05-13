"""
Summarize Service

Main service class for generating summaries from transcripts.
"""

import os
from pathlib import Path
from typing import Dict, Optional

from .content_builder import analyze_transcript_with_workflow_api, is_workflow_api_available
from .placeholders import generate_placeholder_result


class SummarizeService:
    """Service for generating summaries, SVG images, and tickers from transcripts."""
    
    def __init__(self, use_external: Optional[bool] = None):
        """
        Initialize the summarizer service.
        
        Args:
            use_external: If True, use external services (Workflow API or Content-Builder), 
                         else use placeholder. If None, uses environment variable 
                         USE_EXTERNAL_SUMMARIZER or defaults to True.
        """
        if use_external is None:
            use_external = os.getenv("USE_EXTERNAL_SUMMARIZER", "true").lower() == "true"
        # use_external is True if Workflow API is available
        self.use_external = use_external and is_workflow_api_available()
    
    def generate_summary(self, transcript_path: str) -> Dict:
        """
        Generate summary, SVG, and tickers from transcript file.
        
        Args:
            transcript_path: Path to transcript file
            
        Returns:
            Dictionary with:
                - summary_text: Summary text (markdown)
                - svg_content: SVG XML string (placeholder)
                - related_tickers: List of ticker symbols (placeholder)
        """
        # Read transcript file
        transcript_path_obj = Path(transcript_path)
        if transcript_path_obj.exists():
            transcript_text = transcript_path_obj.read_text(encoding='utf-8')
        else:
            transcript_text = ""
        
        return self.generate_summary_from_text(transcript_text)
    
    def generate_summary_from_text(
        self, 
        transcript_text: str, 
        podcast_name: Optional[str] = None,
        episode_title: Optional[str] = None,
        words: Optional[list] = None,
        sentences: Optional[list] = None
    ) -> Dict:
        """
        Generate summary, SVG, and tickers from transcript text.
        
        Tries methods in order:
        1. Workflow API (if DIFI_API_KEY and DIFI_API_BASE_URL are available)
        2. Content-Builder library (if available)
        3. Placeholder summarizer (fallback)
        
        Args:
            transcript_text: Transcript text content (string)
            podcast_name: Name of the podcast (optional, for external summarizer)
            episode_title: Title of the episode (optional, for external summarizer)
            words: Optional list of word objects with timing information (deprecated)
            sentences: Optional list of sentence objects with timing information
            
        Returns:
            Dictionary with:
                - summary_text: Summary text (markdown)
                - svg_content: SVG XML string (placeholder)
                - related_tickers: List of ticker symbols (placeholder)
        """
        if not self.use_external:
            return generate_placeholder_result(transcript_text)
        
        # Try Workflow API (if available)
        if is_workflow_api_available():
            try:
                print("📡 Attempting to use Workflow API for summarization...")
                
                api_result = analyze_transcript_with_workflow_api(
                    transcript=transcript_text,
                    source=podcast_name or "Podcast",
                    episode_title=episode_title or "Episode",
                    sentences=sentences,
                    words=words  # Deprecated, kept for backward compatibility
                )
                
                # Extract markdown_report, events_markdown, pptx_base64, marp_markdown, ticker_recommendations, and ticker_marp_markdown from API result
                # API result is now a dict with markdown_report, events_markdown, pptx_base64, marp_markdown, ticker_recommendations, and ticker_marp_markdown
                if isinstance(api_result, dict):
                    summary_text = api_result.get("markdown_report", "")
                    events_markdown = api_result.get("events_markdown")
                    pptx_base64 = api_result.get("pptx_base64")
                    marp_markdown = api_result.get("marp_markdown")
                    ticker_recommendations = api_result.get("ticker_recommendations")
                    ticker_marp_markdown = api_result.get("ticker_marp_markdown")
                else:
                    # Backward compatibility: if API returns string, use it as markdown_report
                    summary_text = api_result
                    events_markdown = None
                    pptx_base64 = None
                    marp_markdown = None
                    ticker_recommendations = None
                    ticker_marp_markdown = None
                
                # SVG and tickers remain as placeholders (Workflow API doesn't provide them)
                from .placeholders import extract_placeholder_tickers, generate_placeholder_svg
                svg_content = generate_placeholder_svg()
                related_tickers = extract_placeholder_tickers()
                
                print("✓ Successfully generated summary using Workflow API")
                result = {
                    'summary_text': summary_text,
                    'svg_content': svg_content,
                    'related_tickers': related_tickers
                }
                
                # Add events_markdown if available
                if events_markdown:
                    result['events_markdown'] = events_markdown
                    print(f"  ✓ Also received events_markdown ({len(events_markdown):,} characters)")
                
                # Add pptx_base64 if available
                if pptx_base64:
                    result['pptx_base64'] = pptx_base64
                    print(f"  ✓ Also received pptx_base64 ({len(pptx_base64):,} characters)")
                
                # Add marp_markdown if available
                if marp_markdown:
                    result['marp_markdown'] = marp_markdown
                    print(f"  ✓ Also received marp_markdown ({len(marp_markdown):,} characters)")
                
                # Add ticker_recommendations if available
                if ticker_recommendations:
                    result['ticker_recommendations'] = ticker_recommendations
                    if isinstance(ticker_recommendations, dict):
                        ticker_count = len(ticker_recommendations.get('ticker_recommendations', []))
                        print(f"  ✓ Also received ticker_recommendations ({ticker_count} tickers)")
                    else:
                        print("  ✓ Also received ticker_recommendations")
                
                # Add ticker_marp_markdown if available
                if ticker_marp_markdown:
                    result['ticker_marp_markdown'] = ticker_marp_markdown
                    print(f"  ✓ Also received ticker_marp_markdown ({len(ticker_marp_markdown):,} characters)")
                
                return result
            except ValueError as e:
                err_str = str(e)
                if "unparseable" in err_str or "JSON" in err_str:
                    print(f"⚠ LLM output parse error: {e}")
                else:
                    print(f"⚠ Pipeline configuration error: {e}")
                print("  Falling back to placeholder summarizer...")
            except Exception as e:
                print(f"⚠ Pipeline error: {e}")
                print("  Falling back to placeholder summarizer...")
        
        # Final fallback to placeholder
        print("⚠ Using placeholder summarizer (no external services available)")
        return generate_placeholder_result(transcript_text)
