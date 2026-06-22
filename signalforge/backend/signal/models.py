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


class FinvizSnapshot(BaseModel):
    """Subset of FinViz data surfaced to the frontend."""
    pe_ratio: Optional[float]
    forward_pe: Optional[float]
    peg_ratio: Optional[float]
    profit_margin_pct: Optional[float]
    roe_pct: Optional[float]
    debt_to_equity: Optional[float]
    insider_own_pct: Optional[float]
    net_insider_sentiment: Optional[float]
    insider_buys_90d: Optional[int]
    insider_sells_90d: Optional[int]
    eps_next_5y_pct: Optional[float]
    market_cap_billions: Optional[float]
    beta: Optional[float]
    recent_analyst_actions: list = []
    source: str = "finviz"


class TipRanksSnapshot(BaseModel):
    analyst_consensus: Optional[str]
    price_target_mean: Optional[float]
    price_target_high: Optional[float]
    price_target_low: Optional[float]
    number_of_analysts: Optional[int]
    buy_pct: Optional[float]
    hold_pct: Optional[float]
    sell_pct: Optional[float]
    buy_count: Optional[int]
    hold_count: Optional[int]
    sell_count: Optional[int]
    smart_score: Optional[int]
    upside_to_target_pct: Optional[float]
    source: str = "tipranks"


class FundamentalsDisplay(BaseModel):
    ticker: str
    fundamental_score: float
    score_components: dict
    finviz: Optional[FinvizSnapshot]
    tipranks: Optional[TipRanksSnapshot]
    disclaimer: str = (
        "Fundamental data is for informational context. "
        "fundamental_score feeds into the overall signal weighting."
    )


class SignalOutput(BaseModel):
    """Final signal output from the analysis pipeline."""
    ticker: str = Field(description="Stock ticker symbol")
    signal: str = Field(description="BUY, HOLD, or SELL signal")
    confidence: float = Field(description="Confidence score from 0.0 to 1.0")
    timestamp: datetime = Field(description="Analysis timestamp")
    stocktwits_sentiment: Optional[StockTwitsSentiment] = None
    fundamentals: Optional[FundamentalsDisplay] = None


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
    skip_tipranks: bool = Field(default=True, description="Skip TipRanks API to preserve free tier rate limit")


class AnalysisResponse(BaseModel):
    """Response model for analysis endpoint."""
    signal: SignalOutput
    confidence_breakdown: ConfidenceBreakdown
    analysis_details: dict = Field(description="Detailed analysis results from each agent")