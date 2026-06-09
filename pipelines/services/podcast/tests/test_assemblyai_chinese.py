#!/usr/bin/env python3
"""
Test script for AssemblyAI transcription with Chinese audio files.

This script provides a highly customizable function to test AssemblyAI's transcription
API with various configuration options based on the official API specification.
"""

import inspect
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from dotenv import load_dotenv

# Load environment variables from project root
# Try to find .env file in project root (parent of tests directory)
project_root = Path(__file__).parent.parent
env_file = project_root / ".env"
load_dotenv(dotenv_path=env_file)

# Import AssemblyAI
try:
    import assemblyai as aai
except ImportError:
    raise ImportError(
        "assemblyai is not installed. Install it with: pip install assemblyai"
    )


# Enum values from API specification
LANGUAGE_CODES = [
    "en", "en_au", "en_uk", "en_us", "es", "fr", "de", "it", "pt", "nl",
    "af", "sq", "am", "ar", "hy", "as", "az", "ba", "eu", "be", "bn", "bs",
    "br", "bg", "my", "ca", "zh", "hr", "cs", "da", "et", "fo", "fi", "gl",
    "ka", "el", "gu", "ht", "ha", "haw", "he", "hi", "hu", "is", "id", "ja",
    "jw", "kn", "kk", "km", "ko", "lo", "la", "lv", "ln", "lt", "lb", "mk",
    "mg", "ms", "ml", "mt", "mi", "mr", "mn", "ne", "no", "nn", "oc", "pa",
    "ps", "fa", "pl", "ro", "ru", "sa", "sr", "sn", "sd", "si", "sk", "sl",
    "so", "su", "sw", "sv", "tl", "tg", "ta", "tt", "te", "th", "bo", "tr",
    "tk", "uk", "ur", "uz", "vi", "cy", "yi", "yo"
]

SPEECH_MODELS = ["best", "slam-1", "universal"]

REDACT_PII_AUDIO_QUALITY = ["mp3", "wav"]

PII_POLICIES = [
    "account_number", "banking_information", "blood_type", "credit_card_cvv",
    "credit_card_expiration", "credit_card_number", "date", "date_interval",
    "date_of_birth", "drivers_license", "drug", "duration", "email_address",
    "event", "filename", "gender_sexuality", "healthcare_number", "injury",
    "ip_address", "language", "location", "marital_status", "medical_condition",
    "medical_process", "money_amount", "nationality", "number_sequence",
    "occupation", "organization", "passport_number", "password", "person_age",
    "person_name", "phone_number", "physical_attribute", "political_affiliation",
    "religion", "statistics", "time", "url", "us_social_security_number",
    "username", "vehicle_id", "zodiac_sign"
]

SUBSTITUTION_POLICIES = ["entity_name", "hash"]

SUMMARY_MODELS = ["informative", "conversational", "catchy"]

SUMMARY_TYPES = ["bullets", "bullets_verbose", "gist", "headline", "paragraph"]


def test_assemblyai_transcription(
    audio_path: Union[str, Path] = "./data/downloads/1test_short/shortmp3.mp3",
    output_path: Optional[Union[str, Path]] = None,
    output_dir: Union[str, Path] = "data/test_transcript",
    # Language settings
    language_code: Optional[str] = "zh",
    language_codes: Optional[List[str]] = None,
    language_detection: bool = False,
    language_detection_options: Optional[Dict[str, Any]] = None,
    language_confidence_threshold: Optional[float] = None,
    # Speech model settings
    speech_model: Optional[str] = None,
    speech_models: Optional[List[str]] = None,
    # Basic transcription settings
    punctuate: bool = True,
    format_text: bool = True,
    disfluencies: bool = False,
    multichannel: bool = False,
    # Webhook settings
    webhook_url: Optional[str] = None,
    webhook_auth_header_name: Optional[str] = None,
    webhook_auth_header_value: Optional[str] = None,
    # Audio processing settings
    auto_highlights: bool = False,
    audio_start_from: Optional[int] = None,
    audio_end_at: Optional[int] = None,
    filter_profanity: bool = False,
    # PII Redaction settings
    redact_pii: bool = False,
    redact_pii_audio: bool = False,
    redact_pii_audio_quality: Optional[str] = None,
    redact_pii_policies: Optional[List[str]] = None,
    redact_pii_sub: Optional[str] = None,
    redact_pii_audio_options: Optional[Dict[str, Any]] = None,
    # Speaker diarization settings
    speaker_labels: bool = False,
    speakers_expected: Optional[int] = None,
    speaker_options: Optional[Dict[str, Any]] = None,
    # Content analysis settings
    content_safety: bool = False,
    content_safety_confidence: int = 50,
    iab_categories: bool = False,
    # Customization settings
    custom_spelling: Optional[List[Dict[str, Any]]] = None,
    keyterms_prompt: Optional[List[str]] = None,
    prompt: Optional[str] = None,
    # Analysis features
    sentiment_analysis: bool = False,
    auto_chapters: bool = False, # TODO: test TRUE
    entity_detection: bool = False, # TODO: test TRUE
    speech_threshold: Optional[float] = None,
    # Summarization settings
    summarization: bool = False, # TODO: test TRUE
    summary_model: Optional[str] = None,
    summary_type: Optional[str] = None,
    # Custom topics
    custom_topics: bool = False,
    topics: Optional[List[str]] = None,
    # Speech understanding
    speech_understanding: Optional[Dict[str, Any]] = None,
    # API key
    api_key: Optional[str] = None
) -> Dict[str, Any]:
    """
    Test AssemblyAI transcription with highly customizable parameters.
    
    This function transcribes an audio file using AssemblyAI's API and saves
    the complete API response to a JSON file.
    
    Args:
        audio_path: Path to the audio file to transcribe. Default: "./data/downloads/1test_short/shortmp3.mp3"
        output_path: Full path for the output JSON file. If None, will be auto-generated.
        output_dir: Directory to save output JSON file. Default: "data/test_transcript"
        
        Language Settings:
        language_code: Language code for transcription. 
            Possible values: {LANGUAGE_CODES}
            Default: "zh" (Chinese)
        language_codes: List of language codes for code switching. One must be "en".
        language_detection: Enable automatic language detection. Default: False
        language_detection_options: Dict with keys:
            - expected_languages: List of expected languages (default: ["all"])
            - fallback_language: Fallback language (default: "auto")
            - code_switching: bool (default: False)
            - code_switching_confidence_threshold: float
        language_confidence_threshold: Confidence threshold for detected language (0.0-1.0)
        
        Speech Model Settings:
        speech_model: Speech model to use.
            Possible values: {SPEECH_MODELS}
            Default: None (uses "universal")
        speech_models: List of speech models in priority order.
            Possible values: {SPEECH_MODELS}
        
        Basic Transcription Settings:
        punctuate: Enable automatic punctuation. Default: True
        format_text: Enable text formatting. Default: True
        disfluencies: Transcribe filler words like "umm". Default: False
        multichannel: Enable multichannel transcription. Default: False
        
        Webhook Settings:
        webhook_url: URL for webhook notifications
        webhook_auth_header_name: Header name for webhook auth
        webhook_auth_header_value: Header value for webhook auth
        
        Audio Processing Settings:
        auto_highlights: Enable key phrases extraction. Default: False
        audio_start_from: Start time in milliseconds
        audio_end_at: End time in milliseconds
        filter_profanity: Filter profanity from transcript. Default: False
        
        PII Redaction Settings:
        redact_pii: Redact PII from transcript. Default: False
        redact_pii_audio: Generate redacted audio file. Default: False
        redact_pii_audio_quality: Audio quality for redacted file.
            Possible values: {REDACT_PII_AUDIO_QUALITY}
        redact_pii_policies: List of PII policies to enable.
            Possible values: {PII_POLICIES}
        redact_pii_sub: Replacement logic for PII.
            Possible values: {SUBSTITUTION_POLICIES}
        redact_pii_audio_options: Dict with key:
            - return_redacted_no_speech_audio: bool (default: False)
        
        Speaker Diarization Settings:
        speaker_labels: Enable speaker diarization. Default: False
        speakers_expected: Number of expected speakers
        speaker_options: Dict with keys:
            - min_speakers_expected: int (default: 1)
            - max_speakers_expected: int (default: 10)
        
        Content Analysis Settings:
        content_safety: Enable content moderation. Default: False
        content_safety_confidence: Confidence threshold (25-100). Default: 50
        iab_categories: Enable topic detection. Default: False
        
        Customization Settings:
        custom_spelling: List of dicts with keys "from" (list of strings) and "to" (string)
        keyterms_prompt: List of domain-specific words/phrases (max 200 for Universal, 1000 for Slam-1)
        prompt: Prompt string (currently no functionality)
        
        Analysis Features:
        sentiment_analysis: Enable sentiment analysis. Default: False
        auto_chapters: Enable auto chapters. Default: False
        entity_detection: Enable entity detection. Default: False
        speech_threshold: Reject audio with less than this fraction of speech (0.0-1.0)
        
        Summarization Settings:
        summarization: Enable summarization. Default: False
        summary_model: Model for summarization.
            Possible values: {SUMMARY_MODELS}
        summary_type: Type of summary.
            Possible values: {SUMMARY_TYPES}
        
        Custom Topics:
        custom_topics: Enable custom topics. Default: False
        topics: List of custom topics
        
        Speech Understanding:
        speech_understanding: Dict for speech understanding tasks (translation, speaker identification, custom formatting)
        
        API Key:
        api_key: AssemblyAI API key. If None, uses ASSEMBLYAI_API_KEY env var.
    
    Returns:
        Dict containing the complete API response
    
    Raises:
        FileNotFoundError: If audio file doesn't exist
        ValueError: If invalid parameter values are provided
        RuntimeError: If transcription fails
    """
    # Format docstring with enum values
    docstring = test_assemblyai_transcription.__doc__.format(
        LANGUAGE_CODES=", ".join(LANGUAGE_CODES),
        SPEECH_MODELS=", ".join(SPEECH_MODELS),
        REDACT_PII_AUDIO_QUALITY=", ".join(REDACT_PII_AUDIO_QUALITY),
        PII_POLICIES=", ".join(PII_POLICIES),
        SUBSTITUTION_POLICIES=", ".join(SUBSTITUTION_POLICIES),
        SUMMARY_MODELS=", ".join(SUMMARY_MODELS),
        SUMMARY_TYPES=", ".join(SUMMARY_TYPES)
    )
    test_assemblyai_transcription.__doc__ = docstring
    
    # Get API key
    api_key = api_key or os.getenv("ASSEMBLYAI_API_KEY")
    if not api_key:
        # Check if .env file exists
        env_file = Path(".env")
        env_file_abs = Path(__file__).parent.parent / ".env"
        
        error_msg = (
            "AssemblyAI API key is required.\n\n"
            "To fix this, you have two options:\n"
            "1. Set it in your .env file:\n"
            "   Create or edit .env file in the project root and add:\n"
            "   ASSEMBLYAI_API_KEY=your_api_key_here\n\n"
            "2. Pass it directly to the function:\n"
            "   test_assemblyai_transcription(api_key='your_api_key_here', ...)\n\n"
        )
        
        if not env_file.exists() and not env_file_abs.exists():
            error_msg += (
                "Note: No .env file found in the project root.\n"
                "You can create one at: " + str(Path(__file__).parent.parent / ".env") + "\n"
            )
        else:
            error_msg += (
                "Note: .env file exists but ASSEMBLYAI_API_KEY is not set.\n"
                "Please add ASSEMBLYAI_API_KEY=your_api_key_here to your .env file.\n"
            )
        
        error_msg += (
            "\nTo get your API key:\n"
            "1. Sign up at https://www.assemblyai.com/\n"
            "2. Go to your dashboard and copy your API key\n"
            "3. Add it to your .env file or pass it as a parameter\n"
        )
        
        raise ValueError(error_msg)
    
    # Set API key
    aai.settings.api_key = api_key
    
    # Validate audio file
    audio_path = Path(audio_path)
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")
    
    # Validate enum values
    if language_code and language_code not in LANGUAGE_CODES:
        raise ValueError(f"Invalid language_code: {language_code}. Must be one of: {LANGUAGE_CODES}")
    
    if speech_model and speech_model not in SPEECH_MODELS:
        raise ValueError(f"Invalid speech_model: {speech_model}. Must be one of: {SPEECH_MODELS}")
    
    if speech_models:
        for model in speech_models:
            if model not in SPEECH_MODELS:
                raise ValueError(f"Invalid speech_model in speech_models: {model}. Must be one of: {SPEECH_MODELS}")
    
    if redact_pii_audio_quality and redact_pii_audio_quality not in REDACT_PII_AUDIO_QUALITY:
        raise ValueError(f"Invalid redact_pii_audio_quality: {redact_pii_audio_quality}. Must be one of: {REDACT_PII_AUDIO_QUALITY}")
    
    if redact_pii_sub and redact_pii_sub not in SUBSTITUTION_POLICIES:
        raise ValueError(f"Invalid redact_pii_sub: {redact_pii_sub}. Must be one of: {SUBSTITUTION_POLICIES}")
    
    if summary_model and summary_model not in SUMMARY_MODELS:
        raise ValueError(f"Invalid summary_model: {summary_model}. Must be one of: {SUMMARY_MODELS}")
    
    if summary_type and summary_type not in SUMMARY_TYPES:
        raise ValueError(f"Invalid summary_type: {summary_type}. Must be one of: {SUMMARY_TYPES}")
    
    if redact_pii_policies:
        for policy in redact_pii_policies:
            if policy not in PII_POLICIES:
                raise ValueError(f"Invalid PII policy: {policy}. Must be one of: {PII_POLICIES}")
    
    # Build transcription config
    config_params = {}
    
    # Language settings
    if language_code:
        config_params["language_code"] = language_code
    if language_codes:
        config_params["language_codes"] = language_codes
    if language_detection:
        config_params["language_detection"] = language_detection
    if language_detection_options:
        config_params["language_detection_options"] = language_detection_options
    if language_confidence_threshold is not None:
        config_params["language_confidence_threshold"] = language_confidence_threshold
    
    # Speech model settings
    # Note: The SDK may show a Pydantic warning about enum vs string, but strings work fine
    if speech_model:
        config_params["speech_model"] = speech_model
    if speech_models:
        config_params["speech_models"] = speech_models
    
    # Basic transcription settings
    config_params["punctuate"] = punctuate
    config_params["format_text"] = format_text
    config_params["disfluencies"] = disfluencies
    config_params["multichannel"] = multichannel
    
    # Webhook settings
    if webhook_url:
        config_params["webhook_url"] = webhook_url
    if webhook_auth_header_name:
        config_params["webhook_auth_header_name"] = webhook_auth_header_name
    if webhook_auth_header_value:
        config_params["webhook_auth_header_value"] = webhook_auth_header_value
    
    # Audio processing settings
    config_params["auto_highlights"] = auto_highlights
    if audio_start_from is not None:
        config_params["audio_start_from"] = audio_start_from
    if audio_end_at is not None:
        config_params["audio_end_at"] = audio_end_at
    config_params["filter_profanity"] = filter_profanity
    
    # PII Redaction settings
    config_params["redact_pii"] = redact_pii
    config_params["redact_pii_audio"] = redact_pii_audio
    if redact_pii_audio_quality:
        config_params["redact_pii_audio_quality"] = redact_pii_audio_quality
    if redact_pii_policies:
        config_params["redact_pii_policies"] = redact_pii_policies
    if redact_pii_sub:
        config_params["redact_pii_sub"] = redact_pii_sub
    if redact_pii_audio_options:
        config_params["redact_pii_audio_options"] = redact_pii_audio_options
    
    # Speaker diarization settings
    config_params["speaker_labels"] = speaker_labels
    if speakers_expected is not None:
        config_params["speakers_expected"] = speakers_expected
    if speaker_options:
        config_params["speaker_options"] = speaker_options
    
    # Content analysis settings
    config_params["content_safety"] = content_safety
    config_params["content_safety_confidence"] = content_safety_confidence
    config_params["iab_categories"] = iab_categories
    
    # Customization settings
    if custom_spelling:
        config_params["custom_spelling"] = custom_spelling
    if keyterms_prompt:
        config_params["keyterms_prompt"] = keyterms_prompt
    if prompt:
        config_params["prompt"] = prompt
    
    # Analysis features
    config_params["sentiment_analysis"] = sentiment_analysis
    config_params["auto_chapters"] = auto_chapters
    config_params["entity_detection"] = entity_detection
    if speech_threshold is not None:
        config_params["speech_threshold"] = speech_threshold
    
    # Summarization settings
    config_params["summarization"] = summarization
    if summary_model:
        config_params["summary_model"] = summary_model
    if summary_type:
        config_params["summary_type"] = summary_type
    
    # Custom topics - Note: These may not be directly supported in Python SDK
    # Some parameters from the API spec may need to be set differently
    # We'll filter out unsupported parameters before creating the config
    if custom_topics:
        # Note: custom_topics might not be a direct parameter in Python SDK
        # It may need to be handled differently or may not be supported yet
        # Try adding it, but it will be filtered if not supported
        config_params["custom_topics"] = custom_topics
    if topics:
        # Note: topics might not be a direct parameter in Python SDK
        # Try adding it, but it will be filtered if not supported
        config_params["topics"] = topics
    
    # Speech understanding
    if speech_understanding:
        config_params["speech_understanding"] = speech_understanding
    
    # Filter out parameters that aren't supported by the Python SDK
    # Get the valid parameters from TranscriptionConfig using introspection
    try:
        sig = inspect.signature(aai.TranscriptionConfig.__init__)
        valid_params = set(sig.parameters.keys()) - {'self'}
        
        # Filter config_params to only include valid parameters
        filtered_config_params = {
            k: v for k, v in config_params.items() 
            if k in valid_params
        }
        
        # Warn about filtered parameters
        filtered_out = set(config_params.keys()) - set(filtered_config_params.keys())
        if filtered_out:
            print(f"Warning: The following parameters are not supported by the Python SDK and will be ignored: {sorted(filtered_out)}")
            print("Note: The API specification includes these parameters, but the Python SDK may not support them yet.")
        
        config_params = filtered_config_params
    except Exception as e:
        print(f"Warning: Could not validate parameters using introspection: {e}")
        print("Attempting to create config with all parameters - some may fail...")
        # If we can't validate, try with all parameters and let it fail with a clearer error
    
    # Create transcription config
    try:
        config = aai.TranscriptionConfig(**config_params)
    except TypeError as e:
        # Provide a more helpful error message
        error_msg = str(e)
        # Try to extract the problematic parameter name from the error
        match = re.search(r"unexpected keyword argument ['\"]([^'\"]+)['\"]", error_msg)
        if match:
            bad_param = match.group(1)
            raise TypeError(
                f"Failed to create TranscriptionConfig: {error_msg}\n"
                f"The parameter '{bad_param}' is not supported by the AssemblyAI Python SDK.\n"
                f"Please remove it from your configuration or check the SDK documentation.\n"
                f"All parameters attempted: {sorted(config_params.keys())}"
            ) from e
        else:
            raise TypeError(
                f"Failed to create TranscriptionConfig: {error_msg}\n"
                f"This may be because some parameters are not supported by the AssemblyAI Python SDK.\n"
                f"Parameters attempted: {sorted(config_params.keys())}\n"
                f"Please check the AssemblyAI Python SDK documentation for supported parameters."
            ) from e
    
    # Create transcriber and transcribe
    print(f"Transcribing audio file: {audio_path}")
    print(f"Configuration: {len(config_params)} parameters set")
    
    transcriber = aai.Transcriber(config=config)
    
    # transcribe() already waits for completion and returns a completed transcript
    print("Starting transcription (this may take a while for long audio files)...")
    transcript = transcriber.transcribe(str(audio_path))
    
    # Check status - handle both enum and string types
    status_value = str(transcript.status)
    if hasattr(transcript.status, 'value'):
        status_value = str(transcript.status.value)
    status_value_lower = status_value.lower()
    
    print(f"Status: {transcript.status}")
    print(f"Transcript ID: {transcript.id}")
    
    # Check for errors
    if status_value_lower == "error":
        error_msg = transcript.error if hasattr(transcript, 'error') else "Unknown error"
        raise RuntimeError(f"Transcription failed: {error_msg}")
    
    if status_value_lower != "completed":
        print(f"Warning: Transcript status is '{status_value}', expected 'completed'")
    
    print("✓ Transcription completed successfully!")
    
    # Convert transcript to dict by extracting all attributes directly
    # Don't use Pydantic methods, just extract all values as-is
    print("  Extracting all transcript attributes...")
    transcript_dict = {}
    
    # Get all attributes from the transcript object
    for attr_name in dir(transcript):
        # Skip private attributes and methods
        if attr_name.startswith('_'):
            continue
        
        # Skip callable methods (but keep properties)
        try:
            attr_value = getattr(transcript, attr_name)
            if callable(attr_value) and not isinstance(attr_value, property):
                continue
        except Exception:
            continue
        
        # Extract the value
        try:
            value = getattr(transcript, attr_name)
            # Convert to JSON-serializable format
            transcript_dict[attr_name] = _convert_to_json_serializable(value)
        except Exception:
            # If we can't get the value, skip it
            pass
    
    print(f"  Extracted {len(transcript_dict)} attributes")
    
    # Generate output path
    if output_path is None:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        output_filename = f"{audio_path.stem}_transcript.json"
        output_path = output_dir / output_filename
    else:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Save to JSON file
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(transcript_dict, f, indent=2, ensure_ascii=False, default=str)
    
    print(f"✓ Transcript saved to: {output_path}")
    print(f"  Transcript text length: {len(transcript.text) if transcript.text else 0} characters")
    
    return transcript_dict


def _convert_to_json_serializable(obj):
    """Helper function to convert any object to JSON-serializable format."""
    if obj is None:
        return None
    
    # Handle primitive types
    if isinstance(obj, (str, int, float, bool)):
        return obj
    
    # Handle dict-like objects
    if isinstance(obj, dict):
        return {k: _convert_to_json_serializable(v) for k, v in obj.items()}
    
    # Handle lists and tuples
    if isinstance(obj, (list, tuple)):
        return [_convert_to_json_serializable(item) for item in obj]
    
    # Handle sets
    if isinstance(obj, set):
        return [_convert_to_json_serializable(item) for item in obj]
    
    # Handle enum types
    if hasattr(obj, 'value'):
        return _convert_to_json_serializable(obj.value)
    if hasattr(obj, 'name'):
        return str(obj.name)
    
    # Handle objects with __dict__
    if hasattr(obj, '__dict__'):
        result = {}
        for key, value in obj.__dict__.items():
            if not key.startswith('_'):
                result[key] = _convert_to_json_serializable(value)
        return result
    
    # Handle dataclasses
    if hasattr(obj, '__dataclass_fields__'):
        result = {}
        for field_name in obj.__dataclass_fields__:
            try:
                value = getattr(obj, field_name)
                result[field_name] = _convert_to_json_serializable(value)
            except Exception:
                pass
        return result
    
    # For other types, try to convert to string
    try:
        return str(obj)
    except Exception:
        return None


if __name__ == "__main__":
    # Example usage with Chinese audio
    # 
    # Option 1: Use API key from .env file (recommended)
    # Make sure ASSEMBLYAI_API_KEY is set in your .env file
    #
    # Option 2: Pass API key directly (for testing)
    # result = test_assemblyai_transcription(
    #     api_key="your_api_key_here",
    #     audio_path="./data/downloads/1test_short/shortmp3.mp3",
    #     ...
    # )
    
    result = test_assemblyai_transcription(
        audio_path="./data/downloads/1test_short/shortmp3.mp3",
        language_code="zh",
        speech_model="best", # best, slam-1, universal
        punctuate=True,
        format_text=True,
        # auto_chapters=True,
        # sentiment_analysis=True,
    )
    
    print("\nTranscription completed successfully!")
    if result:
        print(f"Transcript ID: {result.get('id', 'N/A')}")
        print(f"Status: {result.get('status', 'N/A')}")
        text_preview = result.get('text', '')
        if text_preview:
            print(f"Text preview: {text_preview[:100]}...")
        else:
            print("Text: (empty or not available)")
    else:
        print("Warning: Result dictionary is empty. Check the JSON file for details.")

