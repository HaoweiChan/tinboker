#!/usr/bin/env python3
"""
Test script for Groq Whisper speech-to-text API.

This script tests Groq's Whisper transcription API with audio samples.
It extracts audio segments from files and transcribes them to various formats.
"""

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional, Union

from dotenv import load_dotenv

# Load environment variables from project root
project_root = Path(__file__).parent.parent
env_file = project_root / ".env"
load_dotenv(dotenv_path=env_file)

# Import Groq
try:
    from groq import Groq
except ImportError:
    raise ImportError(
        "groq is not installed. Install it with: pip install groq"
    )

# Import pydub for audio processing
try:
    from pydub import AudioSegment
except ImportError:
    raise ImportError(
        "pydub is not installed. Install it with: pip install pydub"
    )

# Import zhconv for Chinese conversion (optional)
try:
    import zhconv
    ZHCONV_AVAILABLE = True
except ImportError:
    ZHCONV_AVAILABLE = False
    print("Warning: zhconv not installed. Chinese conversion will be skipped.")
    print("Install it with: pip install zhconv")


def extract_audio_segment(
    input_path: Union[str, Path],
    output_path: Union[str, Path],
    duration_minutes: float = 5.0,
    start_minutes: float = 0.0,
    speed_multiplier: float = 1.0
) -> Path:
    """
    Extract a segment from an audio file, optionally with speed adjustment.
    
    Uses pydub if available, otherwise falls back to ffmpeg directly.
    
    Args:
        input_path: Path to the input audio file
        output_path: Path to save the extracted segment
        duration_minutes: Duration in minutes to extract
        start_minutes: Start time in minutes (0.0 = from beginning)
        speed_multiplier: Speed multiplier (1.0 = normal, 1.5 = 1.5x speed, 2.0 = 2x speed)
                         Note: Speeding up audio may reduce transcription quality.
        
    Returns:
        Path to the extracted audio file
    """
    input_path = Path(input_path)
    output_path = Path(output_path)
    
    if not input_path.exists():
        raise FileNotFoundError(f"Audio file not found: {input_path}")
    
    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Calculate duration in seconds for ffmpeg
    duration_seconds = duration_minutes * 60
    start_seconds = start_minutes * 60
    
    # Try using pydub first
    try:
        print(f"Loading audio file: {input_path}")
        # Try different audio formats
        if input_path.suffix.lower() == '.mp3':
            audio = AudioSegment.from_mp3(str(input_path))
        elif input_path.suffix.lower() == '.wav':
            audio = AudioSegment.from_wav(str(input_path))
        else:
            # Try to load with ffmpeg
            audio = AudioSegment.from_file(str(input_path))
        
        # Calculate start and end in milliseconds
        start_ms = int(start_minutes * 60 * 1000)
        duration_ms = int(duration_minutes * 60 * 1000)
        end_ms = start_ms + duration_ms
        
        # Extract the segment from start to end
        if start_minutes > 0:
            print(f"Extracting {duration_minutes} minutes starting from {start_minutes} minutes ({start_ms} ms to {end_ms} ms)...")
        else:
            print(f"Extracting first {duration_minutes} minutes ({duration_ms} ms)...")
        segment = audio[start_ms:end_ms]
        
        # Apply speed adjustment if needed
        if speed_multiplier != 1.0:
            print(f"Adjusting speed to {speed_multiplier}x...")
            segment = segment.speedup(playback_speed=speed_multiplier)
            print(f"  Original duration: {len(segment) / 1000 / speed_multiplier:.2f}s")
            print(f"  New duration: {len(segment) / 1000:.2f}s")
            print("  Warning: Speed adjustment may affect transcription quality!")
        
        # Export the segment
        print(f"Exporting segment to: {output_path}")
        # Export in the requested format (MP3 is smaller, WAV is uncompressed)
        if output_path.suffix.lower() == '.wav':
            segment.export(str(output_path), format="wav")
        else:
            segment.export(str(output_path), format="mp3")
        
        print(f"Extracted {len(segment) / 1000:.2f} seconds of audio")
        return output_path
        
    except (FileNotFoundError, OSError) as e:
        # Fallback to ffmpeg directly
        print(f"pydub failed (likely missing ffmpeg): {e}")
        print("Falling back to ffmpeg directly...")
        
        # Check if ffmpeg is available
        try:
            subprocess.run(
                ["ffmpeg", "-version"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True
            )
        except (FileNotFoundError, subprocess.CalledProcessError):
            raise RuntimeError(
                "ffmpeg is not installed or not in PATH. "
                "Please install ffmpeg:\n"
                "  Ubuntu/Debian: sudo apt-get install ffmpeg\n"
                "  macOS: brew install ffmpeg\n"
                "  Windows: Download from https://ffmpeg.org/download.html"
            )
        
        # Use ffmpeg to extract the segment
        if start_minutes > 0:
            print(f"Extracting {duration_minutes} minutes starting from {start_minutes} minutes using ffmpeg...")
        else:
            print(f"Extracting first {duration_minutes} minutes using ffmpeg...")
        if speed_multiplier != 1.0:
            print(f"Adjusting speed to {speed_multiplier}x...")
            print("  Warning: Speed adjustment may affect transcription quality!")
        print(f"Exporting segment to: {output_path}")
        
        # Build ffmpeg command
        if speed_multiplier != 1.0:
            if speed_multiplier < 0.5 or speed_multiplier > 2.0:
                atempo_value = min(max(speed_multiplier, 0.5), 2.0)
                filter_complex = f"atempo={atempo_value}"
            else:
                filter_complex = f"atempo={speed_multiplier}"
            
            cmd = [
                "ffmpeg",
                "-i", str(input_path),
                "-ss", str(start_seconds),
                "-t", str(duration_seconds),
                "-filter:a", filter_complex,
                "-acodec", "libmp3lame" if output_path.suffix.lower() == '.mp3' else "pcm_s16le",
                "-y",
                str(output_path)
            ]
        else:
            cmd = [
                "ffmpeg",
                "-i", str(input_path),
                "-ss", str(start_seconds),
                "-t", str(duration_seconds),
                "-c", "copy",
                "-y",
                str(output_path)
            ]
        
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        if result.returncode != 0:
            if speed_multiplier == 1.0:
                print("Copy codec failed, trying with re-encoding...")
                cmd = [
                    "ffmpeg",
                    "-i", str(input_path),
                    "-ss", str(start_seconds),
                    "-t", str(duration_seconds),
                    "-acodec", "libmp3lame" if output_path.suffix.lower() == '.mp3' else "pcm_s16le",
                    "-y",
                    str(output_path)
                ]
                result = subprocess.run(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
        
        if result.returncode != 0:
            raise RuntimeError(
                f"ffmpeg failed to extract audio segment:\n"
                f"Command: {' '.join(cmd)}\n"
                f"Error: {result.stderr}"
            )
        
        print(f"Extracted {duration_seconds:.2f} seconds of audio using ffmpeg")
        return output_path


def convert_verbose_json_to_srt(verbose_json: dict) -> str:
    """
    Convert Groq verbose_json response to SRT format.
    
    Args:
        verbose_json: The verbose_json response from Groq API
        
    Returns:
        SRT formatted string
    """
    srt_lines = []
    segment_index = 1
    
    # Check if response has segments
    if 'segments' in verbose_json:
        segments = verbose_json['segments']
    elif isinstance(verbose_json, dict) and 'segments' in verbose_json:
        segments = verbose_json['segments']
    else:
        # Fallback: try to extract text if no segments
        text = verbose_json.get('text', '')
        if text:
            srt_lines.append("1")
            srt_lines.append("00:00:00,000 --> 00:00:01,000")
            srt_lines.append(text)
            srt_lines.append("")
        return '\n'.join(srt_lines)
    
    for segment in segments:
        # Extract timing information
        start = segment.get('start', 0)
        end = segment.get('end', start + 1)
        text = segment.get('text', '').strip()
        
        if not text:
            continue
        
        # Convert seconds to SRT timestamp format (HH:MM:SS,mmm)
        def format_timestamp(seconds: float) -> str:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            secs = int(seconds % 60)
            millis = int((seconds % 1) * 1000)
            return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"
        
        srt_lines.append(str(segment_index))
        srt_lines.append(f"{format_timestamp(start)} --> {format_timestamp(end)}")
        srt_lines.append(text)
        srt_lines.append("")
        segment_index += 1
    
    return '\n'.join(srt_lines)


def scale_srt_timestamps(srt_content: str, speed_multiplier: float) -> str:
    """
    Scale SRT timestamps back to original timeline after speed adjustment.
    
    Args:
        srt_content: SRT file content as string
        speed_multiplier: Speed multiplier used (e.g., 2.0 for 2x speed)
        
    Returns:
        SRT content with scaled timestamps
    """
    if speed_multiplier == 1.0:
        return srt_content
    
    def scale_timestamp(match):
        """Scale a single timestamp (HH:MM:SS,mmm format)."""
        hours = int(match.group(1))
        minutes = int(match.group(2))
        seconds = int(match.group(3))
        milliseconds = int(match.group(4))
        
        total_ms = (hours * 3600 + minutes * 60 + seconds) * 1000 + milliseconds
        scaled_ms = int(total_ms * speed_multiplier)
        
        scaled_hours = scaled_ms // 3600000
        scaled_ms %= 3600000
        scaled_minutes = scaled_ms // 60000
        scaled_ms %= 60000
        scaled_seconds = scaled_ms // 1000
        scaled_milliseconds = scaled_ms % 1000
        
        return f"{scaled_hours:02d}:{scaled_minutes:02d}:{scaled_seconds:02d},{scaled_milliseconds:03d}"
    
    pattern = r'(\d{2}):(\d{2}):(\d{2}),(\d{3})'
    
    def scale_timestamp_line(line):
        """Scale both timestamps in a timestamp line."""
        return re.sub(pattern, scale_timestamp, line)
    
    lines = srt_content.split('\n')
    scaled_lines = []
    
    for line in lines:
        if '-->' in line:
            scaled_lines.append(scale_timestamp_line(line))
        else:
            scaled_lines.append(line)
    
    return '\n'.join(scaled_lines)


def convert_to_traditional_chinese(text: str) -> str:
    """
    Convert simplified Chinese to traditional Chinese.
    
    Args:
        text: Text that may contain simplified Chinese characters
        
    Returns:
        Text with all Chinese characters converted to traditional Chinese
    """
    if not ZHCONV_AVAILABLE:
        return text  # Return as-is if zhconv is not available
    
    try:
        # Convert simplified Chinese (zh-cn) to traditional Chinese (zh-tw)
        return zhconv.convert(text, 'zh-tw')
    except Exception as e:
        print(f"Warning: Failed to convert Chinese text: {e}")
        return text  # Return original text on error


def convert_json_to_traditional_chinese(data: Union[dict, str]) -> Union[dict, str]:
    """
    Recursively convert all Chinese text in a JSON structure to traditional Chinese.
    
    Args:
        data: Dictionary or JSON string containing transcription data
        
    Returns:
        Dictionary or string with all Chinese text converted to traditional
    """
    if not ZHCONV_AVAILABLE:
        return data
    
    # If it's a string, try to parse as JSON first
    if isinstance(data, str):
        try:
            parsed = json.loads(data)
            converted = convert_json_to_traditional_chinese(parsed)
            return json.dumps(converted, indent=2, ensure_ascii=False, default=str)
        except (json.JSONDecodeError, TypeError):
            # Not JSON, just convert the string directly
            return convert_to_traditional_chinese(data)
    
    # If it's a dictionary, recursively process
    if isinstance(data, dict):
        result = {}
        for key, value in data.items():
            if isinstance(value, str):
                # Convert string values
                result[key] = convert_to_traditional_chinese(value)
            elif isinstance(value, (dict, list)):
                # Recursively process nested structures
                result[key] = convert_json_to_traditional_chinese(value)
            else:
                # Keep other types as-is
                result[key] = value
        return result
    
    # If it's a list, process each item
    if isinstance(data, list):
        return [convert_json_to_traditional_chinese(item) for item in data]
    
    # For other types, return as-is
    return data


def convert_srt_to_traditional_chinese(srt_content: str) -> str:
    """
    Convert Chinese text in SRT file to traditional Chinese.
    Only converts subtitle text, preserves timestamps and formatting.
    
    Args:
        srt_content: SRT file content as string
        
    Returns:
        SRT content with all Chinese text converted to traditional
    """
    if not ZHCONV_AVAILABLE:
        return srt_content
    
    lines = srt_content.split('\n')
    converted_lines = []
    
    for line in lines:
        line_stripped = line.strip()
        # Skip empty lines, subtitle numbers, and timestamp lines
        if not line_stripped or line_stripped.isdigit() or '-->' in line:
            converted_lines.append(line)
        else:
            # This is a subtitle text line, convert it
            converted_lines.append(convert_to_traditional_chinese(line))
    
    return '\n'.join(converted_lines)


def test_groq_whisper_transcription(
    audio_path: Union[str, Path] = "./data/downloads/Gooaye 股癌/0616_EP616 _ 🥚.mp3",
    output_path: Optional[Union[str, Path]] = None,
    output_dir: Union[str, Path] = "data/test_transcript",
    duration_minutes: float = 5.0,
    start_minutes: float = 0.0,
    speed_multiplier: float = 1.0,
    model: str = "whisper-large-v3-turbo",
    response_format: str = "verbose_json",
    prompt: Optional[str] = None,
    temperature: float = 0.0,
    timestamp_granularities: Optional[List[str]] = None,
    use_mp3: bool = True  # Use MP3 instead of WAV to reduce file size
) -> Union[str, dict]:
    """
    Test Groq Whisper transcription API.
    
    Args:
        audio_path: Path to the input audio file
        output_path: Path to save the transcription output (optional)
        output_dir: Directory to save output files (if output_path not specified)
        duration_minutes: Duration in minutes to extract and transcribe
        start_minutes: Start time in minutes (0.0 = from beginning)
        speed_multiplier: Speed multiplier for audio (1.0 = normal)
        model: Whisper model to use (default: "whisper-large-v3-turbo")
        response_format: Output format - "json", "text", "srt", "verbose_json", or "vtt"
        prompt: Optional text to guide the model. Use for:
            - Providing context (e.g., technical terms, proper nouns)
            - Continuing from a previous audio segment
            - Note: Prompt text may appear in the transcription output, so avoid using
              descriptive sentences that you don't want in the final transcript
        temperature: Sampling temperature between 0 and 1 (default: 0.0)
        timestamp_granularities: List of granularities - ["word", "segment"] (requires verbose_json)
        use_mp3: If True, use MP3 format (smaller file size). If False, use WAV (uncompressed, larger)
        
    Returns:
        Transcription text, SRT content, or JSON dict depending on response_format
    """
    audio_path = Path(audio_path)
    project_root = Path(__file__).parent.parent
    
    # Resolve relative paths
    if not audio_path.is_absolute():
        audio_path = project_root / audio_path
    
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")
    
    # Create temporary file for the extracted segment
    # Use MP3 by default to reduce file size (Groq accepts both MP3 and WAV)
    suffix = ".mp3" if use_mp3 else ".wav"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temp_file:
        temp_audio_path = Path(temp_file.name)
    
    try:
        # Extract the audio segment
        print(f"\n{'='*60}")
        print("Step 1: Extracting audio segment")
        print(f"{'='*60}")
        extracted_path = extract_audio_segment(
            audio_path,
            temp_audio_path,
            duration_minutes,
            start_minutes,
            speed_multiplier
        )
        
        # Check file size before uploading (Groq free tier limit: 25MB)
        file_size_bytes = extracted_path.stat().st_size
        file_size_mb = file_size_bytes / (1024 * 1024)
        max_size_mb = 25.0
        max_size_bytes = max_size_mb * 1024 * 1024
        
        print(f"\nExtracted file size: {file_size_mb:.2f} MB ({file_size_bytes:,} bytes)")
        print(f"File format: {extracted_path.suffix.upper()}")
        
        if file_size_bytes > max_size_bytes:
            error_msg = (
                f"File size ({file_size_mb:.2f} MB) exceeds Groq's free tier limit of {max_size_mb} MB.\n"
                f"Solutions:\n"
                f"  1. Reduce duration_minutes (currently {duration_minutes} minutes)\n"
                f"  2. Use MP3 format instead of WAV (set use_mp3=True)\n"
                f"  3. Use speed_multiplier > 1.0 to reduce processed duration"
            )
            raise ValueError(error_msg)
        elif file_size_mb > max_size_mb * 0.9:  # Warn if > 90% of limit
            print(f"⚠️  Warning: File size is {file_size_mb:.2f} MB, close to the {max_size_mb} MB limit!")
            if not use_mp3:
                print("💡 Tip: Consider using MP3 format (use_mp3=True) to reduce file size")
        
        # Initialize Groq client
        print(f"\n{'='*60}")
        print("Step 2: Initializing Groq client")
        print(f"{'='*60}")
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError(
                "GROQ_API_KEY not found in environment variables. "
                "Please set it in your .env file or environment."
            )
        
        client = Groq(api_key=api_key)
        print("Groq client initialized successfully")
        
        # Prepare transcription parameters
        print(f"\n{'='*60}")
        print("Step 3: Transcribing audio with Groq Whisper API")
        print(f"{'='*60}")
        print(f"Model: {model}")
        print(f"Response format: {response_format}")
        if prompt:
            print(f"Prompt: {prompt[:50]}...")
        if timestamp_granularities:
            print(f"Timestamp granularities: {timestamp_granularities}")
        print(f"Temperature: {temperature}")
        
        # Open audio file and transcribe
        with open(extracted_path, "rb") as audio_file:
            transcription_params = {
                "file": audio_file,
                "model": model,
                "response_format": response_format,
                "temperature": temperature
            }
            
            if prompt:
                transcription_params["prompt"] = prompt
            
            if timestamp_granularities:
                transcription_params["timestamp_granularities"] = timestamp_granularities
            
            print("\nSending request to Groq API...")
            transcription = client.audio.transcriptions.create(**transcription_params)
        
        # Display cost information (Groq pricing may vary)
        print(f"\n{'='*60}")
        print("Transcription Information")
        print(f"{'='*60}")
        print(f"Original audio duration: {duration_minutes:.2f} minutes")
        if speed_multiplier != 1.0:
            processed_duration_minutes = duration_minutes / speed_multiplier
            print(f"Speed multiplier: {speed_multiplier}x")
            print(f"Processed audio duration: {processed_duration_minutes:.2f} minutes")
        else:
            print(f"Processed audio duration: {duration_minutes:.2f} minutes")
        print(f"Uploaded file size: {file_size_mb:.2f} MB ({file_size_bytes:,} bytes)")
        print(f"File size limit: {max_size_mb} MB (Groq free tier)")
        print("\nNote: Check your Groq dashboard for usage and billing information.")
        
        # Get the transcription content
        transcription_dict = None  # Store dict for verbose_json format
        if response_format == "text":
            transcription_text = transcription.text
        elif response_format == "verbose_json":
            # Convert to dict if needed
            if hasattr(transcription, 'model_dump'):
                transcription_dict = transcription.model_dump()
            elif hasattr(transcription, 'dict'):
                transcription_dict = transcription.dict()
            else:
                transcription_dict = dict(transcription)
            
            # Convert to SRT if requested
            if output_path and str(output_path).endswith('.srt'):
                transcription_text = convert_verbose_json_to_srt(transcription_dict)
            else:
                transcription_text = json.dumps(transcription_dict, indent=2, ensure_ascii=False, default=str)
        elif response_format in ["json", "srt", "vtt"]:
            transcription_text = str(transcription)
        else:
            # Fallback
            if hasattr(transcription, 'text'):
                transcription_text = transcription.text
            else:
                transcription_text = str(transcription)
        
        # Scale SRT timestamps back to original timeline if speed was adjusted
        if (response_format == "srt" or (response_format == "verbose_json" and output_path and str(output_path).endswith('.srt'))) and speed_multiplier != 1.0:
            print(f"\nScaling SRT timestamps by {speed_multiplier}x to match original audio timeline...")
            transcription_text = scale_srt_timestamps(transcription_text, speed_multiplier)
            print("SRT timestamps scaled successfully.")
        
        # Convert simplified Chinese to traditional Chinese (post-processing)
        if ZHCONV_AVAILABLE:
            print(f"\n{'='*60}")
            print("Step 5: Converting to Traditional Chinese")
            print(f"{'='*60}")
            if response_format == "verbose_json" and transcription_dict is not None:
                # For verbose_json, convert the dict structure
                transcription_dict = convert_json_to_traditional_chinese(transcription_dict)
                # Rebuild transcription_text from converted dict
                if output_path and str(output_path).endswith('.srt'):
                    transcription_text = convert_verbose_json_to_srt(transcription_dict)
                else:
                    transcription_text = json.dumps(transcription_dict, indent=2, ensure_ascii=False, default=str)
            elif response_format == "srt" or (output_path and str(output_path).endswith('.srt')):
                # SRT format
                transcription_text = convert_srt_to_traditional_chinese(transcription_text)
            else:
                # Plain text or other formats
                transcription_text = convert_to_traditional_chinese(transcription_text)
            print("Conversion to Traditional Chinese completed.")
        else:
            print("\n⚠️  Warning: zhconv not available. Skipping Chinese conversion.")
            print("   Install it with: pip install zhconv")
        
        # Save output to file
        if output_path is None:
            audio_stem = audio_path.stem
            output_dir = project_root / output_dir
            output_dir.mkdir(parents=True, exist_ok=True)
            
            if response_format == "verbose_json":
                extension = "json"
            elif response_format == "srt":
                extension = "srt"
            else:
                extension = "txt"
            
            speed_suffix = f"_{speed_multiplier}x" if speed_multiplier != 1.0 else ""
            start_suffix = f"_from{start_minutes}min" if start_minutes > 0 else ""
            output_path = output_dir / f"{audio_stem}_groq_{duration_minutes}min{start_suffix}{speed_suffix}.{extension}"
        else:
            output_path = Path(output_path)
            if not output_path.is_absolute():
                output_path = project_root / output_path
            output_path.parent.mkdir(parents=True, exist_ok=True)
        
        print(f"\n{'='*60}")
        print("Step 4: Saving transcription")
        print(f"{'='*60}")
        print(f"Saving to: {output_path}")
        
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(transcription_text)
        
        print("Transcription saved successfully!")
        print(f"Output file size: {output_path.stat().st_size} bytes")
        
        # Display preview of transcription
        print(f"\n{'='*60}")
        print("Transcription Preview (first 500 characters):")
        print(f"{'='*60}")
        if isinstance(transcription_text, dict):
            preview = json.dumps(transcription_text, indent=2, ensure_ascii=False, default=str)[:500]
        else:
            preview = transcription_text[:500]
        print(preview)
        if len(str(transcription_text)) > 500:
            print(f"\n... (truncated, total length: {len(str(transcription_text))} characters)")
        
        return transcription_text
        
    finally:
        # Clean up temporary file
        if temp_audio_path.exists():
            temp_audio_path.unlink()
            print(f"\nCleaned up temporary file: {temp_audio_path}")


def main():
    """Main function to run the test."""
    print("Groq Whisper Transcription Test")
    print("=" * 60)
    
    # Test with the specified audio file
    audio_file = "./data/downloads/Gooaye 股癌/0616_EP616 _ 🥚.mp3"
    
    # Test parameters: 20-25 minutes (start=20, duration=5)
    start_minutes = 20.0
    duration_minutes = 5.0
    
    try:
        # Test with verbose_json format (includes timestamps)
        print("\n" + "=" * 60)
        print("TEST: Groq Whisper Transcription (verbose_json)")
        print("=" * 60)
        transcription = test_groq_whisper_transcription(
            audio_path=audio_file,
            duration_minutes=duration_minutes,
            start_minutes=start_minutes,
            speed_multiplier=1.0,
            model="whisper-large-v3-turbo",
            response_format="verbose_json",
            prompt="繁體",  # Specify Traditional Chinese script
            temperature=0.0,
            timestamp_granularities=["word", "segment"]
        )
        
        # Also save as SRT format
        print("\n" + "=" * 60)
        print("Converting to SRT format...")
        print("=" * 60)
        project_root = Path(__file__).parent.parent
        audio_stem = Path(audio_file).stem
        output_dir = project_root / "data/test_transcript"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Convert verbose_json to SRT
        if isinstance(transcription, str):
            try:
                transcription_dict = json.loads(transcription)
            except (ValueError, json.JSONDecodeError):
                transcription_dict = {}
        else:
            transcription_dict = transcription
        
        srt_content = convert_verbose_json_to_srt(transcription_dict)
        srt_path = output_dir / f"{audio_stem}_groq_{duration_minutes}min_from{start_minutes}min.srt"
        
        with open(srt_path, "w", encoding="utf-8") as f:
            f.write(srt_content)
        
        print(f"SRT file saved to: {srt_path}")
        
        print("\n" + "=" * 60)
        print("Test completed successfully!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\nError during transcription: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())

