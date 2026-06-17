"""
StockTwits sentiment data layer.

Uses curl_cffi instead of httpx for all HTTP calls to bypass Cloudflare
TLS fingerprint detection. curl_cffi impersonates a real Chrome browser
at the TLS handshake level (cipher suites, extension order, HTTP/2
SETTINGS frames), producing a JA3/JA4 fingerprint indistinguishable
from a real browser. This is the only reliable fix for Cloudflare 403
errors from server-side Python async runtimes.

httpx is intentionally NOT used in this file. Do not reintroduce it.

Use Public stream API (free): no auth, per-message sentiment tags ONLY
"""

import logging
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime, timezone

from curl_cffi.requests import AsyncSession

logger = logging.getLogger(__name__)


PUBLIC_STREAM_BASE = "https://api.stocktwits.com/api/2"

# Impersonate Chrome — produces a real browser JA3/JA4 TLS fingerprint.
# "chrome" always resolves to the latest supported Chrome version in curl_cffi.
# This is what bypasses Cloudflare's bot detection.
BROWSER_IMPERSONATION = "chrome"

TIMEOUT = 10.0  # seconds — slightly higher than httpx default to allow TLS negotiation


@dataclass
class SentimentResult:
    ticker: str
    source: str                           # "public_stream" | "unavailable"
    bullish_pct: Optional[float]
    bearish_pct: Optional[float]
    neutral_pct: Optional[float]
    sentiment_label: Optional[str]        # "BULLISH" | "BEARISH" | "NEUTRAL"
    message_volume_label: Optional[str]
    message_volume_24h: Optional[float]
    participation_score: Optional[float]
    total_messages_sampled: Optional[int]
    labeled_messages: Optional[int]
    fetched_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
async def fetch_stocktwits_sentiment(ticker: str) -> SentimentResult:
    """
    Main entry point. Uses public stream API, returns unavailable on all failures.

    Uses curl_cffi.AsyncSession with Chrome impersonation for all requests.
    The AsyncSession is created fresh per call — do not share a session
    across the FastAPI event loop as curl_cffi sessions are not thread-safe.
    """

    return await _fetch_public_stream(ticker)


# ---------------------------------------------------------------------------
# Shared session factory
# ---------------------------------------------------------------------------
def _make_session() -> AsyncSession:
    """
    Creates a curl_cffi AsyncSession that impersonates Chrome.

    impersonate="chrome" sets:
    - TLS cipher suite order matching Chrome's BoringSSL
    - TLS extension order and values matching Chrome
    - HTTP/2 SETTINGS and WINDOW_UPDATE frames matching Chrome
    - ALPN negotiation order matching Chrome

    This produces a JA3/JA4 fingerprint that Cloudflare classifies as
    legitimate browser traffic, bypassing bot detection.
    """
    return AsyncSession(
        impersonate=BROWSER_IMPERSONATION,
        timeout=TIMEOUT,
        verify=True,  # always verify TLS certificates
    )



# ---------------------------------------------------------------------------
# Public Stream API
# ---------------------------------------------------------------------------
async def _fetch_public_stream(ticker: str) -> SentimentResult:
    """
    Calls GET https://api.stocktwits.com/api/2/streams/symbol/{symbol}.json
    Parses user-tagged bullish/bearish sentiment from the last 30 messages.
    Uses curl_cffi with Chrome impersonation.
    """
    url = f"{PUBLIC_STREAM_BASE}/streams/symbol/{ticker}.json"
    params: dict = {"limit": 30}

    logger.info("calling public StockTwits for %s", ticker)

    try:
        async with _make_session() as session:
            resp = await session.get(url, params=params)

        if resp.status_code == 404:
            logger.warning("StockTwits: ticker %s not found (404)", ticker)
            return _unavailable(ticker)

        if resp.status_code == 429:
            logger.warning("StockTwits: rate limited (429) for %s", ticker)
            return _unavailable(ticker)

        if resp.status_code != 200:
            logger.warning(
                "StockTwits public stream: status %s for %s",
                resp.status_code, ticker
            )
            return _unavailable(ticker)

        messages = resp.json().get("messages", [])
        if not messages:
            return _unavailable(ticker)

        bullish_count = 0
        bearish_count = 0
        neutral_count = 0
        labeled_count = 0

        for msg in messages:
            sentiment_tag = msg.get("entities", {}).get("sentiment") or {}
            basic = (sentiment_tag.get("basic") or "").lower()
            if basic == "bullish":
                bullish_count += 1
                labeled_count += 1
            elif basic == "bearish":
                bearish_count += 1
                labeled_count += 1
            else:
                neutral_count += 1

        total = len(messages)
        bullish_pct = round(bullish_count / total * 100, 1)
        bearish_pct = round(bearish_count / total * 100, 1)
        neutral_pct = round(neutral_count / total * 100, 1)

        if labeled_count > 0:
            bullish_ratio = bullish_count / labeled_count
            label = (
                "BULLISH" if bullish_ratio >= 0.6
                else "BEARISH" if bullish_ratio <= 0.4
                else "NEUTRAL"
            )
        else:
            label = "NEUTRAL"

        return SentimentResult(
            ticker=ticker,
            source="public_stream",
            bullish_pct=bullish_pct,
            bearish_pct=bearish_pct,
            neutral_pct=neutral_pct,
            sentiment_label=label,
            message_volume_label=None,
            message_volume_24h=None,
            participation_score=None,
            total_messages_sampled=total,
            labeled_messages=labeled_count,
        )

    except Exception as exc:
        logger.warning("StockTwits public stream error for %s: %s", ticker, exc)
        return _unavailable(ticker)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _unavailable(ticker: str) -> SentimentResult:
    return SentimentResult(
        ticker=ticker,
        source="unavailable",
        bullish_pct=None,
        bearish_pct=None,
        neutral_pct=None,
        sentiment_label=None,
        message_volume_label=None,
        message_volume_24h=None,
        participation_score=None,
        total_messages_sampled=None,
        labeled_messages=None,
    )