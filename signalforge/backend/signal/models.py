from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class SignalOutput(BaseModel):
    """Final signal output from the analysis pipeline."""
    ticker: str = Field(description="Stock ticker symbol")
    signal: str = Field(description="BUY, HOLD, or SELL signal")
    confidence: float = Field(description="Confidence score from 0.0 to 1.0")
    timestamp: datetime = Field(description="Analysis timestamp")


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