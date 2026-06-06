#!/usr/bin/env python3
"""
Test script for Whisper API chunking functionality.

This script tests the chunking feature by:
1. Creating a 5MB audio file (or using existing)
2. Chunking it into 5 x 1MB pieces
3. Transcribing chunks separately and combining
4. Transcribing the full 5MB file directly
5. Comparing results for correctness
"""

import subprocess
from pathlib import Path
from typing import Dict, List, Optional

from dotenv import load_dotenv

# Load environment variables from project root
project_root = Path(__file__).parent.parent
env_file = project_root / ".env"
load_dotenv(dotenv_path=env_file)

# Add project root to Python path
import sys

sys.path.insert(0, str(project_root))

# Import OpenAI
try:
    from openai import OpenAI
except ImportError:
    raise ImportError(
        "openai is not installed. Install it with: pip install openai"
    )

# Import WhisperService
from src.service.speech_to_text import WhisperService


def transcribe_with_chunking(
    audio_path: Path,
    chunk_size_mb: float = 1.0,
    language: Optional[str] = None
) -> Dict:
    """
    Transcribe audio file using chunking approach.
    
    Args:
        audio_path: Path to audio file
        chunk_size_mb: Size of each chunk in MB
        language: Optional language code
        
    Returns:
        Dictionary with text, sentences, and words
    """
    print(f"\n{'='*60}")
    print("Transcribing with CHUNKING approach")
    print(f"{'='*60}")
    
    # Create WhisperService with custom chunking settings
    service = WhisperService(
        max_file_size_mb=1.0,  # Force chunking for files > 1MB
        chunk_size_mb=chunk_size_mb,
        chunk_overlap_seconds=2.0,
        language=language
    )
    
    result = service.transcribe(audio_path, language=language)
    
    print("\nChunking transcription results:")
    print(f"  Total sentences: {len(result.get('sentences', []))}")
    print(f"  Total text length: {len(result.get('text', ''))} characters")
    
    return result


def transcribe_direct(
    audio_path: Path,
    language: Optional[str] = None
) -> Dict:
    """
    Transcribe audio file directly without chunking.
    
    Args:
        audio_path: Path to audio file
        language: Optional language code
        
    Returns:
        Dictionary with text, sentences, and words
    """
    print(f"\n{'='*60}")
    print("Transcribing with DIRECT approach")
    print(f"{'='*60}")
    
    # Create WhisperService with high limit to avoid chunking
    service = WhisperService(
        max_file_size_mb=100.0,  # High limit to avoid chunking
        language=language
    )
    
    result = service.transcribe(audio_path, language=language)
    
    print("\nDirect transcription results:")
    print(f"  Total sentences: {len(result.get('sentences', []))}")
    print(f"  Total text length: {len(result.get('text', ''))} characters")
    
    return result


def compare_transcriptions(
    chunked_result: Dict,
    direct_result: Dict,
    chunked_srt_path: Optional[Path] = None,
    direct_srt_path: Optional[Path] = None
) -> None:
    """
    Compare chunked and direct transcription results.
    
    Args:
        chunked_result: Result from chunked transcription
        direct_result: Result from direct transcription
        chunked_srt_path: Optional path to save chunked SRT
        direct_srt_path: Optional path to save direct SRT
    """
    print(f"\n{'='*60}")
    print("Comparison Results")
    print(f"{'='*60}")
    
    chunked_sentences = chunked_result.get('sentences', [])
    direct_sentences = direct_result.get('sentences', [])
    
    chunked_text = chunked_result.get('text', '')
    direct_text = direct_result.get('text', '')
    
    # Basic statistics
    print("\nSentence Count:")
    print(f"  Chunked: {len(chunked_sentences)}")
    print(f"  Direct:  {len(direct_sentences)}")
    print(f"  Difference: {abs(len(chunked_sentences) - len(direct_sentences))}")
    
    print("\nText Length:")
    print(f"  Chunked: {len(chunked_text)} characters")
    print(f"  Direct:  {len(direct_text)} characters")
    print(f"  Difference: {abs(len(chunked_text) - len(direct_text))} characters")
    
    # Calculate similarity
    def extract_text_from_sentences(sentences: List[Dict]) -> str:
        """Extract text content from sentences."""
        return ' '.join(s.get('content', '') for s in sentences)
    
    chunked_text_from_sentences = extract_text_from_sentences(chunked_sentences)
    direct_text_from_sentences = extract_text_from_sentences(direct_sentences)
    
    # Simple character-level similarity
    chunked_chars = set(chunked_text_from_sentences.replace(' ', ''))
    direct_chars = set(direct_text_from_sentences.replace(' ', ''))
    common_chars = chunked_chars & direct_chars
    similarity = len(common_chars) / len(direct_chars) * 100 if direct_chars else 0
    
    print(f"\nCharacter-level similarity: {similarity:.1f}%")
    
    # Check timestamp alignment
    if chunked_sentences and direct_sentences:
        chunked_first_start = chunked_sentences[0].get('start', 0)
        direct_first_start = direct_sentences[0].get('start', 0)
        chunked_last_end = chunked_sentences[-1].get('end', 0)
        direct_last_end = direct_sentences[-1].get('end', 0)
        
        print("\nTimestamp Alignment:")
        print("  First sentence start:")
        print(f"    Chunked: {chunked_first_start} ms")
        print(f"    Direct:  {direct_first_start} ms")
        print("  Last sentence end:")
        print(f"    Chunked: {chunked_last_end} ms")
        print(f"    Direct:  {direct_last_end} ms")
        print(f"  Total duration difference: {abs(chunked_last_end - direct_last_end)} ms")
    
    # Sample comparison
    print(f"\n{'='*60}")
    print("Sample Comparison (first 200 characters):")
    print(f"{'='*60}")
    print("\nChunked:")
    print(f"  {chunked_text_from_sentences[:200]}...")
    print("\nDirect:")
    print(f"  {direct_text_from_sentences[:200]}...")
    
    # Save SRT files if paths provided
    if chunked_srt_path:
        # Convert sentences back to SRT format
        
        def sentences_to_srt(sentences: List[Dict]) -> str:
            """Convert sentences back to SRT format."""
            def ms_to_srt_timestamp(total_ms: int) -> str:
                hours = total_ms // 3600000
                total_ms %= 3600000
                minutes = total_ms // 60000
                total_ms %= 60000
                seconds = total_ms // 1000
                milliseconds = total_ms % 1000
                return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"
            
            srt_lines = []
            for sentence in sentences:
                srt_lines.append(str(sentence["index"] + 1))
                start_ts = ms_to_srt_timestamp(sentence["start"])
                end_ts = ms_to_srt_timestamp(sentence["end"])
                srt_lines.append(f"{start_ts} --> {end_ts}")
                srt_lines.append(sentence["content"])
                srt_lines.append("")
            
            return "\n".join(srt_lines)
        
        chunked_srt_path.write_text(sentences_to_srt(chunked_sentences), encoding="utf-8")
        print(f"\n✓ Saved chunked SRT to: {chunked_srt_path}")
    
    if direct_srt_path:
        # For direct, we need to get the SRT from the service
        # For now, just save the sentences as SRT
        def sentences_to_srt(sentences: List[Dict]) -> str:
            def ms_to_srt_timestamp(total_ms: int) -> str:
                hours = total_ms // 3600000
                total_ms %= 3600000
                minutes = total_ms // 60000
                total_ms %= 60000
                seconds = total_ms // 1000
                milliseconds = total_ms % 1000
                return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"
            
            srt_lines = []
            for sentence in sentences:
                srt_lines.append(str(sentence["index"] + 1))
                start_ts = ms_to_srt_timestamp(sentence["start"])
                end_ts = ms_to_srt_timestamp(sentence["end"])
                srt_lines.append(f"{start_ts} --> {end_ts}")
                srt_lines.append(sentence["content"])
                srt_lines.append("")
            
            return "\n".join(srt_lines)
        
        direct_srt_path.write_text(sentences_to_srt(direct_sentences), encoding="utf-8")
        print(f"✓ Saved direct SRT to: {direct_srt_path}")


def extract_audio_segment(
    input_path: Path,
    output_path: Path,
    start_minutes: float,
    duration_minutes: float
) -> Path:
    """
    Extract a segment from an audio file using ffmpeg.
    
    Args:
        input_path: Path to input audio file
        output_path: Path to save extracted segment
        start_minutes: Start time in minutes
        duration_minutes: Duration in minutes
        
    Returns:
        Path to extracted audio file
    """
    input_path = Path(input_path)
    output_path = Path(output_path)
    
    if not input_path.exists():
        raise FileNotFoundError(f"Audio file not found: {input_path}")
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    start_seconds = start_minutes * 60
    duration_seconds = duration_minutes * 60
    
    # Use ffmpeg to extract segment
    cmd = [
        "ffmpeg",
        "-i", str(input_path),
        "-ss", str(start_seconds),
        "-t", str(duration_seconds),
        "-acodec", "libmp3lame",
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
    
    return output_path


def main():
    """Main function to run the chunking test."""
    print("Whisper API Chunking Test")
    print("=" * 60)
    
    # Test parameters
    source_audio = Path("./data/downloads/Gooaye 股癌/0616_EP616 _ 🥚.mp3")
    start_minutes = 20.0
    duration_minutes = 5.0
    chunk_size_mb = 1.0
    language = "zh"
    
    # Check if source audio exists
    if not source_audio.exists():
        print(f"Error: Source audio file not found: {source_audio}")
        print("Please update the source_audio path in the script.")
        return 1
    
    try:
        # Extract 20-25 minute segment as test audio
        test_output_dir = Path("./data/test_chunking")
        test_output_dir.mkdir(parents=True, exist_ok=True)
        test_audio_path = test_output_dir / "test_20-25min_audio.mp3"
        
        print(f"\nExtracting audio segment: {start_minutes}-{start_minutes + duration_minutes} minutes")
        extract_audio_segment(
            source_audio,
            test_audio_path,
            start_minutes,
            duration_minutes
        )
        
        actual_size_mb = test_audio_path.stat().st_size / (1024 * 1024)
        print(f"Created test audio file: {test_audio_path}")
        print(f"  Size: {actual_size_mb:.2f} MB")
        print(f"  Duration: {duration_minutes} minutes ({start_minutes}-{start_minutes + duration_minutes} min)")
        
        # Test 1: Transcribe with chunking (1MB chunks)
        chunked_result = transcribe_with_chunking(
            test_audio_path,
            chunk_size_mb=chunk_size_mb,
            language=language
        )
        
        # Test 2: Transcribe directly (no chunking)
        direct_result = transcribe_direct(
            test_audio_path,
            language=language
        )
        
        # Compare results
        chunked_srt_path = test_output_dir / "chunked_transcription.srt"
        direct_srt_path = test_output_dir / "direct_transcription.srt"
        
        compare_transcriptions(
            chunked_result,
            direct_result,
            chunked_srt_path,
            direct_srt_path
        )
        
        print("\n" + "=" * 60)
        print("Test completed successfully!")
        print("=" * 60)
        
        return 0
        
    except Exception as e:
        print(f"\nError during test: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())

