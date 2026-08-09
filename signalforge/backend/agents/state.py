from typing import TypedDict, List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field


class AnalysisState(TypedDict):
    """State definition for the LangGraph analysis pipeline."""
    ticker: str
    skip_tipranks: bool
    previous_signal: Optional[str]  # Previous signal for hysteresis
    market_data: Optional[Dict[str, Any]]
    sector_data: Optional[Dict[str, Any]]
    stock_data: Optional[Dict[str, Any]]
    fundamentals: Optional[Any]  # FundamentalsResult — for display only
    earnings_quality: Optional[Any]  # EarningsQuality dataclass — informational only
    news_articles: Optional[List[dict]]  # raw news summaries from Alpaca
    stocktwits_raw: Optional[Any]  # SentimentResult dataclass
    news_sentiment_narrative: Optional[str]  # LLM output from news_sentiment_agent
    overall_analysis_narrative: Optional[str]  # LLM synthesis from overall_analysis_agent (final verdict)
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

    # MA trend indicators (informational only, do not affect signal)
    long_term_ma_trend: Optional[str] = None      # "up" | "down"
    long_term_ma_value: Optional[float] = None
    medium_term_ma_trend: Optional[str] = None    # "up" | "down"
    medium_term_ma_value: Optional[float] = None
    short_term_ma_trend: Optional[str] = None     # "up" | "down"
    short_term_ma_value: Optional[float] = None


class MarketContext(BaseModel):
    # --- existing fields ---
    vix_value: float
    vix_regime: str
    fear_greed_index: float
    fear_greed_label: str
    yield_curve_spread: float
    yield_curve_signal: str
    macro_regime: str
    market_score: float

    # --- new: major indexes ---
    sp500_level: Optional[float] = None
    sp500_chg_1d_pct: Optional[float] = None
    sp500_chg_5d_pct: Optional[float] = None
    sp500_chg_20d_pct: Optional[float] = None
    nasdaq_chg_20d_pct: Optional[float] = None
    indexes_above_200ma: Optional[int] = None   # 0-4 count

    # --- new: rates ---
    us10y_yield: Optional[float] = None
    us10y_chg_1m_bps: Optional[float] = None
    us30y_yield: Optional[float] = None
    fed_funds_rate: Optional[float] = None

    # --- new: FX ---
    dxy_rate: Optional[float] = None
    dxy_chg_1m_pct: Optional[float] = None

    # --- new: inflation expectations (forward-looking only) ---
    breakeven_10y: Optional[float] = None
    breakeven_5y: Optional[float] = None
    breakeven_10y_chg_1m_bps: Optional[float] = None
    breakeven_trend: Optional[str] = None       # "rising"|"falling"|"stable"
    inflation_data_source: Optional[str] = None # "fred"|"tip_proxy"|"unavailable"