"""Unit tests for the transcript-vs-audio guard in ``speech_to_text``.

41 股癌 episodes (293 across all shows) shipped with transcripts covering a fraction
of their audio: the chunked path skips chunks that fail to transcribe and combines
whatever is left, and the model can collapse on a whole file and return a few
characters spanning the full duration. Both were stored without complaint.
"""

from __future__ import annotations

import pytest
from src.service.speech_to_text import (
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
