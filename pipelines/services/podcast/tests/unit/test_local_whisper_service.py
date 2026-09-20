"""Whisper on our own hardware, spoken to over the OpenAI audio API.

Measured 2026-09-20 on a 52.5-minute 股癌 episode (M4 Pro, ggml-large-v3-turbo): 148 s
for the audio — 21x realtime — with the same coverage as the Groq transcript. The one
defect was script: un-seeded output carried 104 Simplified glyphs per 1,000 characters
where Groq's had none, which the decoder seed removes entirely. So the two things worth
pinning here are that the seed actually reaches the server, and that segment timings
survive the conversion — the extractor addresses sentences by position and the clusterer
reads their timestamps, so a silently dropped or mistimed segment desyncs every chapter
after it.
"""

from __future__ import annotations

import pytest
from src.service.speech_to_text import TRADITIONAL_SEED_PROMPT, LocalWhisperService


class _Resp:
    def __init__(self, payload, status_code=200, text=""):
        self._payload, self.status_code, self.text = payload, status_code, text

    def json(self):
        return self._payload


@pytest.fixture
def svc(monkeypatch):
    monkeypatch.setenv("LOCAL_WHISPER_BASE_URL", "http://mac-mini:11434/v1")
    return LocalWhisperService()


def test_it_refuses_to_start_without_a_base_url(monkeypatch):
    monkeypatch.delenv("LOCAL_WHISPER_BASE_URL", raising=False)
    with pytest.raises(ValueError, match="LOCAL_WHISPER_BASE_URL"):
        LocalWhisperService()


def test_the_traditional_seed_reaches_the_server(svc, monkeypatch, tmp_path):
    sent = {}

    def fake_post(url, files=None, data=None, timeout=None):
        sent.update(url=url, data=data, filename=files["file"][0])
        return _Resp({"text": "測試", "segments": [{"text": "測試", "start": 0.0, "end": 1.0}]})

    monkeypatch.setattr("requests.post", fake_post)
    audio = tmp_path / "ep.mp3"
    audio.write_bytes(b"not-really-audio")

    svc.transcribe(audio)

    assert sent["url"] == "http://mac-mini:11434/v1/audio/transcriptions"
    assert sent["data"]["prompt"] == TRADITIONAL_SEED_PROMPT
    assert sent["data"]["response_format"] == "verbose_json"
    assert sent["data"]["language"] == "zh"
    assert sent["filename"] == "ep.mp3"


def test_the_seed_can_be_turned_off_explicitly(monkeypatch):
    monkeypatch.setenv("LOCAL_WHISPER_BASE_URL", "http://mac-mini:11434/v1")
    sent = {}
    monkeypatch.setattr("requests.post", lambda url, files=None, data=None, timeout=None:
                        (sent.update(data=data), _Resp({"text": "", "segments": []}))[1])

    LocalWhisperService(prompt="").transcribe(b"bytes")

    assert "prompt" not in sent["data"], "an empty seed must mean no prompt, not an empty one"


def test_segments_become_sentence_rows_with_millisecond_timings(svc):
    out = LocalWhisperService._to_sentences({
        "text": "一二",
        "segments": [
            {"text": " 記憶體缺貨 ", "start": 0.0, "end": 2.5},
            {"text": "頻寬最重要", "start": 2.5, "end": 4.0},
        ],
    })

    assert out["sentences"] == [
        {"index": 0, "content": "記憶體缺貨", "start": 0, "end": 2500},
        {"index": 1, "content": "頻寬最重要", "start": 2500, "end": 4000},
    ]
    assert out["words"] is None


def test_untimed_or_empty_segments_are_dropped_and_indices_stay_dense(svc):
    """A guessed timestamp is worse than a missing sentence: it desyncs every chapter after it."""
    out = LocalWhisperService._to_sentences({
        "segments": [
            {"text": "有時間", "start": 0.0, "end": 1.0},
            {"text": "沒有結束時間", "start": 1.0, "end": None},
            {"text": "   ", "start": 2.0, "end": 3.0},
            {"text": "也有時間", "start": 3.0, "end": 4.0},
        ],
    })

    assert [s["index"] for s in out["sentences"]] == [0, 1]
    assert [s["content"] for s in out["sentences"]] == ["有時間", "也有時間"]
    # No "text" in the payload: it is rebuilt from what survived, not left empty.
    assert out["text"] == "有時間也有時間"


def test_a_server_error_surfaces_the_body_not_just_the_status(svc, monkeypatch):
    monkeypatch.setattr("requests.post", lambda *a, **k:
                        _Resp(None, status_code=400, text="unknown model whisper-large-v9"))

    with pytest.raises(RuntimeError, match="whisper-large-v9"):
        svc.transcribe(b"bytes")


def test_a_missing_file_fails_before_any_request(svc, monkeypatch):
    monkeypatch.setattr("requests.post", lambda *a, **k: pytest.fail("must not call the server"))

    with pytest.raises(FileNotFoundError):
        svc.transcribe("/nope/missing.mp3")


def test_the_factory_selects_it_for_transcript_service_local(monkeypatch):
    monkeypatch.setenv("LOCAL_WHISPER_BASE_URL", "http://mac-mini:11434/v1")
    from src.pipeline.steps.initialize import initialize_stt_service

    class _Cfg:
        stt_service_name = "local"
        stt_model = None

    assert initialize_stt_service(_Cfg()).get_service_name() == "local-whisper"


def test_the_route_is_configurable_because_servers_disagree_about_it(monkeypatch):
    """Regression: whisper.cpp's whisper-server serves /inference, not the OpenAI route.

    The first end-to-end run against a real server 404'd on /v1/audio/transcriptions
    while every mocked test passed, so the path is a knob and its default is the
    OpenAI one (ollama, LiteLLM, faster-whisper servers all use that).
    """
    monkeypatch.setenv("LOCAL_WHISPER_BASE_URL", "http://mac-mini:8910")
    monkeypatch.setenv("LOCAL_WHISPER_TRANSCRIBE_PATH", "inference")
    seen = {}
    monkeypatch.setattr("requests.post", lambda url, files=None, data=None, timeout=None:
                        (seen.update(url=url), _Resp({"text": "", "segments": []}))[1])

    LocalWhisperService().transcribe(b"bytes")

    assert seen["url"] == "http://mac-mini:8910/inference", "a path without its slash must still work"
