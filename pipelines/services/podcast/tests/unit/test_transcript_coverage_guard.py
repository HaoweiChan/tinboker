"""Unit tests for the transcript-vs-audio guard in ``speech_to_text``.

41 股癌 episodes (293 across all shows) shipped with transcripts covering a fraction
of their audio: the chunked path skips chunks that fail to transcribe and combines
whatever is left, and the model can collapse on a whole file and return a few
characters spanning the full duration. Both were stored without complaint.
"""

from __future__ import annotations

import pytest
from src.service import speech_to_text
from src.service.speech_to_text import (
    ChunkTranscriptionError,
    GroqService,
    TranscriptTooShortError,
    check_transcript_covers_audio,
)

AUDIO_SECONDS = 52 * 60  # a typical 股癌 episode


def _transcript(chars: int, spanned_seconds: float) -> dict:
    """One sentence carrying ``chars`` characters and ending at ``spanned_seconds``."""
    return {
        "text": "股" * chars,
        "sentences": [{"index": 0, "content": "股" * chars, "start": 0, "end": int(spanned_seconds * 1000)}],
        "words": None,
    }


def test_healthy_transcript_passes():
    check_transcript_covers_audio(_transcript(20_000, AUDIO_SECONDS), AUDIO_SECONDS)


def test_truncated_transcript_raises():
    # EP520: 4,673 characters and timestamps stopping a fifth of the way in.
    with pytest.raises(TranscriptTooShortError, match="covers only"):
        check_transcript_covers_audio(_transcript(4_673, AUDIO_SECONDS * 0.2), AUDIO_SECONDS)


def test_collapsed_transcript_raises_even_at_full_coverage():
    # EP519: 363 characters whose timestamps still span the whole episode.
    with pytest.raises(TranscriptTooShortError, match="chars/min"):
        check_transcript_covers_audio(_transcript(363, AUDIO_SECONDS), AUDIO_SECONDS)


def test_empty_transcript_raises():
    with pytest.raises(TranscriptTooShortError):
        check_transcript_covers_audio({"text": "", "sentences": [], "words": None}, AUDIO_SECONDS)


def test_sparsest_legitimate_density_passes():
    # The thinnest real episode measured in production: 224 chars/min of Mandarin.
    check_transcript_covers_audio(_transcript(int(224 * 52), AUDIO_SECONDS), AUDIO_SECONDS)


@pytest.mark.parametrize("duration", [None, 0, -1])
def test_unknown_duration_disables_the_check(duration):
    # ffprobe could not read the file: no denominator, no verdict.
    check_transcript_covers_audio(_transcript(0, 0), duration)


SRT_CHUNK = "1\n00:00:00,000 --> 00:00:05,000\n這是一段內容\n"


def _chunked_groq(monkeypatch, tmp_path, failing_chunk: int | None, fail_times: int = 99):
    """A GroqService whose file always chunks, with one chunk failing ``fail_times``."""
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setattr(speech_to_text.time, "sleep", lambda _s: None)  # no real backoff
    service = GroqService()
    chunks = [(tmp_path / f"chunk_{i}.mp3", i * 300.0) for i in range(4)]
    for path, _ in chunks:
        path.write_bytes(b"")

    monkeypatch.setattr(service, "_should_chunk", lambda _path: True)
    monkeypatch.setattr(service, "_get_file_size", lambda _path: 60 * 1024 * 1024)
    monkeypatch.setattr(service, "_chunk_audio_file", lambda _path, _dir: chunks)

    attempts: dict[int, int] = {}

    def fake_call(chunk_path, label=""):
        index = chunks.index(next(c for c in chunks if c[0] == chunk_path))
        attempts[index] = attempts.get(index, 0) + 1
        if index == failing_chunk and attempts[index] <= fail_times:
            raise RuntimeError("429 rate limit exceeded")
        return {"text": "這是一段內容", "duration": 300.0, "segments": []}

    monkeypatch.setattr(service, "_transcribe_call", fake_call)
    service._test_attempts = attempts
    monkeypatch.setattr(
        "src.service.speech_to_text.convert_verbose_json_to_srt", lambda _d: SRT_CHUNK
    )
    return service


def test_a_failed_chunk_stops_the_episode(monkeypatch, tmp_path):
    # Was: log it, drop the chunk, combine the rest, exit 0 — a fifth of an episode
    # stored as a whole one.
    service = _chunked_groq(monkeypatch, tmp_path, failing_chunk=2)
    with pytest.raises(ChunkTranscriptionError, match="Chunk 3/4"):
        service._transcribe_file_chunked(tmp_path / "episode.mp3", None)


def test_all_chunks_succeeding_still_returns_a_transcript(monkeypatch, tmp_path):
    service = _chunked_groq(monkeypatch, tmp_path, failing_chunk=None)
    result = service._transcribe_file_chunked(tmp_path / "episode.mp3", None)
    assert len(result["sentences"]) == 4


def test_a_chunk_is_retried_before_the_episode_fails(monkeypatch, tmp_path):
    # A rate limit clears if you wait, which is the whole reason the retry is there.
    service = _chunked_groq(monkeypatch, tmp_path, failing_chunk=2, fail_times=2)
    result = service._transcribe_file_chunked(tmp_path / "episode.mp3", None)
    assert len(result["sentences"]) == 4
    assert service._test_attempts[2] == 3


def test_retries_are_bounded(monkeypatch, tmp_path):
    service = _chunked_groq(monkeypatch, tmp_path, failing_chunk=2)
    with pytest.raises(ChunkTranscriptionError, match="after 3 attempts"):
        service._transcribe_file_chunked(tmp_path / "episode.mp3", None)
    assert service._test_attempts[2] == 3
