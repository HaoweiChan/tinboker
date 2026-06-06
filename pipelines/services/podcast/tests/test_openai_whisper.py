#!/usr/bin/env python3
"""
Test script for OpenAI Whisper speech-to-text API.

This script tests OpenAI's Whisper transcription API with a 5-minute audio sample.
It extracts the first 5 minutes from the audio file and transcribes it to SRT format.
"""

import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Union

from dotenv import load_dotenv

# Load environment variables from project root
project_root = Path(__file__).parent.parent
env_file = project_root / ".env"
load_dotenv(dotenv_path=env_file)

# Import OpenAI
try:
    from openai import OpenAI
except ImportError:
    raise ImportError(
        "openai is not installed. Install it with: pip install openai"
    )

# Import pydub for audio processing
try:
    from pydub import AudioSegment
except ImportError:
    raise ImportError(
        "pydub is not installed. Install it with: pip install pydub"
    )


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
                         Research shows 1.2x-1.5x has minimal quality impact.
        
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
        audio = AudioSegment.from_mp3(str(input_path))
        
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
            # pydub's speedup method changes playback speed without changing pitch
            # It uses frame rate manipulation
            segment = segment.speedup(playback_speed=speed_multiplier)
            print(f"  Original duration: {len(segment) / 1000 / speed_multiplier:.2f}s")
            print(f"  New duration: {len(segment) / 1000:.2f}s")
            print("  Warning: Speed adjustment may affect transcription quality!")
        
        # Export the segment
        print(f"Exporting segment to: {output_path}")
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
        # If speed adjustment is needed, we must re-encode (can't use -c copy)
        if speed_multiplier != 1.0:
            # Use atempo filter for speed adjustment (maintains pitch)
            # atempo can only handle 0.5-2.0 range, so for >2.0 we chain filters
            if speed_multiplier < 0.5 or speed_multiplier > 2.0:
                # Chain multiple atempo filters for values outside 0.5-2.0 range
                # For 2x, we can use atempo=2.0 directly
                atempo_value = min(max(speed_multiplier, 0.5), 2.0)
                filter_complex = f"atempo={atempo_value}"
            else:
                filter_complex = f"atempo={speed_multiplier}"
            
            cmd = [
                "ffmpeg",
                "-i", str(input_path),
                "-ss", str(start_seconds),  # Start time
                "-t", str(duration_seconds),  # Duration
                "-filter:a", filter_complex,
                "-acodec", "libmp3lame",
                "-y",
                str(output_path)
            ]
        else:
            # No speed adjustment - try copy first (faster)
            cmd = [
                "ffmpeg",
                "-i", str(input_path),
                "-ss", str(start_seconds),  # Start time
                "-t", str(duration_seconds),  # Duration
                "-c", "copy",  # Copy codec (faster, no re-encoding)
                "-y",  # Overwrite output file if exists
                str(output_path)
            ]
        
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        if result.returncode != 0:
            # If copy fails and we weren't already re-encoding, try with re-encoding
            if speed_multiplier == 1.0:
                print("Copy codec failed, trying with re-encoding...")
                cmd = [
                    "ffmpeg",
                    "-i", str(input_path),
                    "-ss", str(start_seconds),  # Start time
                    "-t", str(duration_seconds),  # Duration
                    "-acodec", "libmp3lame",  # MP3 encoder
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


def scale_srt_timestamps(srt_content: str, speed_multiplier: float) -> str:
    """
    Scale SRT timestamps back to original timeline after speed adjustment.
    
    When audio is sped up, the SRT timestamps are based on the sped-up duration.
    This function scales them back to match the original audio timeline.
    
    Args:
        srt_content: SRT file content as string
        speed_multiplier: Speed multiplier used (e.g., 2.0 for 2x speed)
                         All timestamps will be multiplied by this value
        
    Returns:
        SRT content with scaled timestamps
    """
    if speed_multiplier == 1.0:
        return srt_content  # No scaling needed
    
    def scale_timestamp(match):
        """Scale a single timestamp (HH:MM:SS,mmm format)."""
        hours = int(match.group(1))
        minutes = int(match.group(2))
        seconds = int(match.group(3))
        milliseconds = int(match.group(4))
        
        # Convert to total milliseconds
        total_ms = (hours * 3600 + minutes * 60 + seconds) * 1000 + milliseconds
        
        # Scale by speed multiplier
        scaled_ms = int(total_ms * speed_multiplier)
        
        # Convert back to HH:MM:SS,mmm
        scaled_hours = scaled_ms // 3600000
        scaled_ms %= 3600000
        scaled_minutes = scaled_ms // 60000
        scaled_ms %= 60000
        scaled_seconds = scaled_ms // 1000
        scaled_milliseconds = scaled_ms % 1000
        
        return f"{scaled_hours:02d}:{scaled_minutes:02d}:{scaled_seconds:02d},{scaled_milliseconds:03d}"
    
    # SRT timestamp pattern: HH:MM:SS,mmm --> HH:MM:SS,mmm
    # Match both start and end timestamps in the same line
    pattern = r'(\d{2}):(\d{2}):(\d{2}),(\d{3})'
    
    def scale_timestamp_line(line):
        """Scale both timestamps in a timestamp line."""
        return re.sub(pattern, scale_timestamp, line)
    
    # Process each line
    lines = srt_content.split('\n')
    scaled_lines = []
    
    for line in lines:
        # Check if this line contains timestamps
        if '-->' in line:
            scaled_lines.append(scale_timestamp_line(line))
        else:
            scaled_lines.append(line)
    
    return '\n'.join(scaled_lines)


def test_openai_whisper_transcription(
    audio_path: Union[str, Path] = "./data/downloads/Gooaye 股癌/0616_EP616 _ 🥚.mp3",
    output_path: Optional[Union[str, Path]] = None,
    output_dir: Union[str, Path] = "data/test_transcript",
    duration_minutes: float = 5.0,
    start_minutes: float = 0.0,
    speed_multiplier: float = 1.0,
    model: str = "whisper-1",
    response_format: str = "srt",
    language: Optional[str] = None,
    temperature: Optional[float] = None,
    prompt: Optional[str] = None
) -> str:
    """
    Test OpenAI Whisper transcription API.
    
    Args:
        audio_path: Path to the input audio file
        output_path: Path to save the transcription output (optional)
        output_dir: Directory to save output files (if output_path not specified)
        duration_minutes: Duration in minutes to extract and transcribe
        start_minutes: Start time in minutes (0.0 = from beginning)
        speed_multiplier: Speed multiplier for audio (1.0 = normal, 1.5 = 1.5x speed, 2.0 = 2x speed)
                         Note: Research shows 1.2x-1.5x has minimal quality impact (~1-2% WER increase).
                         Beyond 1.5x, quality degrades significantly. Speeding up reduces API costs.
        model: Whisper model to use (default: "whisper-1")
        response_format: Output format - "json", "text", "srt", "verbose_json", or "vtt"
        language: Language code (e.g., "zh" for Chinese, "en" for English)
        temperature: Sampling temperature between 0 and 1
        prompt: Optional text to guide the model's style or continue a previous audio segment
        
    Returns:
        Transcription text or SRT content
    """
    audio_path = Path(audio_path)
    project_root = Path(__file__).parent.parent
    
    # Resolve relative paths
    if not audio_path.is_absolute():
        audio_path = project_root / audio_path
    
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")
    
    # Create temporary file for the extracted segment
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as temp_file:
        temp_audio_path = Path(temp_file.name)
    
    try:
        # Extract the first N minutes
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
        
        # Initialize OpenAI client
        print(f"\n{'='*60}")
        print("Step 2: Initializing OpenAI client")
        print(f"{'='*60}")
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError(
                "OPENAI_API_KEY not found in environment variables. "
                "Please set it in your .env file or environment."
            )
        
        client = OpenAI(api_key=api_key)
        print("OpenAI client initialized successfully")
        
        # Prepare transcription parameters
        print(f"\n{'='*60}")
        print("Step 3: Transcribing audio with Whisper API")
        print(f"{'='*60}")
        print(f"Model: {model}")
        print(f"Response format: {response_format}")
        if language:
            print(f"Language: {language}")
        if temperature is not None:
            print(f"Temperature: {temperature}")
        if prompt:
            print(f"Prompt: {prompt[:50]}...")
        
        # Open audio file and transcribe
        with open(extracted_path, "rb") as audio_file:
            transcription_params = {
                "model": model,
                "file": audio_file,
                "response_format": response_format
            }
            
            if language:
                transcription_params["language"] = language
            if temperature is not None:
                transcription_params["temperature"] = temperature
            if prompt:
                transcription_params["prompt"] = prompt
            
            print("\nSending request to OpenAI API...")
            transcription = client.audio.transcriptions.create(**transcription_params)
        
        # Extract usage and cost information
        # Note: OpenAI Whisper API responses typically don't include usage/cost in the response body
        # Usage is tracked on OpenAI's side and visible in your dashboard
        # However, we can calculate estimated cost based on audio duration
        
        # Calculate estimated cost based on audio duration
        # OpenAI Whisper API pricing: $0.006 per minute (as of 2024)
        # Note: Cost is based on the processed audio duration (after speed adjustment)
        # When audio is sped up, the processed duration is shorter, reducing cost
        WHISPER_COST_PER_MINUTE = 0.006
        # Processed duration = original duration / speed_multiplier
        # (e.g., 5 min at 2x speed = 2.5 min processed duration)
        processed_duration_minutes = duration_minutes / speed_multiplier if speed_multiplier > 0 else duration_minutes
        estimated_cost = processed_duration_minutes * WHISPER_COST_PER_MINUTE
        
        # Try to extract any usage information from response object
        usage_info = {}
        response_headers = {}
        
        # Check if response object has metadata
        if hasattr(transcription, '_response'):
            response = transcription._response
            if hasattr(response, 'headers'):
                response_headers = dict(response.headers)
                # Filter for relevant headers
                usage_info = {
                    k: v for k, v in response_headers.items()
                    if any(keyword in k.lower() for keyword in ['rate', 'usage', 'limit', 'request', 'remaining'])
                }
        
        # Also check response object attributes directly
        if hasattr(transcription, 'usage'):
            usage_info['usage'] = transcription.usage
        
        # Display cost information
        print(f"\n{'='*60}")
        print("Cost & Usage Information")
        print(f"{'='*60}")
        print(f"Original audio duration: {duration_minutes:.2f} minutes")
        if speed_multiplier != 1.0:
            print(f"Speed multiplier: {speed_multiplier}x")
            print(f"Processed audio duration: {processed_duration_minutes:.2f} minutes")
            cost_savings = (duration_minutes - processed_duration_minutes) * WHISPER_COST_PER_MINUTE
            savings_percent = (cost_savings / (duration_minutes * WHISPER_COST_PER_MINUTE)) * 100
            print(f"Cost savings from speed adjustment: ${cost_savings:.4f} USD ({savings_percent:.1f}% reduction)")
            
            # Quality impact warnings based on research
            if speed_multiplier <= 1.2:
                print("  Quality impact: Minimal (~1-2% WER increase expected)")
            elif speed_multiplier <= 1.5:
                print("  Quality impact: Low (~2-3% WER increase expected)")
            else:
                print("  Quality impact: SIGNIFICANT - Quality may degrade substantially!")
                print("  Recommendation: Use 1.2x-1.5x for best balance of cost and quality")
        else:
            print(f"Processed audio duration: {duration_minutes:.2f} minutes")
        print(f"Whisper API pricing: ${WHISPER_COST_PER_MINUTE} per minute")
        print(f"Estimated cost for this request: ${estimated_cost:.4f} USD")
        print("\nNote: Actual usage and billing are tracked by OpenAI.")
        print("      Check your OpenAI dashboard for detailed usage statistics.")
        
        if usage_info:
            print("\nResponse metadata found:")
            for key, value in usage_info.items():
                print(f"  {key}: {value}")
        
        if response_headers and not usage_info:
            # Show all headers if no usage-specific ones found
            print("\nResponse headers (showing rate-limit related):")
            relevant_headers = {
                k: v for k, v in response_headers.items()
                if any(keyword in k.lower() for keyword in ['x-', 'rate', 'limit', 'request'])
            }
            if relevant_headers:
                for key, value in relevant_headers.items():
                    print(f"  {key}: {value}")
            else:
                print("  (No usage-related headers found in response)")
        
        # Get the transcription content
        # Handle different response formats
        if response_format == "text":
            # For "text" format, the response has a .text attribute
            transcription_text = transcription.text
        elif response_format in ["srt", "vtt"]:
            # For "srt" and "vtt" formats, the response is a string directly
            transcription_text = str(transcription)
        elif response_format in ["json", "verbose_json"]:
            # For JSON formats, transcription is an object
            import json
            transcription_text = json.dumps(transcription.model_dump(), indent=2, ensure_ascii=False)
        else:
            # Fallback: try to get .text attribute, otherwise convert to string
            if hasattr(transcription, 'text'):
                transcription_text = transcription.text
            else:
                transcription_text = str(transcription)
        
        # Scale SRT timestamps back to original timeline if speed was adjusted
        if response_format == "srt" and speed_multiplier != 1.0:
            print(f"\nScaling SRT timestamps by {speed_multiplier}x to match original audio timeline...")
            transcription_text = scale_srt_timestamps(transcription_text, speed_multiplier)
            print("SRT timestamps scaled successfully.")
        
        # Save output to file
        if output_path is None:
            # Generate output filename based on input filename
            audio_stem = audio_path.stem
            output_dir = project_root / output_dir
            output_dir.mkdir(parents=True, exist_ok=True)
            
            extension = "srt" if response_format == "srt" else "txt"
            speed_suffix = f"_{speed_multiplier}x" if speed_multiplier != 1.0 else ""
            start_suffix = f"_from{start_minutes}min" if start_minutes > 0 else ""
            output_path = output_dir / f"{audio_stem}_whisper_{duration_minutes}min{start_suffix}{speed_suffix}.{extension}"
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
        preview = transcription_text[:500]
        print(preview)
        if len(transcription_text) > 500:
            print(f"\n... (truncated, total length: {len(transcription_text)} characters)")
        
        return transcription_text
        
    finally:
        # Clean up temporary file
        if temp_audio_path.exists():
            temp_audio_path.unlink()
            print(f"\nCleaned up temporary file: {temp_audio_path}")


def compare_transcriptions(
    normal_transcription: str,
    speed_transcription: str,
    normal_output_path: Path,
    speed_output_path: Path
) -> None:
    """
    Compare two transcriptions and display differences.
    
    Args:
        normal_transcription: Transcription from normal speed audio
        speed_transcription: Transcription from sped-up audio
        normal_output_path: Path to normal speed output file
        speed_output_path: Path to speed-adjusted output file
    """
    print(f"\n{'='*60}")
    print("Transcription Comparison")
    print(f"{'='*60}")
    
    # Extract text from SRT (remove timestamps and subtitle numbers)
    def extract_text_from_srt(srt_content: str) -> str:
        """Extract just the text content from SRT, removing timestamps."""
        lines = srt_content.split('\n')
        text_lines = []
        for line in lines:
            line = line.strip()
            # Skip empty lines, subtitle numbers, and timestamp lines
            if not line or line.isdigit() or '-->' in line:
                continue
            text_lines.append(line)
        return ' '.join(text_lines)
    
    normal_text = extract_text_from_srt(normal_transcription)
    speed_text = extract_text_from_srt(speed_transcription)
    
    # Basic statistics
    print("\nNormal Speed Transcription:")
    print(f"  File: {normal_output_path.name}")
    print(f"  Length: {len(normal_text)} characters")
    print(f"  Words (approx): {len(normal_text.split())}")
    
    print("\n2x Speed Transcription:")
    print(f"  File: {speed_output_path.name}")
    print(f"  Length: {len(speed_text)} characters")
    print(f"  Words (approx): {len(speed_text.split())}")
    
    # Calculate similarity (simple character-based)
    # For more accurate comparison, we'd need word-level alignment
    normal_chars = set(normal_text.replace(' ', ''))
    speed_chars = set(speed_text.replace(' ', ''))
    common_chars = normal_chars & speed_chars
    similarity = len(common_chars) / len(normal_chars) * 100 if normal_chars else 0
    
    print(f"\nCharacter-level similarity: {similarity:.1f}%")
    
    # Show first few differences (simple approach)
    print(f"\n{'='*60}")
    print("Sample Comparison (first 200 characters):")
    print(f"{'='*60}")
    print("\nNormal Speed:")
    print(f"  {normal_text[:200]}...")
    print("\n2x Speed:")
    print(f"  {speed_text[:200]}...")
    
    # Save comparison report
    # Create comparison filename based on normal output path
    comparison_name = normal_output_path.stem.replace("_1.0x", "").replace("_from20.0min", "_from20min")
    comparison_path = normal_output_path.parent / f"{comparison_name}_comparison.txt"
    with open(comparison_path, "w", encoding="utf-8") as f:
        f.write("Transcription Comparison Report\n")
        f.write("=" * 60 + "\n\n")
        f.write(f"Normal Speed: {normal_output_path.name}\n")
        f.write(f"2x Speed: {speed_output_path.name}\n\n")
        f.write(f"Normal Speed Length: {len(normal_text)} characters\n")
        f.write(f"2x Speed Length: {len(speed_text)} characters\n")
        f.write(f"Character-level similarity: {similarity:.1f}%\n\n")
        f.write("=" * 60 + "\n")
        f.write("Normal Speed Transcription:\n")
        f.write("=" * 60 + "\n")
        f.write(normal_text + "\n\n")
        f.write("=" * 60 + "\n")
        f.write("2x Speed Transcription:\n")
        f.write("=" * 60 + "\n")
        f.write(speed_text + "\n")
    
    print(f"\nComparison report saved to: {comparison_path}")


def main():
    """Main function to run the test."""
    print("OpenAI Whisper Transcription Test - Speed Comparison")
    print("=" * 60)
    
    # Test with the specified audio file
    audio_file = "./data/downloads/Gooaye 股癌/0616_EP616 _ 🥚.mp3"
    
    # Test parameters: 20-25 minutes (start=20, duration=5)
    start_minutes = 20.0
    duration_minutes = 5.0
    
    try:
        # Test 1: Normal speed (1.0x)
        print("\n" + "=" * 60)
        print("TEST 1: Normal Speed (1.0x)")
        print("=" * 60)
        normal_transcription = test_openai_whisper_transcription(
            audio_path=audio_file,
            duration_minutes=duration_minutes,
            start_minutes=start_minutes,
            speed_multiplier=1.0,
            model="whisper-1",
            response_format="srt",
            language="zh"  # Chinese language code
        )
        
        # Test 2: 2x speed
        print("\n" + "=" * 60)
        print("TEST 2: 2x Speed")
        print("=" * 60)
        speed_transcription = test_openai_whisper_transcription(
            audio_path=audio_file,
            duration_minutes=duration_minutes,
            start_minutes=start_minutes,
            speed_multiplier=2.0,
            model="whisper-1",
            response_format="srt",
            language="zh"  # Chinese language code
        )
        
        # Get the output paths (they're constructed in the function with same format)
        project_root = Path(__file__).parent.parent
        audio_stem = Path(audio_file).stem
        output_dir = project_root / "data/test_transcript"
        # Match the format used in test_openai_whisper_transcription
        normal_output_path = output_dir / f"{audio_stem}_whisper_{duration_minutes}min_from{start_minutes}min.srt"
        speed_output_path = output_dir / f"{audio_stem}_whisper_{duration_minutes}min_from{start_minutes}min_2.0x.srt"
        
        # Compare the two transcriptions
        compare_transcriptions(
            normal_transcription,
            speed_transcription,
            normal_output_path,
            speed_output_path
        )
        
        print("\n" + "=" * 60)
        print("All tests completed successfully!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\nError during transcription: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())

