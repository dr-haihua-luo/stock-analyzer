import os
import sys
import pytest

# Add signalforge/backend to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'signalforge', 'backend'))

from data.stocktwits_data import (
    SentimentResult,
    _unavailable,
)


# --- Test fixtures ---

PUBLIC_STREAM_RESPONSE = {
    "messages": [
        {"entities": {"sentiment": {"basic": "Bullish"}}},
        {"entities": {"sentiment": {"basic": "Bullish"}}},
        {"entities": {"sentiment": {"basic": "Bearish"}}},
        {"entities": {"sentiment": None}},
        {"entities": {"sentiment": None}},
    ]
}


# --- Helper to create expected SentimentResult for testing ---
def _make_result(messages: list) -> SentimentResult:
    """Helper to create SentimentResult for test comparison."""
    bullish_count = 0
    bearish_count = 0
    neutral_count = 0
    labeled = 0

    for m in messages:
        sentiment_tag = m.get("entities", {}).get("sentiment") or {}
        basic = (sentiment_tag.get("basic") or "").lower()
        if basic == "bullish":
            bullish_count += 1
            labeled += 1
        elif basic == "bearish":
            bearish_count += 1
            labeled += 1
        else:
            neutral_count += 1

    total = len(messages)
    bullish_pct = round(bullish_count / total * 100, 1) if total else 0.0
    bearish_pct = round(bearish_count / total * 100, 1) if total else 0.0
    neutral_pct = round(neutral_count / total * 100, 1) if total else 0.0

    bullish_ratio = bullish_count / labeled if labeled else 0
    label = (
        "BULLISH" if bullish_ratio >= 0.6
        else "BEARISH" if bullish_ratio <= 0.4
        else "NEUTRAL"
    )

    return SentimentResult(
        ticker="TEST",
        source="public_stream",
        bullish_pct=bullish_pct,
        bearish_pct=bearish_pct,
        neutral_pct=neutral_pct,
        sentiment_label=label,
        message_volume_label=None,
        message_volume_24h=None,
        participation_score=None,
        total_messages_sampled=total,
        labeled_messages=labeled,
    )


def test_sentiment_result_creation():
    """Verify SentimentResult works correctly."""
    result = _make_result(PUBLIC_STREAM_RESPONSE["messages"])
    assert result.source == "public_stream"
    assert result.total_messages_sampled == 5
    assert result.labeled_messages == 3
    assert result.bullish_pct == 40.0
    assert result.bearish_pct == 20.0
    assert result.neutral_pct == 40.0
    assert result.sentiment_label == "BULLISH"


def test_sentiment_label_bullish():
    """Test BULLISH label when bullish ratio >= 0.6."""
    messages = [
        {"entities": {"sentiment": {"basic": "Bullish"}}},
        {"entities": {"sentiment": {"basic": "Bullish"}}},
        {"entities": {"sentiment": {"basic": "Bullish"}}},
    ]
    result = _make_result(messages)
    assert result.sentiment_label == "BULLISH"


def test_sentiment_label_bearish():
    """Test BEARISH label when bullish ratio <= 0.4."""
    messages = [
        {"entities": {"sentiment": {"basic": "Bearish"}}},
        {"entities": {"sentiment": {"basic": "Bearish"}}},
        {"entities": {"sentiment": {"basic": "Bearish"}}},
    ]
    result = _make_result(messages)
    assert result.sentiment_label == "BEARISH"


def test_sentiment_label_neutral():
    """Test NEUTRAL label when bullish ratio is between 0.4 and 0.6."""
    messages = [
        {"entities": {"sentiment": {"basic": "Bullish"}}},
        {"entities": {"sentiment": {"basic": "Bearish"}}},
        {"entities": {"sentiment": {"basic": "Bullish"}}},
        {"entities": {"sentiment": {"basic": "Bearish"}}},
    ]
    result = _make_result(messages)
    assert result.sentiment_label == "NEUTRAL"


def test_unavailable_result():
    """Test _unavailable helper returns correct default values."""
    result = _unavailable("TEST")
    assert result.source == "unavailable"
    assert result.bullish_pct is None
    assert result.bearish_pct is None
    assert result.neutral_pct is None
    assert result.sentiment_label is None
    assert result.total_messages_sampled is None


def test_empty_messages_returns_zero():
    """Test handling of empty message list."""
    result = _make_result([])
    assert result.total_messages_sampled == 0
    assert result.labeled_messages == 0


def test_no_labeled_messages():
    """Test when no messages have sentiment tags."""
    messages = [
        {"entities": {}},
        {"entities": {}},
    ]
    result = _make_result(messages)
    assert result.neutral_pct == 100.0
    assert result.labeled_messages == 0