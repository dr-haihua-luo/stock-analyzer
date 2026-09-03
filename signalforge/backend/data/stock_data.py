import asyncio
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Optional
from io import StringIO

import logging
import numpy as np
import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import MACD
from ta.volatility import BollingerBands

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.historical.news import NewsClient
from alpaca.data.requests import (
    NewsRequest,
    StockBarsRequest,
    StockLatestTradeRequest,
    StockSnapshotRequest,
)
from alpaca.data.timeframe import TimeFrame
from alpaca.data.enums import Adjustment, DataFeed

from backend.config import settings
from backend.cache.redis_client import redis_client

logger = logging.getLogger(__name__)

# Cache TTLs for stock data
OHLCV_CACHE_TTL = 900   # 15 minutes — bars only close once per day
                         # but allow intraday refresh without thrash
PRICE_CACHE_TTL = 60      # 1 minute — price genuinely moves intraday,
                          # but this prevents two calls 5 seconds apart
                          # from hitting two different quote ticks

# --- Client singletons (credentials injected from settings, never hardcoded) ---
_stock_client = StockHistoricalDataClient(
    api_key=settings.APCA_API_KEY_ID,
    secret_key=settings.APCA_API_SECRET_KEY,
    # url_override="https://paper-api.alpaca.markets",
)

_news_client = NewsClient(
    api_key=settings.APCA_API_KEY_ID,
    secret_key=settings.APCA_API_SECRET_KEY,
    # url_override="https://paper-api.alpaca.markets",
)


# ---------------------------------------------------------------------------
# OHLCV bars — 6 months of daily bars
# ---------------------------------------------------------------------------
async def fetch_ohlcv(ticker: str) -> pd.DataFrame:
    """
    Returns a DataFrame with columns: open, high, low, close, volume
    indexed by timestamp. Raises ValueError if no data returned.
    Uses Redis caching to prevent signal instability from API noise.
    """
    cache_key = f"data:ohlcv:{ticker.upper()}"

    cached = await redis_client.get_raw(cache_key)
    if cached:
        df = pd.read_json(StringIO(cached), orient="split")
        # Ensure index is datetime64[ns, UTC] for proper comparison with compute_52w_metrics
        df.index = pd.to_datetime(df.index, utc=True)
        return df

    end   = datetime.now(timezone.utc)
    start = end - timedelta(days=500)  # extended for 12mo MA trend calc

    request = StockBarsRequest(
        symbol_or_symbols=ticker,
        timeframe=TimeFrame.Day,
        start=start,
        end=end,
        feed=DataFeed.IEX, # for free paper trading account
        adjustment="all",       # corporate action adjusted
    )
    bars = _stock_client.get_stock_bars(request)
    df = bars.df
    logger.info(f"Stock Bars {ticker} data received: {df}")

    if df is None or df.empty:
        raise ValueError(f"Alpaca returned no bar data for ticker: {ticker}")

    # bars.df returns a multi-index (symbol, timestamp); drop the symbol level
    if isinstance(df.index, pd.MultiIndex):
        df = df.xs(ticker, level="symbol")

    df.index = pd.to_datetime(df.index, utc=True)
    df = df.rename(columns={
        "open": "open", "high": "high", "low": "low",
        "close": "close", "volume": "volume",
    })
    df = df[["open", "high", "low", "close", "volume"]].sort_index()

    # Ensure numeric types for all columns to avoid comparison issues
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Cache the result
    await redis_client.set_raw(cache_key, df.to_json(orient="split"), ttl=OHLCV_CACHE_TTL)
    return df


# ---------------------------------------------------------------------------
# Latest quote — for current price
# ---------------------------------------------------------------------------
async def fetch_latest_price(ticker: str) -> float:
    """
    Returns the latest traded price (last trade) from Alpaca.
    Uses Redis caching to prevent signal instability from quote tick noise.
    """
    cache_key = f"data:price:{ticker.upper()}"

    cached = await redis_client.get_raw(cache_key)
    if cached:
        return float(cached)

    request = StockLatestTradeRequest(symbol_or_symbols=ticker, feed=DataFeed.IEX)
    trades  = _stock_client.get_stock_latest_trade(request)
    trade   = trades[ticker]

    logger.info(f"Stock latest trade {ticker} data received: {trade}")
    price   = trade.price
    if not price or price <= 0:
        raise ValueError(f"Could not retrieve valid latest price for {ticker}")

    # Cache the price
    await redis_client.set_raw(cache_key, str(price), ttl=PRICE_CACHE_TTL)
    return float(price)


# ---------------------------------------------------------------------------
# Snapshot — 52-week high/low + fundamentals proxy
# ---------------------------------------------------------------------------
def fetch_snapshot(ticker: str) -> dict:
    """
    Returns a dict with keys: prev_close, daily_change_pct.
    Note: Alpaca snapshot does not include P/E; fundamentals come from
    fetch_fundamentals() below via the Alpaca data API.
    """
    request  = StockSnapshotRequest(symbol_or_symbols=ticker)
    snapshot = _stock_client.get_stock_snapshot(request)
    snap     = snapshot[ticker]

    logger.info(f"Stock snapshot {ticker} data received: {snap}")
 
    return {
        "prev_close":        snap.previous_daily_bar.close if snap.previous_daily_bar else None,
        "daily_change_pct":  snap.daily_bar.percent_change if snap.daily_bar else None,
    }


# ---------------------------------------------------------------------------
# 52-week high derived from bar data
# ---------------------------------------------------------------------------
def compute_52w_metrics(df: pd.DataFrame, current_price: float) -> dict:
    """Compute 52-week high/low from the OHLCV dataframe."""
    year_ago_ts = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=365)
    # Ensure the index is in a compatible format for comparison
    # Convert to datetime64[ns, UTC] if not already
    df_index = pd.to_datetime(df.index, utc=True)
    yearly = df[df_index >= year_ago_ts]
    high_52w = float(yearly["high"].max()) if not yearly.empty else current_price
    low_52w  = float(yearly["low"].min())  if not yearly.empty else current_price
    pct_from_high = ((current_price - high_52w) / high_52w) * 100
    return {
        "high_52w":        high_52w,
        "low_52w":         low_52w,
        "pct_from_52w_high": round(pct_from_high, 2),
    }


# ---------------------------------------------------------------------------
# Technical indicators — RSI, MACD, Bollinger Bands, volume trend
# ---------------------------------------------------------------------------
def compute_technicals(df: pd.DataFrame) -> dict:
    """
    Compute RSI(14), MACD signal, Bollinger Band position, and volume trend.
    All computed with the `ta` library on the close/volume series.
    """
    close  = df["close"]
    volume = df["volume"]

    # RSI
    rsi_indicator = RSIIndicator(close=close, window=14)
    rsi = float(rsi_indicator.rsi().iloc[-1])

    # MACD
    macd_indicator = MACD(close=close)
    macd_line   = macd_indicator.macd().iloc[-1]
    signal_line = macd_indicator.macd_signal().iloc[-1]
    if macd_line > signal_line:
        macd_signal = "bullish"
    elif macd_line < signal_line:
        macd_signal = "bearish"
    else:
        macd_signal = "neutral"

    # Bollinger Bands
    bb = BollingerBands(close=close, window=20, window_dev=2)
    bb_upper = bb.bollinger_hband().iloc[-1]
    bb_lower = bb.bollinger_lband().iloc[-1]
    last_close = float(close.iloc[-1])
    if last_close > bb_upper:
        bb_position = "above_upper"
    elif last_close < bb_lower:
        bb_position = "below_lower"
    else:
        bb_position = "within"

    # Volume trend: 5-day avg vs 20-day avg
    vol_5d  = float(volume.iloc[-5:].mean())
    vol_20d = float(volume.iloc[-20:].mean())
    if vol_5d > vol_20d * 1.1:
        volume_trend = "increasing"
    elif vol_5d < vol_20d * 0.9:
        volume_trend = "decreasing"
    else:
        volume_trend = "neutral"

    return {
        "rsi_14":       round(rsi, 2),
        "macd_signal":  macd_signal,
        "bb_position":  bb_position,
        "volume_trend": volume_trend,
    }


# ---------------------------------------------------------------------------
# Technical score: -1.0 to +1.0
# ---------------------------------------------------------------------------
def compute_technical_score(technicals: dict, price_vs_52w_high: float) -> float:
    score = 0.0

    # RSI component (weight 0.35)
    rsi = technicals["rsi_14"]
    if rsi < 30:
        score += 0.35        # oversold → bullish signal
    elif rsi > 70:
        score -= 0.35        # overbought → bearish signal
    else:
        score += 0.35 * ((rsi - 50) / -20)  # linear between 30-70

    # MACD component (weight 0.30)
    if technicals["macd_signal"] == "bullish":
        score += 0.30
    elif technicals["macd_signal"] == "bearish":
        score -= 0.30

    # Bollinger Band component (weight 0.20)
    if technicals["bb_position"] == "below_lower":
        score += 0.20
    elif technicals["bb_position"] == "above_upper":
        score -= 0.20

    # Volume trend component (weight 0.15)
    if technicals["volume_trend"] == "increasing":
        score += 0.15
    elif technicals["volume_trend"] == "decreasing":
        score -= 0.15

    return round(max(-1.0, min(1.0, score)), 4)


# ---------------------------------------------------------------------------
# Price range projection — volatility-based statistical projection
# ---------------------------------------------------------------------------
def compute_price_range_projection(
    df: pd.DataFrame,
    current_price: float,
    vix_regime: Optional[str] = None,
) -> dict:
    """
    Computes statistically-projected price ranges at 68%, 90%, and
    95% confidence levels for 2-day, 1-week, 2-week, and 1-month
    horizons.

    This is a VOLATILITY-BASED STATISTICAL PROJECTION, not a
    prediction. It answers: "given how much this stock has moved
    historically, what price range would we expect X% of the time?"
    It says nothing about DIRECTION — ranges are always centered on
    the current price.

    Method: log-normal price distribution using realized volatility
    (annualized std dev of daily log returns), scaled by sqrt(time)
    per the standard random-walk assumption for equity prices.

    VIX regime adjustment: when implied vol (VIX regime) suggests
    more uncertainty than the stock's own recent realized vol, the
    range widens using a regime multiplier. Never narrows — realized
    vol is treated as a floor.

    Returns dict with keys:
      daily_volatility_pct   — annualized realized vol %
      vix_adjustment_applied — bool
      ranges: {
        "2_day":   { "68pct": {...}, "90pct": {...}, "95pct": {...} },
        "1_week":  { ... },
        "2_week":  { ... },
        "1_month": { ... },
      }
    """

    close = df["close"]

    if len(close) < 30:
        return {
            "daily_volatility_pct": None,
            "vix_adjustment_applied": False,
            "ranges": {},
        }

    # Log returns — standard for volatility calculations
    log_returns = np.log(close / close.shift(1)).dropna()

    # Use the most recent 60 trading days for realized vol —
    # long enough to smooth noise, short enough to reflect current regime
    recent_returns = log_returns.iloc[-60:] if len(log_returns) >= 60 else log_returns

    daily_sigma = float(recent_returns.std())
    annualized_sigma = daily_sigma * np.sqrt(252)

    # VIX regime multiplier — widen if implied vol regime suggests
    # more uncertainty than recent realized vol indicates.
    # Never narrows below realized vol (multiplier floor is 1.0).
    VIX_MULTIPLIERS = {
        "low": 1.00,
        "normal": 1.00,
        "elevated": 1.10,
        "high": 1.25,
        "extreme": 1.50,
    }
    multiplier = VIX_MULTIPLIERS.get(vix_regime, 1.00)
    adjusted_sigma = daily_sigma * multiplier
    vix_adjustment_applied = multiplier > 1.00

    Z_SCORES = {
        "68pct": 1.000,   # ~1 standard deviation
        "90pct": 1.645,
        "95pct": 1.960,
    }
    HORIZONS = {
        "2_day":   2,     # 2 trading days
        "1_week":  5,     # 5 trading days
        "2_week":  10,    # existing
        "1_month": 21,    # existing
    }

    ranges = {}
    for horizon_label, trading_days in HORIZONS.items():
        horizon_ranges = {}
        for conf_label, z in Z_SCORES.items():
            move = adjusted_sigma * z * np.sqrt(trading_days)
            upper = current_price * np.exp(move)
            lower = current_price * np.exp(-move)
            horizon_ranges[conf_label] = {
                "low": round(float(lower), 2),
                "high": round(float(upper), 2),
            }
        ranges[horizon_label] = horizon_ranges

    return {
        "daily_volatility_pct": round(annualized_sigma * 100, 2),
        "vix_adjustment_applied": vix_adjustment_applied,
        "vix_multiplier": round(multiplier, 2),
        "ranges": ranges,
    }


# ---------------------------------------------------------------------------
# News sentiment via Alpaca NewsClient
# ---------------------------------------------------------------------------
def fetch_news_sentiment(ticker: str) -> tuple:
    """
    Fetches last 30 days of news headlines for the ticker via Alpaca NewsClient.
    Computes a simple keyword-based sentiment score in range -1.0 to +1.0.
    Returns (sentiment, news_summary) tuple on success.
    Returns (0.0, []) on any error (non-fatal — sentiment is supplementary).
    """
    POSITIVE_WORDS = {
        "beat", "beats", "surge", "surges", "record", "profit", "upgrade",
        "buy", "strong", "growth", "raised", "raises", "bullish", "outperform",
        "revenue", "gains", "positive", "upbeat", "better", "exceeds",
    }
    NEGATIVE_WORDS = {
        "miss", "misses", "drop", "drops", "loss", "downgrade", "sell",
        "weak", "decline", "cut", "cuts", "bearish", "underperform",
        "warning", "negative", "disappoints", "worse", "below", "layoffs",
    }

    try:
        start = datetime.now(timezone.utc) - timedelta(days=10)
        request = NewsRequest(
            symbols=ticker,
            start=start,
            limit=15,
            include_content=False,
            exclude_contentless=True,
        )
        news    = _news_client.get_news(request)
        articles = news.data["news"] if hasattr(news, "data") else []
        logger.info(f"Stock news {ticker} article received: {len(articles)}")
 
        if not articles:
            return 0.0, []

        scores = []
        news_summary = []
        for article in articles:
            text  = getattr(article, "summary",  "").lower()
            #logger.info(f"Stock news for {ticker}: {text}")
            news_summary.append({ "summary": getattr(article, "summary", "")})
            words = set(text.split())
            pos = len(words & POSITIVE_WORDS)
            neg = len(words & NEGATIVE_WORDS)
            if pos + neg > 0:
                scores.append((pos - neg) / (pos + neg))

        return round(float(np.mean(scores)), 4) if scores else 0.0, news_summary

    except Exception:
        return 0.0, []  # sentiment is best-effort; never block the pipeline


# ---------------------------------------------------------------------------
# Fundamental score proxy (Alpaca does not provide P/E natively)
# ---------------------------------------------------------------------------
def compute_fundamental_score(
    df: pd.DataFrame,
    price_vs_52w_high: float,
) -> float:
    """
    Alpaca's market data API does not include P/E ratios. Compute a
    fundamental proxy from price momentum and distance from 52-week high.

    This is explicitly documented in the rationale output as a proxy.
    If you later add a fundamentals provider (e.g. Polygon, FMP), replace
    this function — the signature must remain identical.
    """
    score = 0.0

    # 1-month price momentum (weight 0.50)
    if len(df) >= 21:
        one_month_return = (df["close"].iloc[-1] / df["close"].iloc[-21] - 1)
        score += 0.50 * max(-1.0, min(1.0, one_month_return * 5))

    # Distance from 52-week high (weight 0.50)
    # Deep discount = bullish fundamental; near all-time high = less upside
    if price_vs_52w_high < -30:
        score += 0.50
    elif price_vs_52w_high < -10:
        score += 0.25
    elif price_vs_52w_high > -5:
        score -= 0.20

    return round(max(-1.0, min(1.0, score)), 4)


# ---------------------------------------------------------------------------
# Moving average trend indicators (informational only — does not affect signal)
# ---------------------------------------------------------------------------
MA_TREND_WINDOWS = {
    "long":   252,  # ~12 months trading days
    "medium": 42,   # ~2 months trading days
    "short":  10,   # ~2 weeks trading days
}

# How many recent MA points to fit a slope over — smooths day-to-day
# noise while still being responsive enough to catch genuine reversals.
MA_TREND_LOOKBACK = {
    "long":   20,
    "medium": 10,
    "short":  5,
}


def compute_ma_trends(df: pd.DataFrame) -> dict:
    """
    Computes long/medium/short-term moving average trend direction.

    For each window, builds the MA series, takes the most recent
    N points of that series (MA_TREND_LOOKBACK), fits a linear
    regression, and classifies the slope sign as "up" or "down".

    This measures whether the MOVING AVERAGE ITSELF is rising or
    falling — not whether price is above/below it — which correctly
    distinguishes cases like "price bounced above a still-declining
    long-term MA" from "long-term MA has turned up."

    Returns dict with keys:
      long_term_ma_trend, medium_term_ma_trend, short_term_ma_trend
        — each "up" | "down" | None (None if insufficient data)
      long_term_ma_value, medium_term_ma_value, short_term_ma_value
        — the current MA value, for display context
    """
    close = df["close"]
    result = {}

    for label, window in MA_TREND_WINDOWS.items():
        lookback = MA_TREND_LOOKBACK[label]
        min_required = window + lookback

        if len(close) < min_required:
            result[f"{label}_term_ma_trend"] = None
            result[f"{label}_term_ma_value"] = None
            logger.debug(
                "MA trend skip (%s): need %d points, have %d",
                label, min_required, len(close)
            )
            continue

        ma_series = close.rolling(window).mean().dropna()
        recent    = ma_series.iloc[-lookback:]

        x     = np.arange(len(recent))
        slope = np.polyfit(x, recent.values, 1)[0]

        result[f"{label}_term_ma_trend"] = "up" if slope > 0 else "down"
        result[f"{label}_term_ma_value"] = round(float(ma_series.iloc[-1]), 2)

    return result