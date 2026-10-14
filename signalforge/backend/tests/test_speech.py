"""
Tests for the speech-to-text (Whistle) pipeline.

Never loads the real Whistle model — transcribe_wav_bytes is mocked
for endpoint tests. parse_ticker is a pure function and is tested
directly.

Run: uv run pytest backend/tests/test_speech.py -v
"""
import io
import struct
import wave
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.speech.whistle_service import (
    SpeechUnavailableError,
    parse_ticker,
)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

def make_wav_bytes(
    sample_rate: int = 16000,
    channels: int = 1,
    sample_width: int = 2,
    duration_s: float = 1.0,
) -> bytes:
    """Build a small valid 16-bit PCM WAV in memory."""
    buf = io.BytesIO()
    with wave.open(buf, "w") as w:
        w.setnchannels(channels)
        w.setsampwidth(sample_width)
        w.setframerate(sample_rate)
        num = int(sample_rate * duration_s)
        w.writeframes(struct.pack("<" + "h" * num, *([0] * num)))
    return buf.getvalue()


def make_test_app() -> FastAPI:
    """A minimal FastAPI app with only the speech router (no DB, no Redis)."""
    app = FastAPI()
    from backend.routers import speech
    app.include_router(speech.router)
    return app


@pytest.fixture()
def client():
    return TestClient(make_test_app())


# --------------------------------------------------------------------------- #
# parse_ticker — parametrized
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("transcript,expected", [
    ("Apple.", "AAPL"),
    ("A A P L", "AAPL"),
    ("a.a.p.l.", "AAPL"),
    ("AAPL", "AAPL"),
    ("nvda", "NVDA"),
    ("analyze Microsoft stock please", "MSFT"),
    ("B R K dot B", "BRK.B"),
    ("meta platforms", "META"),
    ("McDonald's", "MCD"),
    ("", None),
    ("hello there world", None),
    ("twelve", None),  # 6 letters, not a ticker (regex allows 1-5)
])
def test_parse_ticker(transcript, expected):
    assert parse_ticker(transcript) == expected


# --------------------------------------------------------------------------- #
# endpoint — validation
# --------------------------------------------------------------------------- #

VALID_WAV = make_wav_bytes(sample_rate=16000)
WAV_44K = make_wav_bytes(sample_rate=44100)
WAVE_16K = VALID_WAV  # 44-byte header + frames; 1 s of silence = ~32 KB


def test_transcribe_valid_wav(client):
    """Valid WAV + mocked transcribe_wav_bytes -> 200 with JSON shape."""
    with patch("backend.routers.speech.transcribe_wav_bytes",
               new_callable=AsyncMock) as mock_fn:
        mock_fn.return_value = {
            "transcript": "Apple",
            "ticker": "AAPL",
            "latency_ms": 84,
        }
        resp = client.post("/speech/transcribe", content=VALID_WAV,
                           headers={"Content-Type": "audio/wav"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["transcript"] == "Apple"
    assert data["ticker"] == "AAPL"
    assert data["latency_ms"] == 84
    mock_fn.assert_awaited_once_with(VALID_WAV)


def test_transcribe_no_ticker_in_response(client):
    """Transcript with no ticker match -> ticker is null in JSON."""
    with patch("backend.routers.speech.transcribe_wav_bytes",
               new_callable=AsyncMock) as mock_fn:
        mock_fn.return_value = {
            "transcript": "hello there",
            "ticker": None,
            "latency_ms": 50,
        }
        resp = client.post("/speech/transcribe", content=VALID_WAV,
                           headers={"Content-Type": "audio/wav"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["ticker"] is None
    assert data["transcript"] == "hello there"


# --------------------------------------------------------------------------- #
# endpoint — validation errors
# --------------------------------------------------------------------------- #

def test_transcribe_empty_body(client):
    resp = client.post("/speech/transcribe", content=b"",
                       headers={"Content-Type": "audio/wav"})
    assert resp.status_code == 400


def test_transcribe_non_wav(client):
    resp = client.post("/speech/transcribe",
                       content=b"not a wav file at all",
                       headers={"Content-Type": "audio/wav"})
    assert resp.status_code == 400


def test_transcribe_44khz_rejected(client):
    resp = client.post("/speech/transcribe", content=WAV_44K,
                       headers={"Content-Type": "audio/wav"})
    assert resp.status_code == 400


def test_transcribe_too_long(client):
    """Body larger than 1 MB -> 413."""
    big = WAVE_16K + b"\x00" * (1_100_000 - len(WAVE_16K))
    resp = client.post("/speech/transcribe", content=big,
                       headers={"Content-Type": "audio/wav"})
    assert resp.status_code == 413


# --------------------------------------------------------------------------- #
# endpoint — server error / unavailable
# --------------------------------------------------------------------------- #

def test_transcribe_speech_unavailable(client):
    """SpeechUnavailableError -> 503."""
    with patch("backend.routers.speech.transcribe_wav_bytes",
               new_callable=AsyncMock,
               side_effect=SpeechUnavailableError("not installed")):
        resp = client.post("/speech/transcribe", content=VALID_WAV,
                           headers={"Content-Type": "audio/wav"})
    assert resp.status_code == 503


def test_transcribe_internal_error(client):
    """Unexpected exception -> 500."""
    with patch("backend.routers.speech.transcribe_wav_bytes",
               new_callable=AsyncMock,
               side_effect=RuntimeError("boom")):
        resp = client.post("/speech/transcribe", content=VALID_WAV,
                           headers={"Content-Type": "audio/wav"})
    assert resp.status_code == 500
