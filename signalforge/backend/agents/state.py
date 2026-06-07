from typing import TypedDict, List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field
from pydantic import BaseModel


class AnalysisState(TypedDict):
    """State definition for the LangGraph analysis pipeline."""
    ticker: str
    market_data: Optional[Dict[str, Any]]
    sector_data: Optional[Dict[str, Any]]
    stock_data: Optional[Dict[str, Any]]
    analysis_result: Optional[Dict[str, Any]]
    signal_output: Optional[Dict[str, Any]]
    confidence_breakdown: Optional[Dict[str, Any]]
    error: Optional[str]
    timestamp: datetime
    retry_count: int

class StockContext(BaseModel):
    ticker: str
    current_price: float
    rsi_14: float
    macd_signal: str           # "bullish" | "bearish" | "neutral"
    bb_position: str           # "above_upper" | "within" | "below_lower"
    volume_trend: str          # "increasing" | "decreasing" | "neutral"
    pe_ratio: Optional[float]
    price_vs_52w_high: float   # percentage
    news_sentiment: float      # -1.0 to 1.0
    technical_score: float     # -1.0 to 1.0
    fundamental_score: float   # -1.0 to 1.0


class SignalOutput(BaseModel):
    """Final signal output model."""
    ticker: str = Field(description="Stock ticker symbol")
    signal: str = Field(description="BUY, HOLD, or SELL signal")
    confidence: float = Field(description="Confidence score from 0.0 to 1.0")
    timestamp: datetime = Field(description="Analysis timestamp")


class ConfidenceBreakdown(BaseModel):
    """Breakdown of confidence factors."""
    market_factor: float = Field(description="Contribution from market analysis (0.0-1.0)")
    sector_factor: float = Field(description="Contribution from sector analysis (0.0-1.0)")
    stock_factor: float = Field(description="Contribution from stock analysis (0.0-1.0)")
    total_confidence: float = Field(description="Weighted total confidence (0.0-1.0)")