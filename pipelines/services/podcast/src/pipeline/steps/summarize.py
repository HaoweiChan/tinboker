"""
Step 3: Generate Summary

This module handles generating summaries, SVG, and tickers from transcripts.
"""


from ..config import PipelineConfig
from ..episode_data import EpisodeData
from ..service_container import ServiceContainer
from ..utils import extract_tags_and_tickers


def generate_summary(
    config: PipelineConfig,
    services: ServiceContainer,
    episode_data: EpisodeData
) -> None:
    """
    Generate summary, SVG, and tickers from transcript.
    
    Args:
        config: Pipeline configuration
        services: Service container
        episode_data: Episode data (mutated in place)
    """
    # Determine if we should summarize
    # Skip if rerun_from is "upload" or "validate"
    should_summarize = config.rerun_from in [None, "download", "transcribe", "summarize"]
    
    if not should_summarize:
        return
    
    # Check if summary already exists (idempotency)
    # For rerun_from="summarize" or "download", we want to regenerate even if summary exists
    if episode_data.summary_result and config.rerun_from not in ["summarize", "download"]:
        return
    
    # Need transcript
    if not episode_data.transcript_text:
        raise ValueError("Transcript not available for summarization")
    
    episode_title = episode_data.api_data.get('title', 'Untitled Episode')
    print(f"  📝 Summarizing: {episode_title}")
    
    # Generate summary
    if not services.summarize_service:
        raise ValueError("Summarize service not initialized")
    
    # Convert sentences to list of dicts if needed
    sentences_data = None
    if episode_data.transcript_sentences:
        from src.models.podcast_models import Sentence
        sentences_data = [
            {
                "index": s.index,
                "content": s.content,
                "start": s.start,
                "end": s.end
            } if isinstance(s, Sentence) else s
            for s in episode_data.transcript_sentences
        ]
    
    summary_result = services.summarize_service.generate_summary_from_text(
        episode_data.transcript_text,
        podcast_name=episode_data.podcast_name,
        episode_title=episode_title,
        words=episode_data.transcript_words,
        sentences=sentences_data
    )
    
    # Convert sentences to markdown format and add to summary_result
    if episode_data.transcript_sentences:
        from ..utils import convert_sentences_to_markdown
        sentences_markdown = convert_sentences_to_markdown(episode_data.transcript_sentences)
        summary_result['sentences_markdown'] = sentences_markdown
        print(f"  ✓ Generated sentences markdown ({len(episode_data.transcript_sentences)} sentences)")
    
    episode_data.summary_result = summary_result
    
    # Extract tags and tickers from summary
    extracted = extract_tags_and_tickers(summary_result)
    episode_data.tags = extracted['tags']
    episode_data.tickers = extracted['tickers']
    
    if episode_data.tags:
        print(f"  ✓ Extracted {len(episode_data.tags)} tags: {', '.join(episode_data.tags[:5])}{'...' if len(episode_data.tags) > 5 else ''}")
    if episode_data.tickers:
        print(f"  ✓ Extracted {len(episode_data.tickers)} tickers: {', '.join(episode_data.tickers[:5])}{'...' if len(episode_data.tickers) > 5 else ''}")
    
    print(f"  ✓ Generated summary ({len(summary_result.get('summary_text', '')):,} characters)")

