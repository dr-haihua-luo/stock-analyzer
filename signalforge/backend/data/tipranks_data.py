"""
TipRanks analyst data via the official Python MCP SDK.

The Python MCP SDK (mcp>=1.9.0) handles all of this transparently
via streamablehttp_client. Use it exclusively for TipRanks.

Authentication: Bearer token passed as HTTP header to the transport.
Free tier: 5 requests/minute, 50 requests/month.
Redis TTL: 6 hours.
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime, timezone

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from backend.config import settings

logger = logging.getLogger(__name__)

TIPRANKS_MCP_URL = "https://mcp.tipranks.com/mcp/"
TIMEOUT = 20.0  # seconds — MCP handshake + tool call can take ~5-10s


@dataclass
class TipRanksData:
    ticker: str
    analyst_consensus: Optional[str]       # "Strong Buy" | "Buy" | "Hold" | "Sell" | "Strong Sell"
    price_target_mean: Optional[float]
    price_target_high: Optional[float]
    price_target_low: Optional[float]
    number_of_analysts: Optional[int]
    buy_count: Optional[int]
    hold_count: Optional[int]
    sell_count: Optional[int]
    smart_score: Optional[int]             # 1-10, TipRanks proprietary composite
    buy_pct: Optional[float]
    hold_pct: Optional[float]
    sell_pct: Optional[float]
    upside_to_target_pct: Optional[float]  # (mean_target - current) / current * 100
    fetched_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    source: str = "tipranks"


async def fetch_tipranks_data(
    ticker: str,
    current_price: Optional[float] = None,
    skip: bool = True,
) -> Optional[TipRanksData]:
    """
    Fetch analyst consensus and price targets from TipRanks MCP.

    Uses the Python MCP SDK streamablehttp_client which:
    - Automatically sends Accept: application/json, text/event-stream
    - Runs the initialize → notifications/initialized handshake
    - Tracks Mcp-Session-Id across requests
    - Parses SSE-framed responses transparently

    Returns None if TIPRANKS_API_KEY is not set, or on any error.
    Never raises — all exceptions are caught and logged.
    """
    logger.info(">>> fetch_tipranks_data called: skip=%s, ticker=%s, api_key_set=%s", skip, ticker, bool(settings.TIPRANKS_API_KEY))
    if skip:
        logger.info("TipRanks fetch skipped by caller for %s", ticker)
        return None

    if not settings.TIPRANKS_API_KEY:
        logger.info("TIPRANKS_API_KEY not set — skipping TipRanks fetch")
        return None

    try:
        headers = {
            "Authorization": f"Bearer {settings.TIPRANKS_API_KEY}",
        }

        # streamablehttp_client manages the full MCP session lifecycle:
        # connect → initialize handshake → tool calls → disconnect
        async with streamablehttp_client(
            url=TIPRANKS_MCP_URL,
            headers=headers,
            timeout=TIMEOUT,
        ) as (read_stream, write_stream, _):

            async with ClientSession(read_stream, write_stream) as session:
                # initialize() sends both:
                #   1. initialize request (captures Mcp-Session-Id)
                #   2. notifications/initialized (tells server client is ready)
                # This is mandatory before any tools/call.
                await session.initialize()

                # Call the get_assets_data tool
                result = await session.call_tool(
                    "get_assets_data",
                    arguments={"tickers": [ticker.upper()]},
                )

        return _parse_result(result, ticker, current_price)

    except Exception as exc:
        logger.warning("TipRanks MCP error for %s: %s", ticker, exc)
        return None


def _parse_result(
    result,
    ticker: str,
    current_price: Optional[float],
) -> Optional[TipRanksData]:
    """
    Parse the MCP tool result into a TipRanksData dataclass.

    MCP tool results have a .content list of content blocks.
    Each block has a .type ("text" | "image" | etc.) and .text for text blocks.
    The text is a JSON string containing the actual data.
    """
    try:
        if not result or not result.content:
            logger.warning("TipRanks: empty result content")
            return None

        # Find the first text content block
        text_block = next(
            (b for b in result.content if hasattr(b, "type") and b.type == "text"),
            None,
        )
        if not text_block or not text_block.text:
            logger.warning("TipRanks: no text content block in result")
            return None

        data = json.loads(text_block.text)

        # TipRanks returns data keyed by ticker (uppercase or lowercase)
        stock_data = (
            data.get(ticker.upper())
            or data.get(ticker.lower())
            or data.get(ticker)
        )
        if not stock_data:
            # Some responses nest under a "data" key
            stock_data = (
                data.get("data", {}).get(ticker.upper())
                or data.get("data", {}).get(ticker.lower())
            )

        if not stock_data:
            logger.warning(
                "TipRanks: no data for ticker %s in response keys: %s",
                ticker, list(data.keys())
            )
            return None

        consensus   = stock_data.get("analystConsensus")
        target_mean = _to_float(stock_data.get("priceTarget"))
        target_high = _to_float(stock_data.get("priceTargetHigh"))
        target_low  = _to_float(stock_data.get("priceTargetLow"))
        n_analysts  = _to_int(stock_data.get("numberOfAnalysts"))
        buy_count   = _to_int(stock_data.get("buyCount"))
        hold_count  = _to_int(stock_data.get("holdCount"))
        sell_count  = _to_int(stock_data.get("sellCount"))
        smart_score = _to_int(stock_data.get("smartScore"))

        total    = (buy_count or 0) + (hold_count or 0) + (sell_count or 0)
        buy_pct  = round(buy_count  / total * 100, 1) if total and buy_count  else None
        hold_pct = round(hold_count / total * 100, 1) if total and hold_count else None
        sell_pct = round(sell_count / total * 100, 1) if total and sell_count else None

        upside = None
        if target_mean and current_price and current_price > 0:
            upside = round((target_mean - current_price) / current_price * 100, 2)

        return TipRanksData(
            ticker=ticker.upper(),
            analyst_consensus=consensus,
            price_target_mean=target_mean,
            price_target_high=target_high,
            price_target_low=target_low,
            number_of_analysts=n_analysts,
            buy_count=buy_count,
            hold_count=hold_count,
            sell_count=sell_count,
            smart_score=smart_score,
            buy_pct=buy_pct,
            hold_pct=hold_pct,
            sell_pct=sell_pct,
            upside_to_target_pct=upside,
        )

    except (json.JSONDecodeError, AttributeError, TypeError) as exc:
        logger.warning("TipRanks: failed to parse result for %s: %s", ticker, exc)
        return None


def _to_float(val) -> Optional[float]:
    try:
        return float(val) if val is not None else None
    except (ValueError, TypeError):
        return None


def _to_int(val) -> Optional[int]:
    try:
        return int(val) if val is not None else None
    except (ValueError, TypeError):
        return None