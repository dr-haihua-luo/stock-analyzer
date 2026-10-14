"""
Speech-to-text via Cactus Whistle (pip: cactus-needle, import: needle).

The model is loaded lazily ONCE and reused. Inference is CPU-bound and
blocking, so it runs in a thread pool and is serialised with a lock
(do not assume the engine is thread-safe).

Contract: callers pass 16 kHz mono 16-bit WAV bytes (the browser
produces this). Audio is capped at 30 seconds by the model.
"""

import asyncio
import logging
import re
import tempfile
import threading
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_whistle = None


class SpeechUnavailableError(RuntimeError):
    """Whistle is not installed or the model could not be loaded."""


# Convenience aliases so "apple" -> AAPL. Not exhaustive; extend freely.
COMPANY_ALIASES = {
    "apple": "AAPL", "microsoft": "MSFT", "google": "GOOGL",
    "alphabet": "GOOGL", "amazon": "AMZN", "tesla": "TSLA",
    "nvidia": "NVDA", "meta": "META", "meta platforms": "META",
    "facebook": "META", "netflix": "NFLX", "intel": "INTC",
    "oracle": "ORCL", "salesforce": "CRM", "adobe": "ADBE",
    "paypal": "PYPL", "disney": "DIS", "walmart": "WMT",
    "costco": "COST", "coca cola": "KO", "pepsi": "PEP",
    "pepsico": "PEP", "nike": "NKE", "boeing": "BA",
    "jpmorgan": "JPM", "jp morgan": "JPM", "jpmorgan chase": "JPM",
    "goldman sachs": "GS", "bank of america": "BAC", "visa": "V",
    "mastercard": "MA", "berkshire hathaway": "BRK.B",
    "berkshire": "BRK.B", "exxon": "XOM", "exxon mobil": "XOM",
    "chevron": "CVX", "pfizer": "PFE", "johnson johnson": "JNJ",
    "johnson and johnson": "JNJ", "uber": "UBER", "starbucks": "SBUX",
    "mcdonalds": "MCD", "qualcomm": "QCOM", "broadcom": "AVGO",
    "micron": "MU", "palantir": "PLTR", "shopify": "SHOP",
    "spotify": "SPOT", "snowflake": "SNOW", "coinbase": "COIN",
    "robinhood": "HOOD",
}

_FILLER = {
    "stock", "stocks", "share", "shares", "ticker", "symbol", "the",
    "please", "analyze", "analyse", "for", "of", "inc", "corp",
    "corporation", "company",
}
_TICKER_RE = re.compile(r"^[A-Z]{1,5}(?:\.[A-Z]{1,2})?$")


def parse_ticker(transcript: str) -> Optional[str]:
    """
    Turn a spoken transcript into a ticker, or None if no confident match.

    Handles, in order:
      1. company names            "Apple." / "meta platforms"
      2. spelled-out letters      "A A P L" / "a.a.p.l." / "B R K dot B"
      3. a single word as symbol  "nvda"
      4. a company name inside a longer phrase
                                  "analyze Microsoft stock please"
    """
    if not transcript:
        return None

    cleaned = transcript.lower().replace("'", "")
    cleaned = re.sub(r"[^a-z0-9.\s]", " ", cleaned)
    tokens = [t for t in cleaned.split()
              if t.strip(".") and t.strip(".") not in _FILLER]
    if not tokens:
        return None

    # 1. whole phrase is a company name
    phrase = " ".join(t.strip(".") for t in tokens)
    if phrase in COMPANY_ALIASES:
        return COMPANY_ALIASES[phrase]

    # 2. spelled out letter by letter
    letters = []
    for tok in tokens:
        if tok == "dot":
            letters.append(".")
        elif re.fullmatch(r"[a-z]", tok) or re.fullmatch(r"(?:[a-z]\.)+[a-z]?", tok):
            letters.append(tok.replace(".", "").upper())
        else:
            letters = None
            break
    if letters:
        candidate = "".join(letters)
        if _TICKER_RE.match(candidate):
            return candidate

    # 3. a single word read as a symbol
    if len(tokens) == 1:
        candidate = tokens[0].strip(".").upper()
        if _TICKER_RE.match(candidate):
            return candidate

    # 4. a known company name anywhere in a longer phrase
    for tok in tokens:
        sym = COMPANY_ALIASES.get(tok.strip("."))
        if sym:
            return sym

    return None


def _bias_keywords() -> list:
    """Company names and symbols to bias the decoder toward."""
    return sorted(set(COMPANY_ALIASES.keys()) | set(COMPANY_ALIASES.values()))


def _get_whistle():
    global _whistle
    if _whistle is None:
        try:
            import needle
        except ImportError as exc:
            raise SpeechUnavailableError(
                "cactus-needle is not installed. Run: uv pip install cactus-needle"
            ) from exc
        try:
            _whistle = needle.Whistle()
        except Exception as exc:
            raise SpeechUnavailableError(f"Could not load Whistle: {exc}") from exc
        logger.info("Whistle speech model loaded")
    return _whistle


def _transcribe_sync(wav_bytes: bytes) -> str:
    with _lock:
        whistle = _get_whistle()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "clip.wav"
            path.write_bytes(wav_bytes)
            try:
                out = whistle.transcribe(str(path), keywords=_bias_keywords())
            except TypeError:
                # this build does not accept keywords=
                out = whistle.transcribe(str(path))
    return (out.get("text") or "").strip() if isinstance(out, dict) else str(out).strip()


async def transcribe_wav_bytes(wav_bytes: bytes) -> dict:
    start = time.perf_counter()
    loop = asyncio.get_running_loop()
    transcript = await loop.run_in_executor(None, _transcribe_sync, wav_bytes)
    ticker = parse_ticker(transcript)
    ms = round((time.perf_counter() - start) * 1000)
    logger.info("Speech: %r -> %s (%d ms)", transcript, ticker, ms)
    return {"transcript": transcript, "ticker": ticker, "latency_ms": ms}
