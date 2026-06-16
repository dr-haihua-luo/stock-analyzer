"""StockTwits sentiment data layer.

No authentication required.
Calls /streams/symbol/{symbol}.json, parses user-tagged sentiment
(bullish / bearish / None) from the last 30 messages.
Computes percentages from only labeled messages; unlabeled → neutral bucket.

On any network error, auth failure, or unexpected response shape:
Returns SentimentResult with source="unavailable" and all percentages null.
Logs the error at WARNING level. Never raises to the caller.
"""

import logging
from dataclasses import dataclass
from typing import Optional
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)

PUBLIC_STREAM_BASE = "https://api.stocktwits.com/api/2"
TIMEOUT = 8.0  # seconds


@dataclass
class SentimentResult:
    ticker: str
    source: str                      # "public_stream" | "unavailable"
    bullish_pct: Optional[float]     # 0.0–100.0
    bearish_pct: Optional[float]
    neutral_pct: Optional[float]
    sentiment_label: Optional[str]   # "BULLISH" | "BEARISH" | "NEUTRAL"
    message_volume_label: Optional[str]   # "LOW" | "NORMAL" | "HIGH"
    message_volume_24h: Optional[float]
    participation_score: Optional[float]
    total_messages_sampled: Optional[int]  # number of messages parsed (public API)
    labeled_messages: Optional[int]        # messages with explicit sentiment tag
    fetched_at: str = ""

    def __post_init__(self):
        if not self.fetched_at:
            self.fetched_at = datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
async def fetch_stocktwits_sentiment(ticker: str) -> SentimentResult:
    """Fetch StockTwits sentiment. Public stream used; no credentials required."""
    return await _fetch_public_stream(ticker)


# ---------------------------------------------------------------------------
# Public Stream API (no auth required)
# ---------------------------------------------------------------------------
async def _fetch_public_stream(ticker: str) -> SentimentResult:
    """
    Calls GET https://api.stocktwits.com/api/2/streams/symbol/{symbol}.json
    Parses the last 30 messages for user-tagged sentiment.

    Each message has: entities.sentiment = {"basic": "Bullish"} | {"basic": "Bearish"} | null
    Note: only ~30-50% of messages carry an explicit sentiment tag.
    Messages without a tag count toward the "neutral" bucket.
    """
    url = f"{PUBLIC_STREAM_BASE}/streams/symbol/{ticker}.json"
    logger.info("Calling StockTwits public stream for %s", ticker)
    try:
        # Use default httpx client - Cloudflare may block Python clients in some environments.
        # The code handles 403 gracefully by returning source="unavailable"
        async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(url)

        if resp.status_code == 404:
            logger.warning("StockTwits: ticker %s not found on public stream", ticker)
            return _unavailable(ticker)
        if resp.status_code == 429:
            logger.warning("StockTwits: rate limited on public stream for %s", ticker)
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
            sentiment_tag = (
                msg.get("entities", {})
                .get("sentiment", {})
            )
            if not sentiment_tag:
                neutral_count += 1
                continue
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

        # Derive label from labeled messages only (ignore untagged for label)
        if labeled_count > 0:
            bullish_ratio = bullish_count / labeled_count
            if bullish_ratio >= 0.6:
                label = "BULLISH"
            elif bullish_ratio <= 0.4:
                label = "BEARISH"
            else:
                label = "NEUTRAL"
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