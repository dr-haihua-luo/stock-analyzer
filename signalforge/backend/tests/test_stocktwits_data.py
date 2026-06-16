import os
import sys
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

# Add the backend directory to the path so we can import from it
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from data.stocktwits_data import (
    fetch_stocktwits_sentiment,
)


# --- Integration-style tests with mocked HTTP ---

PUBLIC_STREAM_RESPONSE = {
    "messages": [
        {"entities": {"sentiment": {"basic": "Bullish"}}},
        {"entities": {"sentiment": {"basic": "Bullish"}}},
        {"entities": {"sentiment": {"basic": "Bearish"}}},
        {"entities": {"sentiment": None}},
        {"entities": {"sentiment": None}},
    ]
}


@pytest.mark.asyncio
async def test_public_stream_success():
    """Test successful public stream response parsing."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = PUBLIC_STREAM_RESPONSE

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client_cls.return_value.__aenter__.return_value.get = AsyncMock(
            return_value=mock_resp
        )
        result = await fetch_stocktwits_sentiment("AAPL")

    assert result.source == "public_stream"
    assert result.total_messages_sampled == 5
    assert result.labeled_messages == 3
    # 2 bullish out of 5 total = 40%
    assert result.bullish_pct == 40.0
    # 1 bearish out of 5 total = 20%
    assert result.bearish_pct == 20.0
    # 2 unlabeled out of 5 total = 40%
    assert result.neutral_pct == 40.0
    # bullish_ratio = 2/3 = 0.67 >= 0.6 → BULLISH
    assert result.sentiment_label == "BULLISH"

    assert result.source == "public_stream"
    assert result.total_messages_sampled == 5
    assert result.labeled_messages == 3
    # 2 bullish out of 5 total = 40%
    assert result.bullish_pct == 40.0
    # 1 bearish out of 5 total = 20%
    assert result.bearish_pct == 20.0
    # 2 unlabeled out of 5 total = 40%
    assert result.neutral_pct == 40.0
    # bullish_ratio = 2/3 = 0.67 >= 0.6 → BULLISH
    assert result.sentiment_label == "BULLISH"


@pytest.mark.asyncio
async def test_public_stream_404_returns_unavailable():
    """Test 404 response returns unavailable sentiment."""
    mock_resp = MagicMock()
    mock_resp.status_code = 404

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client_cls.return_value.__aenter__.return_value.get = AsyncMock(
            return_value=mock_resp
        )
        result = await fetch_stocktwits_sentiment("INVALID")

    assert result.source == "unavailable"
    assert result.bullish_pct is None
    assert result.bearish_pct is None
    assert result.neutral_pct is None


@pytest.mark.asyncio
async def test_public_stream_429_rate_limited():
    """Test rate limited response returns unavailable."""
    mock_resp = MagicMock()
    mock_resp.status_code = 429

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client_cls.return_value.__aenter__.return_value.get = AsyncMock(
            return_value=mock_resp
        )
        result = await fetch_stocktwits_sentiment("AAPL")

    assert result.source == "unavailable"
    assert result.bullish_pct is None


@pytest.mark.asyncio
async def test_public_stream_empty_messages():
    """Test empty messages return unavailable."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"messages": []}

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client_cls.return_value.__aenter__.return_value.get = AsyncMock(
            return_value=mock_resp
        )
        result = await fetch_stocktwits_sentiment("AAPL")

    assert result.source == "unavailable"
    assert result.total_messages_sampled is None


@pytest.mark.asyncio
async def test_network_failure_returns_unavailable():
    """Test network error returns unavailable sentiment."""
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client_cls.return_value.__aenter__.return_value.get = AsyncMock(
            side_effect=Exception("connection refused")
        )
        result = await fetch_stocktwits_sentiment("AAPL")

    assert result.source == "unavailable"
    assert result.bullish_pct is None
    assert result.bearish_pct is None


@pytest.mark.asyncio
async def test_all_bearish():
    """Test all bearish messages."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "messages": [
            {"entities": {"sentiment": {"basic": "Bearish"}}},
            {"entities": {"sentiment": {"basic": "Bearish"}}},
            {"entities": {"sentiment": {"basic": "Bearish"}}},
        ]
    }

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client_cls.return_value.__aenter__.return_value.get = AsyncMock(
            return_value=mock_resp
        )
        result = await fetch_stocktwits_sentiment("AAPL")

    assert result.bullish_pct == 0.0
    assert result.bearish_pct == pytest.approx(100.0, rel=0.01)
    assert result.sentiment_label == "BEARISH"


@pytest.mark.asyncio
async def test_mixed_sentiment_neutral():
    """Test mixed sentiment results in NEUTRAL label."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "messages": [
            {"entities": {"sentiment": {"basic": "Bullish"}}},
            {"entities": {"sentiment": {"basic": "Bearish"}}},
            {"entities": {"sentiment": {"basic": "Bullish"}}},
            {"entities": {"sentiment": {"basic": "Bearish"}}},
        ]
    }

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client_cls.return_value.__aenter__.return_value.get = AsyncMock(
            return_value=mock_resp
        )
        result = await fetch_stocktwits_sentiment("AAPL")

    assert result.bullish_pct == 50.0
    assert result.bearish_pct == 50.0
    assert result.sentiment_label == "NEUTRAL"  # 50/50 split = 0.5 ratio, between 0.4 and 0.6