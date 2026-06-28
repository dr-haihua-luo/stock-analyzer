from typing import TypedDict, List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field
from pydantic import BaseModel


class AnalysisState(TypedDict):
    """State definition for the LangGraph analysis pipeline."""
    ticker: str
    skip_tipranks: bool
    market_data: Optional[Dict[str, Any]]
    sector_data: Optional[Dict[str, Any]]
    stock_data: Optional[Dict[str, Any]]
    fundamentals: Optional[Any]  # FundamentalsResult — for display only
    analysis_result: Optional[Dict[str, Any]]
    signal_output: Optional[Dict[str, Any]]
    confidence_breakdown: Optional[Dict[str, Any]]
    reasoning: Optional[List[str]]  # LLM narratives with [market], [sector], [stock] prefixes
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