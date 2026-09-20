"""Local Whisper must never cost us an episode.

The endpoint is a Mac behind a Tailscale tunnel. FileVault is on and the machine does
not auto-login, so after a reboot for updates it sits at the unlock prompt with no
tunnel at all — for as long as nobody is around to type the password. Ingest has to ride
through that on Groq, and the log has to say which path served the episode.
"""

from __future__ import annotations

import pytest
from src.service.speech_to_text import FallbackTranscriptService


class _Stub:
    def __init__(self, name, result=None, error=None):
        self.name, self.result, self.error, self.calls = name, result, error, 0

    def get_service_name(self):
        return self.name

    def transcribe(self, audio_input, language=None):
        self.calls += 1
        if self.error:
            raise self.error
        return self.result


GOOD = {"text": "記憶體缺貨", "sentences": [{"index": 0, "content": "記憶體缺貨", "start": 0, "end": 1000}], "words": None}
ALSO_GOOD = {"text": "from groq", "sentences": [{"index": 0, "content": "from groq", "start": 0, "end": 900}], "words": None}


def test_the_primary_serves_when_it_works_and_groq_is_never_called():
    primary, backup = _Stub("local-whisper", GOOD), _Stub("groq", ALSO_GOOD)

    out = FallbackTranscriptService(primary, backup).transcribe("ep.mp3")

    assert out == GOOD
    assert backup.calls == 0, "paying Groq while the Mac is healthy defeats the point"


@pytest.mark.parametrize("error", [
    ConnectionError("tunnel down"),
    TimeoutError("mac asleep"),
    RuntimeError("local whisper 500: model not loaded"),
    RuntimeError("local whisper 400: unknown model"),
])
def test_any_primary_failure_hands_off_to_groq(error, capsys):
    primary, backup = _Stub("local-whisper", error=error), _Stub("groq", ALSO_GOOD)

    out = FallbackTranscriptService(primary, backup).transcribe("ep.mp3")

    assert out == ALSO_GOOD
    assert backup.calls == 1
    # A 4xx is really our bug, but a gap in the archive is worse than a Groq bill —
    # the log is what makes the misconfiguration visible.
    assert "falling back to groq" in capsys.readouterr().out


def test_an_empty_sentence_list_counts_as_a_failure(capsys):
    """Downstream indexes sentences by position, so zero of them is not a usable result."""
    primary = _Stub("local-whisper", {"text": "", "sentences": [], "words": None})
    backup = _Stub("groq", ALSO_GOOD)

    out = FallbackTranscriptService(primary, backup).transcribe("ep.mp3")

    assert out == ALSO_GOOD
    assert "no sentences" in capsys.readouterr().out


def test_a_backup_failure_is_raised_not_swallowed():
    """Both paths down is a real outage — the caller must see it, not get a silent empty."""
    primary = _Stub("local-whisper", error=ConnectionError("tunnel down"))
    backup = _Stub("groq", error=RuntimeError("groq 401"))

    with pytest.raises(RuntimeError, match="groq 401"):
        FallbackTranscriptService(primary, backup).transcribe("ep.mp3")


def test_the_name_shows_both_paths_so_logs_say_what_is_configured():
    svc = FallbackTranscriptService(_Stub("local-whisper", GOOD), _Stub("groq", ALSO_GOOD))

    assert svc.get_service_name() == "local-whisper (fallback: groq)"


def test_the_factory_wraps_local_in_a_groq_fallback(monkeypatch):
    monkeypatch.setenv("LOCAL_WHISPER_BASE_URL", "http://mac-mini:8910")
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    from src.pipeline.steps.initialize import initialize_stt_service

    class _Cfg:
        stt_service_name = "local"
        stt_model = None

    assert initialize_stt_service(_Cfg()).get_service_name().startswith("local-whisper (fallback:")


def test_local_still_works_when_groq_is_not_configured(monkeypatch, capsys):
    """No GROQ_API_KEY must degrade to local-only, not break ingest at startup."""
    monkeypatch.setenv("LOCAL_WHISPER_BASE_URL", "http://mac-mini:8910")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    from src.pipeline.steps.initialize import initialize_stt_service

    class _Cfg:
        stt_service_name = "local"
        stt_model = None

    assert initialize_stt_service(_Cfg()).get_service_name() == "local-whisper"
    assert "no Groq fallback" in capsys.readouterr().out
