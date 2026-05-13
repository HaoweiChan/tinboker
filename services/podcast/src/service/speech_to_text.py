#!/usr/bin/env python3
"""
Speech-to-Text Module

This module provides an abstract interface for speech-to-text services
and implementation for OpenAI Whisper API.
"""

import json
import os
import re
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from src.secrets_bootstrap import bootstrap

# Load secrets from GSM (idempotent — safe if already bootstrapped at entry point).
bootstrap()


class SpeechToTextService(ABC):
    """Abstract base class for speech-to-text services."""
    
    @abstractmethod
    def transcribe(self, audio_input: Union[str, Path, bytes], language: Optional[str] = None) -> Dict[str, Any]:
        """
        Transcribe an audio file or bytes to text with sentence-level timing.
        
        Args:
            audio_input: Path to the audio file (str or Path) or bytes of audio data
            language: Optional language code override
            
        Returns:
            Dictionary with keys:
                - "text": The transcribed text as a string
                - "sentences": List of sentence objects with timing (each sentence has: index, content, start, end)
                - "words": None (deprecated, kept for backward compatibility)
            
        Raises:
            FileNotFoundError: If the audio file doesn't exist
            Exception: If transcription fails
        """
        pass
    
    @abstractmethod
    def get_service_name(self) -> str:
        """Return the name of the service."""
        pass


def parse_srt_to_sentences(srt_content: str) -> List[Dict[str, Any]]:
    """
    Parse SRT content to extract sentences with timestamps.
    
    Args:
        srt_content: SRT file content as string
        
    Returns:
        List of sentence dictionaries with keys: index, content, start, end
        - index: int (0-based sentence index)
        - content: str (sentence text)
        - start: int (start time in milliseconds)
        - end: int (end time in milliseconds)
    """
    def srt_timestamp_to_ms(timestamp: str) -> int:
        """Convert SRT timestamp (HH:MM:SS,mmm) to milliseconds."""
        # Match pattern: HH:MM:SS,mmm
        match = re.match(r'(\d{2}):(\d{2}):(\d{2}),(\d{3})', timestamp)
        if not match:
            raise ValueError(f"Invalid SRT timestamp format: {timestamp}")
        
        hours = int(match.group(1))
        minutes = int(match.group(2))
        seconds = int(match.group(3))
        milliseconds = int(match.group(4))
        
        # Convert to total milliseconds
        total_ms = (hours * 3600 + minutes * 60 + seconds) * 1000 + milliseconds
        return total_ms
    
    sentences = []
    lines = srt_content.strip().split('\n')
    i = 0
    sentence_index = 0
    
    while i < len(lines):
        line = lines[i].strip()
        
        # Skip empty lines
        if not line:
            i += 1
            continue
        
        # Check if this is a subtitle number (digit only)
        if line.isdigit():
            # Next line should be timestamp
            if i + 1 < len(lines):
                timestamp_line = lines[i + 1].strip()
                # Check if it's a timestamp line (contains -->)
                if '-->' in timestamp_line:
                    # Parse timestamp line: HH:MM:SS,mmm --> HH:MM:SS,mmm
                    parts = timestamp_line.split('-->')
                    if len(parts) == 2:
                        start_timestamp = parts[0].strip()
                        end_timestamp = parts[1].strip()
                        
                        try:
                            start_ms = srt_timestamp_to_ms(start_timestamp)
                            end_ms = srt_timestamp_to_ms(end_timestamp)
                            
                            # Collect text lines until next empty line or subtitle number
                            content_lines = []
                            i += 2  # Skip number and timestamp lines
                            
                            while i < len(lines):
                                text_line = lines[i].strip()
                                # Stop at empty line or next subtitle number
                                if not text_line or text_line.isdigit():
                                    break
                                # Skip timestamp lines
                                if '-->' not in text_line:
                                    content_lines.append(text_line)
                                i += 1
                            
                            # Join content lines to form sentence
                            content = ' '.join(content_lines).strip()
                            
                            if content:  # Only add non-empty sentences
                                sentences.append({
                                    "index": sentence_index,
                                    "content": content,
                                    "start": start_ms,
                                    "end": end_ms
                                })
                                sentence_index += 1
                        except (ValueError, IndexError):
                            # Skip malformed entries
                            i += 1
                            continue
                    else:
                        i += 1
                else:
                    i += 1
            else:
                i += 1
        else:
            i += 1
    
    return sentences


class WhisperService(SpeechToTextService):
    """OpenAI Whisper speech-to-text service implementation."""
    
    def __init__(
        self, 
        api_key: Optional[str] = None, 
        language: Optional[str] = None,
        max_file_size_mb: float = 25.0,
        chunk_size_mb: float = 10.0,
        chunk_overlap_seconds: float = 2.0
    ):
        """
        Initialize Whisper service.
        
        Args:
            api_key: OpenAI API key. If None, will try to load from OPENAI_API_KEY env var.
            language: Optional language code (e.g., "en", "zh"). If None, auto-detection is used.
            max_file_size_mb: Maximum file size in MB before chunking is required (default: 25.0)
            chunk_size_mb: Size of each chunk in MB (default: 10.0)
            chunk_overlap_seconds: Overlap between chunks in seconds to avoid cutting mid-sentence (default: 2.0)
        """
        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError(
                "openai is not installed. Install it with: pip install openai"
            )
        
        # Get API key from parameter or environment variable
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        
        if not self.api_key:
            raise ValueError(
                "OpenAI API key is required. "
                "Set it in .env file as OPENAI_API_KEY or pass it to the constructor."
            )
        
        # Initialize OpenAI client
        self.client = OpenAI(api_key=self.api_key)
        self.language = language
        
        # Chunking configuration
        self.max_file_size_mb = max_file_size_mb
        self.chunk_size_mb = chunk_size_mb
        self.chunk_overlap_seconds = chunk_overlap_seconds
    
    def transcribe(self, audio_input: Union[str, Path, bytes], language: Optional[str] = None) -> Dict[str, Any]:
        """
        Transcribe an audio file or bytes using OpenAI Whisper API.
        
        Args:
            audio_input: Path to the audio file (str or Path) or bytes of audio data
            language: Optional language code override. If None, uses the language set in __init__ or auto-detection
            
        Returns:
            Dictionary with keys:
                - "text": The transcribed text as a string (concatenated sentences)
                - "sentences": List of sentence dictionaries with index, content, start, end
                - "words": None (deprecated, kept for backward compatibility)
            
        Raises:
            FileNotFoundError: If the audio file doesn't exist
            Exception: If transcription fails
        """
        # Use provided language or fall back to instance default
        lang = language or self.language
        
        # Handle bytes input - need to create temp file
        if isinstance(audio_input, bytes):
            import tempfile
            with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as temp_file:
                temp_path = Path(temp_file.name)
                temp_file.write(audio_input)
            
            try:
                # Transcribe the temp file
                result = self._transcribe_file(temp_path, lang)
            finally:
                # Clean up temp file
                if temp_path.exists():
                    temp_path.unlink()
            return result
        else:
            # Handle file path
            audio_path = Path(audio_input)
            if not audio_path.exists():
                raise FileNotFoundError(f"Audio file not found: {audio_path}")
            
            return self._transcribe_file(audio_path, lang)
    
    def _get_file_size(self, file_path: Path) -> int:
        """Get file size in bytes."""
        return file_path.stat().st_size
    
    def _should_chunk(self, file_path: Path) -> bool:
        """Check if file exceeds size limit and should be chunked."""
        file_size_bytes = self._get_file_size(file_path)
        max_size_bytes = self.max_file_size_mb * 1024 * 1024
        return file_size_bytes > max_size_bytes
    
    def _get_audio_duration(self, file_path: Path) -> float:
        """
        Get actual audio duration using ffprobe.
        
        Returns duration in seconds.
        """
        try:
            # Use ffprobe to get duration
            cmd = [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(file_path)
            ]
            
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            if result.returncode == 0:
                duration = float(result.stdout.strip())
                return duration
            else:
                # Fallback to estimation
                return self._estimate_audio_duration(file_path)
        except Exception:
            # Fallback to estimation
            return self._estimate_audio_duration(file_path)
    
    def _estimate_audio_duration(self, file_path: Path) -> float:
        """
        Estimate audio duration from file size (fallback method).
        
        This is a rough estimation. For MP3 files, assumes average bitrate.
        Returns duration in seconds.
        """
        file_size_bytes = self._get_file_size(file_path)
        file_size_mb = file_size_bytes / (1024 * 1024)
        
        # Rough estimation: assume average bitrate of 128 kbps for MP3
        # Duration (seconds) = (file_size_mb * 8) / bitrate_mbps
        # For 128 kbps = 0.128 Mbps
        estimated_duration_seconds = (file_size_mb * 8) / 0.128
        
        return estimated_duration_seconds
    
    def _chunk_audio_file(
        self, 
        audio_path: Path, 
        output_dir: Optional[Path] = None
    ) -> List[Tuple[Path, float]]:
        """
        Split audio file into chunks using ffmpeg.
        
        Args:
            audio_path: Path to the audio file
            output_dir: Directory to save chunks (if None, uses temp directory)
            
        Returns:
            List of tuples: (chunk_path, chunk_start_time_seconds)
        """
        import tempfile
        
        if output_dir is None:
            output_dir = Path(tempfile.gettempdir()) / "whisper_chunks"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        file_size_bytes = self._get_file_size(audio_path)
        file_size_mb = file_size_bytes / (1024 * 1024)
        total_duration = self._get_audio_duration(audio_path)
        
        # Calculate chunk duration based on chunk_size_mb
        # Duration ratio = chunk_size / total_size
        chunk_duration_ratio = self.chunk_size_mb / file_size_mb
        chunk_duration_seconds = total_duration * chunk_duration_ratio
        
        chunks = []
        current_start = 0.0
        chunk_index = 0
        
        while current_start < total_duration:
            chunk_path = output_dir / f"chunk_{chunk_index:04d}.mp3"
            
            # Extract chunk using ffmpeg (no overlap)
            cmd = [
                "ffmpeg",
                "-i", str(audio_path),
                "-ss", str(current_start),
                "-t", str(chunk_duration_seconds),
                "-acodec", "libmp3lame",
                "-y",
                str(chunk_path)
            ]
            
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            if result.returncode != 0:
                raise RuntimeError(
                    f"ffmpeg failed to create chunk {chunk_index}:\n"
                    f"Command: {' '.join(cmd)}\n"
                    f"Error: {result.stderr}"
                )
            
            chunks.append((chunk_path, current_start))
            
            # Move to next chunk
            current_start += chunk_duration_seconds
            chunk_index += 1
        
        return chunks
    
    def _combine_srt_chunks(
        self, 
        chunk_srt_list: List[Tuple[str, float]]
    ) -> str:
        """
        Combine multiple SRT contents with timestamp offsets.
        
        Args:
            chunk_srt_list: List of tuples (srt_content, chunk_start_time_seconds)
            
        Returns:
            Combined SRT content with corrected timestamps
        """
        def srt_timestamp_to_ms(timestamp: str) -> int:
            """Convert SRT timestamp (HH:MM:SS,mmm) to milliseconds."""
            match = re.match(r'(\d{2}):(\d{2}):(\d{2}),(\d{3})', timestamp)
            if not match:
                raise ValueError(f"Invalid SRT timestamp format: {timestamp}")
            
            hours = int(match.group(1))
            minutes = int(match.group(2))
            seconds = int(match.group(3))
            milliseconds = int(match.group(4))
            
            return (hours * 3600 + minutes * 60 + seconds) * 1000 + milliseconds
        
        def ms_to_srt_timestamp(total_ms: int) -> str:
            """Convert milliseconds to SRT timestamp format (HH:MM:SS,mmm)."""
            hours = total_ms // 3600000
            total_ms %= 3600000
            minutes = total_ms // 60000
            total_ms %= 60000
            seconds = total_ms // 1000
            milliseconds = total_ms % 1000
            
            return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"
        
        combined_sentences = []
        sentence_index = 0
        
        for srt_content, chunk_start_ms in chunk_srt_list:
            # Parse SRT content
            sentences = parse_srt_to_sentences(srt_content)
            
            # Offset timestamps by chunk start time
            chunk_start_ms_int = int(chunk_start_ms * 1000)
            
            for sentence in sentences:
                # Offset start and end times
                sentence["start"] += chunk_start_ms_int
                sentence["end"] += chunk_start_ms_int
                # Re-index
                sentence["index"] = sentence_index
                sentence_index += 1
                combined_sentences.append(sentence)
        
        # Convert back to SRT format
        srt_lines = []
        for sentence in combined_sentences:
            srt_lines.append(str(sentence["index"] + 1))  # SRT uses 1-based indexing
            start_ts = ms_to_srt_timestamp(sentence["start"])
            end_ts = ms_to_srt_timestamp(sentence["end"])
            srt_lines.append(f"{start_ts} --> {end_ts}")
            srt_lines.append(sentence["content"])
            srt_lines.append("")  # Empty line between entries
        
        return "\n".join(srt_lines)
    
    def _transcribe_file(self, audio_path: Path, language: Optional[str]) -> Dict[str, Any]:
        """Internal method to transcribe a file, with chunking support for large files."""
        # Check if file needs chunking
        if self._should_chunk(audio_path):
            return self._transcribe_file_chunked(audio_path, language)
        else:
            return self._transcribe_file_direct(audio_path, language)
    
    def _transcribe_file_direct(self, audio_path: Path, language: Optional[str]) -> Dict[str, Any]:
        """Transcribe a file directly without chunking."""
        try:
            # Prepare transcription parameters
            with open(audio_path, "rb") as audio_file:
                transcription_params = {
                    "model": "whisper-1",
                    "file": audio_file,
                    "response_format": "srt"
                }
                
                if language:
                    transcription_params["language"] = language
                
                # Call OpenAI Whisper API
                transcription = self.client.audio.transcriptions.create(**transcription_params)
            
            # Get SRT content (for srt format, response is a string)
            srt_content = str(transcription)
            
            # Parse SRT to extract sentences
            sentences = parse_srt_to_sentences(srt_content)
            
            # Concatenate sentences to form full text
            full_text = ' '.join(s["content"] for s in sentences)
            
            return {
                "text": full_text,
                "sentences": sentences,
                "words": None  # Deprecated, kept for backward compatibility
            }
            
        except Exception as e:
            raise Exception(f"Whisper transcription failed: {str(e)}")
    
    def _transcribe_file_chunked(self, audio_path: Path, language: Optional[str]) -> Dict[str, Any]:
        """Transcribe a large file by chunking it."""
        import tempfile
        
        chunk_dir = None
        
        try:
            # Create temporary directory for chunks
            chunk_dir = Path(tempfile.mkdtemp(prefix="whisper_chunks_"))
            
            # Split file into chunks
            file_size_mb = self._get_file_size(audio_path) / (1024 * 1024)
            print(f"  📦 File size ({file_size_mb:.2f}MB) exceeds {self.max_file_size_mb}MB limit. Chunking into {self.chunk_size_mb}MB pieces...")
            chunks = self._chunk_audio_file(audio_path, chunk_dir)
            print(f"  ✓ Created {len(chunks)} chunks")
            
            # Transcribe each chunk
            chunk_srt_list = []
            failed_chunks = []
            for i, (chunk_path, chunk_start) in enumerate(chunks):
                print(f"  🎤 Transcribing chunk {i+1}/{len(chunks)}...")
                try:
                    # Transcribe chunk
                    with open(chunk_path, "rb") as chunk_file:
                        transcription_params = {
                            "model": "whisper-1",
                            "file": chunk_file,
                            "response_format": "srt"
                        }
                        
                        if language:
                            transcription_params["language"] = language
                        
                        transcription = self.client.audio.transcriptions.create(**transcription_params)
                    
                    srt_content = str(transcription)
                    chunk_srt_list.append((srt_content, chunk_start))
                    print(f"  ✓ Chunk {i+1} transcribed")
                    
                except Exception as e:
                    print(f"  ✗ Error transcribing chunk {i+1}: {e}")
                    failed_chunks.append(i+1)
                    # Continue with remaining chunks instead of raising
            
            # Check if we have any successful chunks
            if not chunk_srt_list:
                raise Exception(f"All {len(chunks)} chunks failed to transcribe. Cannot proceed.")
            
            # Warn if some chunks failed
            if failed_chunks:
                print(f"  ⚠ Warning: {len(failed_chunks)} chunk(s) failed ({', '.join(map(str, failed_chunks))}), but continuing with {len(chunk_srt_list)} successful chunk(s)")
            
            # Combine SRT chunks
            print(f"  🔗 Combining {len(chunk_srt_list)} chunks...")
            combined_srt = self._combine_srt_chunks(chunk_srt_list)
            
            # Parse combined SRT to extract sentences
            sentences = parse_srt_to_sentences(combined_srt)
            
            # Concatenate sentences to form full text
            full_text = ' '.join(s["content"] for s in sentences)
            
            print(f"  ✓ Combined transcription complete ({len(sentences)} sentences)")
            
            return {
                "text": full_text,
                "sentences": sentences,
                "words": None  # Deprecated, kept for backward compatibility
            }
            
        finally:
            # Clean up chunk files
            if chunk_dir and chunk_dir.exists():
                import shutil
                try:
                    shutil.rmtree(chunk_dir)
                    print("  🧹 Cleaned up temporary chunk files")
                except Exception as e:
                    print(f"  ⚠ Warning: Could not clean up chunk directory: {e}")
    
    def get_service_name(self) -> str:
        """Return the name of the service."""
        return "Whisper"


# Import zhconv for Chinese conversion (optional)
try:
    import zhconv
    ZHCONV_AVAILABLE = True
except ImportError:
    ZHCONV_AVAILABLE = False
    # Note: Warning will be shown when conversion is attempted


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
    except Exception:
        # Return original text on error
        return text


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


class GroqService(SpeechToTextService):
    """Groq Whisper speech-to-text service implementation."""
    
    def __init__(
        self, 
        api_key: Optional[str] = None, 
        language: Optional[str] = None,
        max_file_size_mb: float = 25.0,
        chunk_size_mb: float = 10.0,
        chunk_overlap_seconds: float = 2.0,
        model: str = "whisper-large-v3-turbo",
        prompt: Optional[str] = None,
        temperature: float = 0.0,
        timestamp_granularities: Optional[List[str]] = None
    ):
        """
        Initialize Groq service.
        
        Args:
            api_key: Groq API key. If None, will try to load from GROQ_API_KEY env var.
            language: Optional language code (e.g., "en", "zh"). If None, auto-detection is used.
            max_file_size_mb: Maximum file size in MB before chunking is required (default: 25.0)
            chunk_size_mb: Size of each chunk in MB (default: 10.0)
            chunk_overlap_seconds: Overlap between chunks in seconds to avoid cutting mid-sentence (default: 2.0)
            model: Whisper model to use (default: "whisper-large-v3-turbo")
            prompt: Optional text to guide the model (e.g., proper nouns, technical terms)
            temperature: Sampling temperature between 0 and 1 (default: 0.0)
            timestamp_granularities: List of granularities - ["word", "segment"] (requires verbose_json)
        """
        try:
            from groq import Groq
        except ImportError:
            raise ImportError(
                "groq is not installed. Install it with: pip install groq"
            )
        
        # Get API key from parameter or environment variable
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        
        if not self.api_key:
            raise ValueError(
                "Groq API key is required. "
                "Set it in .env file as GROQ_API_KEY or pass it to the constructor."
            )
        
        # Initialize Groq client
        self.client = Groq(api_key=self.api_key)
        self.language = language
        self.model = model
        self.prompt = prompt
        self.temperature = temperature
        self.timestamp_granularities = timestamp_granularities
        
        # Chunking configuration
        self.max_file_size_mb = max_file_size_mb
        self.chunk_size_mb = chunk_size_mb
        self.chunk_overlap_seconds = chunk_overlap_seconds
        
        # Warn if zhconv is not available for Chinese conversion
        if not ZHCONV_AVAILABLE:
            print("⚠ Warning: zhconv not installed. Chinese conversion will be skipped.")
            print("   Install it with: pip install zhconv")
    
    def transcribe(self, audio_input: Union[str, Path, bytes], language: Optional[str] = None) -> Dict[str, Any]:
        """
        Transcribe an audio file or bytes using Groq Whisper API.
        
        Args:
            audio_input: Path to the audio file (str or Path) or bytes of audio data
            language: Optional language code override. If None, uses the language set in __init__ or auto-detection
            
        Returns:
            Dictionary with keys:
                - "text": The transcribed text as a string (concatenated sentences)
                - "sentences": List of sentence dictionaries with index, content, start, end
                - "words": None (deprecated, kept for backward compatibility)
            
        Raises:
            FileNotFoundError: If the audio file doesn't exist
            Exception: If transcription fails
        """
        # Use provided language or fall back to instance default
        lang = language or self.language
        
        # Handle bytes input - need to create temp file
        if isinstance(audio_input, bytes):
            import tempfile
            with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as temp_file:
                temp_path = Path(temp_file.name)
                temp_file.write(audio_input)
            
            try:
                # Transcribe the temp file
                result = self._transcribe_file(temp_path, lang)
            finally:
                # Clean up temp file
                if temp_path.exists():
                    temp_path.unlink()
            return result
        else:
            # Handle file path
            audio_path = Path(audio_input)
            if not audio_path.exists():
                raise FileNotFoundError(f"Audio file not found: {audio_path}")
            
            return self._transcribe_file(audio_path, lang)
    
    def _get_file_size(self, file_path: Path) -> int:
        """Get file size in bytes."""
        return file_path.stat().st_size
    
    def _should_chunk(self, file_path: Path) -> bool:
        """Check if file exceeds size limit and should be chunked."""
        file_size_bytes = self._get_file_size(file_path)
        max_size_bytes = self.max_file_size_mb * 1024 * 1024
        return file_size_bytes > max_size_bytes
    
    def _get_audio_duration(self, file_path: Path) -> float:
        """
        Get actual audio duration using ffprobe.
        
        Returns duration in seconds.
        """
        try:
            # Use ffprobe to get duration
            cmd = [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(file_path)
            ]
            
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            if result.returncode == 0:
                duration = float(result.stdout.strip())
                return duration
            else:
                # Fallback to estimation
                return self._estimate_audio_duration(file_path)
        except Exception:
            # Fallback to estimation
            return self._estimate_audio_duration(file_path)
    
    def _estimate_audio_duration(self, file_path: Path) -> float:
        """
        Estimate audio duration from file size (fallback method).
        
        This is a rough estimation. For MP3 files, assumes average bitrate.
        Returns duration in seconds.
        """
        file_size_bytes = self._get_file_size(file_path)
        file_size_mb = file_size_bytes / (1024 * 1024)
        
        # Rough estimation: assume average bitrate of 128 kbps for MP3
        # Duration (seconds) = (file_size_mb * 8) / bitrate_mbps
        # For 128 kbps = 0.128 Mbps
        estimated_duration_seconds = (file_size_mb * 8) / 0.128
        
        return estimated_duration_seconds
    
    def _chunk_audio_file(
        self, 
        audio_path: Path, 
        output_dir: Optional[Path] = None
    ) -> List[Tuple[Path, float]]:
        """
        Split audio file into chunks using ffmpeg.
        
        Args:
            audio_path: Path to the audio file
            output_dir: Directory to save chunks (if None, uses temp directory)
            
        Returns:
            List of tuples: (chunk_path, chunk_start_time_seconds)
        """
        import tempfile
        
        if output_dir is None:
            output_dir = Path(tempfile.gettempdir()) / "groq_chunks"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        file_size_bytes = self._get_file_size(audio_path)
        file_size_mb = file_size_bytes / (1024 * 1024)
        total_duration = self._get_audio_duration(audio_path)
        
        # Calculate chunk duration based on chunk_size_mb
        # Duration ratio = chunk_size / total_size
        chunk_duration_ratio = self.chunk_size_mb / file_size_mb
        chunk_duration_seconds = total_duration * chunk_duration_ratio
        
        chunks = []
        current_start = 0.0
        chunk_index = 0
        
        while current_start < total_duration:
            chunk_path = output_dir / f"chunk_{chunk_index:04d}.mp3"
            
            # Extract chunk using ffmpeg (no overlap)
            cmd = [
                "ffmpeg",
                "-i", str(audio_path),
                "-ss", str(current_start),
                "-t", str(chunk_duration_seconds),
                "-acodec", "libmp3lame",
                "-y",
                str(chunk_path)
            ]
            
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            if result.returncode != 0:
                raise RuntimeError(
                    f"ffmpeg failed to create chunk {chunk_index}:\n"
                    f"Command: {' '.join(cmd)}\n"
                    f"Error: {result.stderr}"
                )
            
            chunks.append((chunk_path, current_start))
            
            # Move to next chunk
            current_start += chunk_duration_seconds
            chunk_index += 1
        
        return chunks
    
    def _combine_srt_chunks(
        self, 
        chunk_srt_list: List[Tuple[str, float]]
    ) -> str:
        """
        Combine multiple SRT contents with timestamp offsets.
        
        Args:
            chunk_srt_list: List of tuples (srt_content, chunk_start_time_seconds)
            
        Returns:
            Combined SRT content with corrected timestamps
        """
        def srt_timestamp_to_ms(timestamp: str) -> int:
            """Convert SRT timestamp (HH:MM:SS,mmm) to milliseconds."""
            match = re.match(r'(\d{2}):(\d{2}):(\d{2}),(\d{3})', timestamp)
            if not match:
                raise ValueError(f"Invalid SRT timestamp format: {timestamp}")
            
            hours = int(match.group(1))
            minutes = int(match.group(2))
            seconds = int(match.group(3))
            milliseconds = int(match.group(4))
            
            return (hours * 3600 + minutes * 60 + seconds) * 1000 + milliseconds
        
        def ms_to_srt_timestamp(total_ms: int) -> str:
            """Convert milliseconds to SRT timestamp format (HH:MM:SS,mmm)."""
            hours = total_ms // 3600000
            total_ms %= 3600000
            minutes = total_ms // 60000
            total_ms %= 60000
            seconds = total_ms // 1000
            milliseconds = total_ms % 1000
            
            return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"
        
        combined_sentences = []
        sentence_index = 0
        
        for srt_content, chunk_start_ms in chunk_srt_list:
            # Parse SRT content
            sentences = parse_srt_to_sentences(srt_content)
            
            # Offset timestamps by chunk start time
            chunk_start_ms_int = int(chunk_start_ms * 1000)
            
            for sentence in sentences:
                # Offset start and end times
                sentence["start"] += chunk_start_ms_int
                sentence["end"] += chunk_start_ms_int
                # Re-index
                sentence["index"] = sentence_index
                sentence_index += 1
                combined_sentences.append(sentence)
        
        # Convert back to SRT format
        srt_lines = []
        for sentence in combined_sentences:
            srt_lines.append(str(sentence["index"] + 1))  # SRT uses 1-based indexing
            start_ts = ms_to_srt_timestamp(sentence["start"])
            end_ts = ms_to_srt_timestamp(sentence["end"])
            srt_lines.append(f"{start_ts} --> {end_ts}")
            srt_lines.append(sentence["content"])
            srt_lines.append("")  # Empty line between entries
        
        return "\n".join(srt_lines)
    
    def _transcribe_file(self, audio_path: Path, language: Optional[str]) -> Dict[str, Any]:
        """Internal method to transcribe a file, with chunking support for large files."""
        # Check if file needs chunking
        if self._should_chunk(audio_path):
            return self._transcribe_file_chunked(audio_path, language)
        else:
            return self._transcribe_file_direct(audio_path, language)
    
    def _transcribe_file_direct(self, audio_path: Path, language: Optional[str]) -> Dict[str, Any]:
        """Transcribe a file directly without chunking."""
        try:
            # Prepare transcription parameters
            with open(audio_path, "rb") as audio_file:
                transcription_params = {
                    "file": audio_file,
                    "model": self.model,
                    "response_format": "verbose_json",
                    "temperature": self.temperature
                }
                
                if language:
                    # Note: Groq API may not support language parameter, but include it if provided
                    pass  # Groq API doesn't have explicit language parameter
                
                if self.prompt:
                    transcription_params["prompt"] = self.prompt
                
                if self.timestamp_granularities:
                    transcription_params["timestamp_granularities"] = self.timestamp_granularities
                
                # Call Groq Whisper API
                transcription = self.client.audio.transcriptions.create(**transcription_params)
            
            # Convert response to dict if needed
            if hasattr(transcription, 'model_dump'):
                transcription_dict = transcription.model_dump()
            elif hasattr(transcription, 'dict'):
                transcription_dict = transcription.dict()
            else:
                transcription_dict = dict(transcription)
            
            # Apply traditional Chinese conversion
            transcription_dict = convert_json_to_traditional_chinese(transcription_dict)
            
            # Convert verbose_json to SRT
            srt_content = convert_verbose_json_to_srt(transcription_dict)
            
            # Apply Chinese conversion to SRT (in case any text wasn't converted in JSON)
            srt_content = convert_srt_to_traditional_chinese(srt_content)
            
            # Parse SRT to extract sentences
            sentences = parse_srt_to_sentences(srt_content)
            
            # Concatenate sentences to form full text
            full_text = ' '.join(s["content"] for s in sentences)
            
            return {
                "text": full_text,
                "sentences": sentences,
                "words": None  # Deprecated, kept for backward compatibility
            }
            
        except Exception as e:
            raise Exception(f"Groq transcription failed: {str(e)}")
    
    def _transcribe_file_chunked(self, audio_path: Path, language: Optional[str]) -> Dict[str, Any]:
        """Transcribe a large file by chunking it."""
        import shutil
        import tempfile
        
        chunk_dir = None
        
        try:
            # Create temporary directory for chunks
            chunk_dir = Path(tempfile.mkdtemp(prefix="groq_chunks_"))
            
            # Split file into chunks
            file_size_mb = self._get_file_size(audio_path) / (1024 * 1024)
            print(f"  📦 File size ({file_size_mb:.2f}MB) exceeds {self.max_file_size_mb}MB limit. Chunking into {self.chunk_size_mb}MB pieces...")
            chunks = self._chunk_audio_file(audio_path, chunk_dir)
            print(f"  ✓ Created {len(chunks)} chunks")
            
            # Transcribe each chunk
            chunk_srt_list = []
            failed_chunks = []
            for i, (chunk_path, chunk_start) in enumerate(chunks):
                print(f"  🎤 Transcribing chunk {i+1}/{len(chunks)}...")
                try:
                    # Transcribe chunk
                    with open(chunk_path, "rb") as chunk_file:
                        transcription_params = {
                            "file": chunk_file,
                            "model": self.model,
                            "response_format": "verbose_json",
                            "temperature": self.temperature
                        }
                        
                        if self.prompt:
                            transcription_params["prompt"] = self.prompt
                        
                        if self.timestamp_granularities:
                            transcription_params["timestamp_granularities"] = self.timestamp_granularities
                        
                        transcription = self.client.audio.transcriptions.create(**transcription_params)
                    
                    # Convert response to dict
                    if hasattr(transcription, 'model_dump'):
                        transcription_dict = transcription.model_dump()
                    elif hasattr(transcription, 'dict'):
                        transcription_dict = transcription.dict()
                    else:
                        transcription_dict = dict(transcription)
                    
                    # Apply traditional Chinese conversion
                    transcription_dict = convert_json_to_traditional_chinese(transcription_dict)
                    
                    # Convert to SRT
                    srt_content = convert_verbose_json_to_srt(transcription_dict)
                    srt_content = convert_srt_to_traditional_chinese(srt_content)
                    
                    chunk_srt_list.append((srt_content, chunk_start))
                    print(f"  ✓ Chunk {i+1} transcribed")
                    
                except Exception as e:
                    print(f"  ✗ Error transcribing chunk {i+1}: {e}")
                    failed_chunks.append(i+1)
                    # Continue with remaining chunks instead of raising
            
            # Check if we have any successful chunks
            if not chunk_srt_list:
                raise Exception(f"All {len(chunks)} chunks failed to transcribe. Cannot proceed.")
            
            # Warn if some chunks failed
            if failed_chunks:
                print(f"  ⚠ Warning: {len(failed_chunks)} chunk(s) failed ({', '.join(map(str, failed_chunks))}), but continuing with {len(chunk_srt_list)} successful chunk(s)")
            
            # Combine SRT chunks
            print(f"  🔗 Combining {len(chunk_srt_list)} chunks...")
            combined_srt = self._combine_srt_chunks(chunk_srt_list)
            
            # Apply final Chinese conversion pass (in case of any missed text)
            combined_srt = convert_srt_to_traditional_chinese(combined_srt)
            
            # Parse combined SRT to extract sentences
            sentences = parse_srt_to_sentences(combined_srt)
            
            # Concatenate sentences to form full text
            full_text = ' '.join(s["content"] for s in sentences)
            
            print(f"  ✓ Combined transcription complete ({len(sentences)} sentences)")
            
            return {
                "text": full_text,
                "sentences": sentences,
                "words": None  # Deprecated, kept for backward compatibility
            }
            
        finally:
            # Clean up chunk files
            if chunk_dir and chunk_dir.exists():
                try:
                    shutil.rmtree(chunk_dir)
                    print("  🧹 Cleaned up temporary chunk files")
                except Exception as e:
                    print(f"  ⚠ Warning: Could not clean up chunk directory: {e}")
    
    def get_service_name(self) -> str:
        """Return the name of the service."""
        return "Groq"


def transcribe_audio_file(
    audio_path: Union[str, Path, bytes],
    output_path: Optional[str] = None,
    output_base_dir: Optional[str] = None,
    service: Optional[SpeechToTextService] = None,
    return_text_only: bool = False,
    language: Optional[str] = None
) -> Union[str, Dict[str, Any]]:
    """
    Transcribe an audio file and optionally save the result to a text file.
    
    Args:
        audio_path: Path to the input audio file (e.g., MP3) or bytes of audio data
        output_path: Optional path for the output text file. 
                     If None, will be generated from audio_path (same directory, .txt extension)
                     Ignored if return_text_only=True
        output_base_dir: Optional base directory for output. If provided along with output_path=None,
                        will preserve the relative directory structure from audio_path's parent.
                        Example: audio_path="data/downloads/podcast/episode.mp3", 
                                output_base_dir="data/transcripts" 
                                -> output="data/transcripts/podcast/episode.txt"
                        Ignored if return_text_only=True
        service: Optional SpeechToTextService instance. 
                 If None, will use WhisperService with API key from .env
        return_text_only: If True, return transcript dict directly without saving to file
        language: Optional language code for transcription (e.g., "en", "zh"). 
                 If None, uses service default or auto-detection.
    
    Returns:
        If return_text_only=True: dict with "text", "sentences", and "words" keys
        Otherwise: Path to the saved transcript file (as string)
        
    Raises:
        FileNotFoundError: If the audio file doesn't exist (only for file paths)
        Exception: If transcription fails
    """
    # Handle bytes input - skip file existence check
    if isinstance(audio_path, bytes):
        audio_input = audio_path
        audio_path_obj = None
    else:
        audio_path_obj = Path(audio_path).resolve()
        if not audio_path_obj.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path_obj}")
        audio_input = audio_path_obj
    
    # If return_text_only, skip file path generation and saving
    if return_text_only:
        # Initialize service if not provided
        if service is None:
            service = WhisperService()
        
        # Transcribe directly - returns dict with "text", "sentences", and "words"
        transcript_result = service.transcribe(audio_input, language=language)
        return transcript_result
    
    # Generate output path if not provided (only for file-based mode)
    if output_path is None:
        if output_base_dir:
            # Preserve directory structure from data/downloads/ onwards
            # Example: .../data/downloads/podcast/episode.mp3 -> data/transcripts/podcast/episode.json
            output_base = Path(output_base_dir)
            
            # Find "data/downloads" or "downloads" in the path and preserve structure after it
            parts = audio_path.parts
            try:
                # First try to find "data/downloads" pattern
                if "data" in parts and "downloads" in parts:
                    data_idx = parts.index("data")
                    downloads_idx = parts.index("downloads")
                    if downloads_idx == data_idx + 1:
                        # Found data/downloads pattern
                        relative_parts = parts[downloads_idx + 1:]
                        output_path = output_base / Path(*relative_parts).with_suffix('.json')
                    else:
                        # downloads exists but not right after data
                        relative_parts = parts[downloads_idx + 1:]
                        output_path = output_base / Path(*relative_parts).with_suffix('.json')
                elif "downloads" in parts:
                    # Fallback to just "downloads"
                    downloads_idx = parts.index("downloads")
                    relative_parts = parts[downloads_idx + 1:]
                    output_path = output_base / Path(*relative_parts).with_suffix('.json')
                else:
                    raise ValueError("downloads not found")
            except (ValueError, IndexError):
                # "downloads" not found, preserve parent directory structure
                # Get parent directory name and filename
                output_path = output_base / audio_path.parent.name / audio_path.with_suffix('.json').name
        else:
            # Replace extension with .json, or add .json if no extension
            if audio_path.suffix:
                output_path = audio_path.with_suffix('.json')
            else:
                output_path = audio_path.with_suffix('.json')
    else:
        output_path = Path(output_path)
    
    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Use provided service or default to Whisper
    if service is None:
        service = WhisperService()
    
    # Get display name for logging
    if audio_path_obj:
        display_name = audio_path_obj.name
    else:
        display_name = "audio bytes"
    
    print(f"Transcribing {display_name} using {service.get_service_name()}...")
    
    # Transcribe (pass language if service supports it)
    if hasattr(service, 'transcribe') and language:
        # Check if transcribe method accepts language parameter
        import inspect
        sig = inspect.signature(service.transcribe)
        if 'language' in sig.parameters:
            transcript_result = service.transcribe(audio_input, language=language)
        else:
            transcript_result = service.transcribe(audio_input)
    else:
        transcript_result = service.transcribe(audio_input)
    
    # Ensure transcript_result is a dict with "text", "sentences", and "words"
    if isinstance(transcript_result, dict):
        transcript_data = transcript_result
        # Ensure sentences field exists
        if "sentences" not in transcript_data:
            transcript_data["sentences"] = []
        # Ensure words field exists (for backward compatibility)
        if "words" not in transcript_data:
            transcript_data["words"] = None
    else:
        # Fallback: create dict from text string (backward compatibility)
        transcript_data = {
            "text": str(transcript_result),
            "sentences": [],
            "words": None
        }
    
    # Save transcript as JSON with text, sentences, and words
    output_path.write_text(
        json.dumps(transcript_data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    
    print(f"✓ Transcript saved to: {output_path}")
    
    return str(output_path)


# Example usage
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python speech_to_text.py <audio_file_path> [output_file_path]")
        print("\nExample:")
        print("  python speech_to_text.py data/downloads/podcast/episode.mp3")
        print("  python speech_to_text.py data/downloads/podcast/episode.mp3 data/transcripts/episode.txt")
        sys.exit(1)
    
    audio_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None
    
    try:
        result_path = transcribe_audio_file(audio_file, output_file)
        print(f"\nSuccess! Transcript saved to: {result_path}")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

