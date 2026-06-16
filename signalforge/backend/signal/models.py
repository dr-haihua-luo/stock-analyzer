from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class StockTwitsSentiment(BaseModel):
    """
    Informational only. Never used in signal scoring.
    Displayed separately at the bottom of the dashboard.
    """
    ticker: str
    source: str                       # "public_stream" | "unavailable"
    bullish_pct: Optional[float]
    bearish_pct: Optional[float]
    neutral_pct: Optional[float]
    sentiment_label: Optional[str]    # "BULLISH" | "BEARISH" | "NEUTRAL"
    message_volume_label: Optional[str]
    message_volume_24h: Optional[float]
    participation_score: Optional[float]
    total_messages_sampled: Optional[int]
    labeled_messages: Optional[int]
    fetched_at: str
    disclaimer: str = (
        "Social sentiment is informational only and does not affect "
        "the BUY/HOLD/SELL signal or confidence score."
    )


class SignalOutput(BaseModel):
    """Final signal output from the analysis pipeline."""
    ticker: str = Field(description="Stock ticker symbol")
    signal: str = Field(description="BUY, HOLD, or SELL signal")
    confidence: float = Field(description="Confidence score from 0.0 to 1.0")
    timestamp: datetime = Field(description="Analysis timestamp")
    stocktwits_sentiment: Optional[StockTwitsSentiment] = None


class ConfidenceBreakdown(BaseModel):
    """Breakdown of confidence factors contributing to the final signal."""
    market_factor: float = Field(description="Contribution from market analysis (0.0-1.0)")
    sector_factor: float = Field(description="Contribution from sector analysis (0.0-1.0)")
    stock_factor: float = Field(description="Contribution from stock analysis (0.0-1.0)")
    total_confidence: float = Field(description="Weighted total confidence (0.0-1.0)")


class AnalysisRequest(BaseModel):
    """Request model for analysis endpoint."""
    ticker: str = Field(description="Stock ticker symbol to analyze")
    force_refresh: bool = Field(default=False, description="Force refresh of cached data")


class AnalysisResponse(BaseModel):
    """Response model for analysis endpoint."""
    signal: SignalOutput
    confidence_breakdown: ConfidenceBreakdown
    analysis_details: dict = Field(description="Detailed analysis results from each agent")