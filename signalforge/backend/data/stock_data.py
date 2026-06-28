import asyncio
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Optional

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
    StockLatestQuoteRequest,
    StockSnapshotRequest,
)
from alpaca.data.timeframe import TimeFrame
from alpaca.data.enums import Adjustment, DataFeed

from backend.config import settings

logger = logging.getLogger(__name__)

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
def fetch_ohlcv(ticker: str) -> pd.DataFrame:
    """
    Returns a DataFrame with columns: open, high, low, close, volume
    indexed by timestamp. Raises ValueError if no data returned.
    """
    end   = datetime.now(timezone.utc)
    start = end - timedelta(days=182)

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
    return df[["open", "high", "low", "close", "volume"]].sort_index()


# ---------------------------------------------------------------------------
# Latest quote — for current price
# ---------------------------------------------------------------------------
def fetch_latest_price(ticker: str) -> float:
    """Returns the latest ask price (falls back to last trade price)."""
    request = StockLatestQuoteRequest(symbol_or_symbols=ticker)
    quotes  = _stock_client.get_stock_latest_quote(request)
    quote   = quotes[ticker]

    logger.info(f"Stock latest quote {ticker} data received: {quote}")
    price   = quote.ask_price or quote.bid_price
    if not price or price <= 0:
        raise ValueError(f"Could not retrieve valid latest price for {ticker}")
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
    year_ago = datetime.now(timezone.utc) - timedelta(days=365)
    yearly   = df[df.index >= year_ago]
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
            logger.info(f"Stock news for {ticker}: {text}")
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