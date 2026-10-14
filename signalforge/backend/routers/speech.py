import logging
from fastapi import APIRouter, HTTPException, Request

from backend.speech.whistle_service import (
    SpeechUnavailableError, transcribe_wav_bytes,
)

logger = logging.getLogger(__name__)
router = APIRouter()

# 30 s of 16 kHz 16-bit mono PCM = 960,000 bytes + 44-byte header
MAX_WAV_BYTES = 1_000_000


@router.post("/speech/transcribe")
async def transcribe_speech(request: Request):
    """
    Body: raw WAV bytes (Content-Type: audio/wav), 16 kHz mono 16-bit.
    Returns: {"transcript": str, "ticker": str | null, "latency_ms": int}
    """
    body = await request.body()

    if not body:
        raise HTTPException(status_code=400, detail="Empty audio body")
    if len(body) > MAX_WAV_BYTES:
        raise HTTPException(status_code=413, detail="Audio too long (max 30 seconds)")
    if body[:4] != b"RIFF" or body[8:12] != b"WAVE":
        raise HTTPException(status_code=400, detail="Expected WAV audio")
    if int.from_bytes(body[24:28], "little") != 16000:
        raise HTTPException(status_code=400, detail="Expected 16 kHz audio")

    try:
        return await transcribe_wav_bytes(body)
    except SpeechUnavailableError as exc:
        logger.warning("Speech unavailable: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        logger.exception("Speech transcription failed")
        raise HTTPException(status_code=500, detail="Transcription failed")
