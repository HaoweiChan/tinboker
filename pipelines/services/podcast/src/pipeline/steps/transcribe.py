"""
Step 2: Transcribe Episode

This module handles transcribing episode audio to text.
"""

from pathlib import Path

from ..config import PipelineConfig
from ..episode_data import EpisodeData
from ..service_container import ServiceContainer


def transcribe_episode(
    config: PipelineConfig,
    services: ServiceContainer,
    episode_data: EpisodeData
) -> None:
    """
    Transcribe episode audio to text.
    
    Args:
        config: Pipeline configuration
        services: Service container
        episode_data: Episode data (mutated in place)
    """
    # Check if transcript already exists in episode_data (loaded from existing episode)
    if episode_data.transcript_text:
        print(f"  ♻ Using transcript from episode data ({len(episode_data.transcript_text):,} characters)")
        return
    
    # Determine if we should transcribe
    # Transcribe if rerun_from is None (full pipeline), "download", or "transcribe"
    # For "summarize", "upload", or "validate", we skip transcription
    should_transcribe = config.rerun_from in [None, "download", "transcribe"]
    
    if not should_transcribe:
        # If rerun_from is "upload" or "validate", we don't need transcript
        if config.rerun_from in ["upload", "validate"]:
            return
        # For rerun_from="summarize", transcript should have been loaded in _load_existing_data
        # If it's not here, that means the episode doesn't exist or has no transcript
        if config.rerun_from == "summarize":
            raise ValueError("Transcript not available. Episode may not exist in Firestore or has no transcript_url.")
        return
    
    # Check if transcript already exists (idempotency)
    if episode_data.transcript_text:
        return
    
    # Check if we can reuse existing transcript (legacy support)
    if config.reuse_existing_transcript and services.firebase_service and services.gcs_service:
        existing = services.firebase_service.get_episode_by_fields(
            podcast_name=episode_data.podcast_name,
            episode_title=episode_data.api_data.get('title'),
            episode_number=episode_data.api_data.get('episodeNumber')
        )
        if existing and existing.get('transcript_url'):
            try:
                # Use new download method that returns dict with text, sentences, and words
                transcript_data = services.gcs_service.download_transcript_by_gcs_url(
                    existing['transcript_url']
                )
                if transcript_data and transcript_data.get('text'):
                    episode_data.transcript_text = transcript_data.get('text', '')
                    episode_data.transcript_words = transcript_data.get('words')
                    # Extract sentences from transcript data
                    sentences_data = transcript_data.get('sentences', [])
                    if sentences_data:
                        from src.models.podcast_models import Sentence
                        episode_data.transcript_sentences = [
                            Sentence(**s) if isinstance(s, dict) else s
                            for s in sentences_data
                        ]
                    print("  ♻ Reusing transcript from GCS")
                    if episode_data.transcript_sentences:
                        print(f"  ♻ Sentence-level timing available ({len(episode_data.transcript_sentences)} sentences)")
                    if episode_data.transcript_words:
                        print(f"  ♻ Word-level timing available ({len(episode_data.transcript_words)} words)")
                    return
            except Exception as e:
                print(f"  ⚠ Warning: Error downloading transcript from GCS: {e}")
                # Fall through to transcribe
    
    # Need to transcribe (only if we're actually transcribing, not downloading from GCS)
    # This check should only apply when rerun_from is None or "transcribe"
    if config.rerun_from not in ["summarize", "upload", "validate"]:
        if not episode_data.mp3_path:
            raise ValueError("MP3 file not available for transcription")
        
        if not services.stt_service:
            raise ValueError("STT service not initialized")
    
    episode_title = episode_data.api_data.get('title', 'Untitled Episode')
    
    # Get service name and model for logging
    if services.stt_service:
        service_name = services.stt_service.get_service_name()
        model = getattr(services.stt_service, 'model', None)
        model_info = f" (Model: {model})" if model else ""
    else:
        service_name = "Unknown"
        model_info = ""
    
    print(f"  🎤 Transcribing: {episode_title}")
    print(f"  🔧 Service: {service_name}{model_info}")
    
    # Transcribe
    if config.use_file_mode:
        # File mode: save to file
        from src.service.speech_to_text import transcribe_audio_file
        transcript_path = transcribe_audio_file(
            str(episode_data.mp3_path),
            output_base_dir=str(config.transcripts_dir),
            service=services.stt_service,
            language=episode_data.language
        )
        # Read transcript file (JSON or text for backward compatibility)
        transcript_path_obj = Path(transcript_path)
        if transcript_path_obj.suffix.lower() == '.json':
            # New format: JSON with text, sentences, and words
            try:
                import json
                transcript_data = json.loads(transcript_path_obj.read_text(encoding='utf-8'))
                episode_data.transcript_text = transcript_data.get('text', '')
                episode_data.transcript_words = transcript_data.get('words')
                # Extract sentences from transcript data
                sentences_data = transcript_data.get('sentences', [])
                if sentences_data:
                    from src.models.podcast_models import Sentence
                    episode_data.transcript_sentences = [
                        Sentence(**s) if isinstance(s, dict) else s
                        for s in sentences_data
                    ]
            except (json.JSONDecodeError, KeyError) as e:
                # JSON parse failed, fallback to text-only
                print(f"  ⚠ Warning: Failed to parse transcript JSON: {e}, treating as text-only")
                episode_data.transcript_text = transcript_path_obj.read_text(encoding='utf-8')
                episode_data.transcript_words = None
                episode_data.transcript_sentences = None
        else:
            # Old format: text-only (backward compatibility)
            episode_data.transcript_text = transcript_path_obj.read_text(encoding='utf-8')
            episode_data.transcript_words = None
            episode_data.transcript_sentences = None
    else:
        # Streaming mode: return dict with text and words
        from src.service.speech_to_text import transcribe_audio_file
        transcript_result = transcribe_audio_file(
            str(episode_data.mp3_path),
            service=services.stt_service,
            language=episode_data.language,
            return_text_only=True
        )
        # Extract text, sentences, and words from result
        if isinstance(transcript_result, dict):
            episode_data.transcript_text = transcript_result.get("text", "")
            episode_data.transcript_words = transcript_result.get("words")
            # Extract sentences from transcript result
            sentences_data = transcript_result.get("sentences", [])
            if sentences_data:
                from src.models.podcast_models import Sentence
                episode_data.transcript_sentences = [
                    Sentence(**s) if isinstance(s, dict) else s
                    for s in sentences_data
                ]
        else:
            # Fallback for backward compatibility
            episode_data.transcript_text = str(transcript_result)
            episode_data.transcript_words = None
            episode_data.transcript_sentences = None
    
    print(f"  ✓ Transcribed ({len(episode_data.transcript_text):,} characters)")
    if episode_data.transcript_sentences:
        print(f"  ✓ Sentence-level timing available ({len(episode_data.transcript_sentences)} sentences)")
    if episode_data.transcript_words:
        print(f"  ✓ Word-level timing available ({len(episode_data.transcript_words)} words)")


