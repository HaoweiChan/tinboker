"""
Step 3: Generate Summary

This module handles generating summaries, SVG, and tickers from transcripts.
"""


from ..config import PipelineConfig
from ..episode_data import EpisodeData
from ..service_container import ServiceContainer
from ..utils import extract_tags_and_tickers, extract_tickers_from_markdown


class SummaryNotPersistableError(RuntimeError):
    """Raised when a summary must NOT be persisted (placeholder / failed validation).

    Raising this in the summarize step (BEFORE the GCS/Firestore/Postgres/wiki
    write steps) is what prevents a bad run from overwriting previously-good
    episode content. The processor catches it, logs the failure, and skips the
    episode — the existing stored summary is left untouched.
    """


def assert_summary_persistable(episode_data: EpisodeData) -> None:
    """Gate persistence on a real, self-consistent summary.

    A failed external summarization falls back to the placeholder summarizer,
    which emits junk prose + random tickers. Those writes used to land in GCS /
    Firestore / Postgres / wiki *before* the validate step ran, so a failed run
    clobbered good content. We validate the in-memory summary here, before any
    write, and refuse to persist when:

    - the summary is a placeholder (``is_placeholder`` marker), or
    - there is no real summary text, or
    - a related ticker is missing from the summary body (the same ticker/summary
      consistency check the validate step runs — moved earlier so it gates writes
      instead of firing after them).
    """
    summary_result = episode_data.summary_result or {}

    if summary_result.get('is_placeholder'):
        raise SummaryNotPersistableError(
            "Refusing to persist: summarizer fell back to the placeholder result "
            "(the external summarizer failed — e.g. truncated/unparseable LLM JSON "
            "on a long episode). Not overwriting existing content with placeholder."
        )

    summary_text = (summary_result.get('summary_text') or '').strip()
    if not summary_text:
        raise SummaryNotPersistableError(
            "Refusing to persist: summary text is empty."
        )

    # Every related ticker must appear as #ticker:SYMBOL in the summary body. In
    # the success path episode_data.tickers is derived FROM the summary, so this
    # always holds; it only trips for placeholder/garbage output (random tickers
    # with no #ticker: links) — catching the exact "Ticker Mismatch" the validate
    # step used to raise, but now BEFORE anything is written.
    if episode_data.tickers:
        tickers_in_summary = {t.upper() for t in extract_tickers_from_markdown(summary_text)}
        missing = [t.upper() for t in episode_data.tickers if t.upper() not in tickers_in_summary]
        if missing:
            raise SummaryNotPersistableError(
                "Refusing to persist: related ticker(s) missing from summary text: "
                f"{', '.join(missing)}. The summary and ticker list are inconsistent "
                "(typical of a placeholder fallback)."
            )


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

    # Gate persistence: refuse to continue (and thus to write GCS/Firestore/
    # Postgres/wiki in the later steps) when the summary is a placeholder or fails
    # the ticker/summary consistency check. Raising here — before any write step —
    # is what keeps a failed run from overwriting previously-good content.
    assert_summary_persistable(episode_data)

