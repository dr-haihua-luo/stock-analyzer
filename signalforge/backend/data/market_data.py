import yfinance as yf
import pandas as pd
from typing import Dict, Any, Optional
import asyncio
import time
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from backend.config import settings
from backend.cache.redis_client import redis_client
import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)


class MarketData:
    def __init__(self):
        self.cache = redis_client

    async def get_vix_data(self) -> Dict[str, Any]:
        """Get VIX data (fear and greed index proxy)."""
        cache_key = "vix_data"
        cached_data = await self.cache.get(cache_key)
        # Validate that cached data is in expected format and timestamp is within 60 minutes
        if cached_data and isinstance(cached_data, dict) and "vix" in cached_data:
            cached_ts = cached_data.get("timestamp")
            if cached_ts:
                try:
                    cached_time = datetime.fromisoformat(cached_ts.replace("Z", "+00:00"))
                    age_seconds = (datetime.now(timezone.utc) - cached_time).total_seconds()
                    if age_seconds < 3600:  # Less than 60 minutes old
                        logger.info(f"Returning cached VIX data (age: {age_seconds:.0f}s)")
                        return cached_data
                    else:
                        logger.info(f"VIX cache expired (age: {age_seconds:.0f}s > 3600s), fetching fresh data")
                except (ValueError, TypeError) as e:
                    logger.warning(f"Failed to parse cached VIX timestamp: {e}")

        try:
            # Fetch VIX data (^VIX) using direct API call with proper headers to avoid JSON decode errors
            url = "https://query1.finance.yahoo.com/v8/finance/chart/%5EVIX"
            params = {
                "range": "5d",
                "interval": "1d"
            }
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }

            session = requests.Session()
            retries = Retry(total=5, backoff_factor=1, status_forcelist=[502, 503, 504])
            session.mount('https://', HTTPAdapter(max_retries=retries))

            logger.info(f"Fetching VIX data from Yahoo Finance: {url}")
            response = session.get(url, params=params, headers=headers)
            logger.info(f"VIX API response status: {response.status_code}")

            if response.status_code != 200:
                logger.error(f"VIX API returned non-200 status: {response.status_code}. Response: {response.text[:200]}")
                raise ValueError(f"Yahoo Finance API returned status {response.status_code}")

            response.raise_for_status()
            data_json = response.json()

            logger.info(f"VIX data received: {len(data_json.get('chart', {}).get('result', []))} {len(response.text)}")

            if not data_json['chart']['result']:
                raise ValueError("No VIX data retrieved")

            result = data_json['chart']['result'][0]
            meta = result['meta']
            timestamps = result['timestamp']
            indicators = result['indicators']['quote'][0]

            if not timestamps or not indicators['close']:
                raise ValueError("No VIX price data available")

            # Filter out None values to get valid closes
            valid_closes = [c for c in indicators['close'] if c is not None]
            if not valid_closes:
                raise ValueError("No valid VIX close prices available")

            current_vix = valid_closes[-1]
            prev_close = valid_closes[-2] if len(valid_closes) > 1 else current_vix

            # Simple fear/greed interpretation (lower VIX = less fear)
            # Normalize to 0-100 scale where 0 is extreme fear, 100 is extreme greed
            # Historical VIX range: typically 10-80, but we'll use 15-35 as normal range for scoring
            fear_greed_score = max(0, min(100, 100 - ((current_vix - 15) * 2)))  # Inverse relationship

            data = {
                "vix": round(current_vix, 2),
                "vix_change": round(((current_vix - prev_close) / prev_close) * 100, 2),
                "fear_greed_score": round(fear_greed_score, 2),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "data_points": len(timestamps)
            }

            logger.info(f"VIX data processed: vix={current_vix:.2f}, change={((current_vix - prev_close) / prev_close) * 100:.2f}%")

            await self.cache.set(cache_key, data, expire=settings.MARKET_DATA_TTL)
            return data

        except Exception as e:
            logger.error(f"Error fetching VIX data: {e}")
            # Return cached data if available and timestamp is valid (within 60 minutes)
            if cached_data and isinstance(cached_data, dict) and "vix" in cached_data:
                cached_ts = cached_data.get("timestamp")
                if cached_ts:
                    try:
                        cached_time = datetime.fromisoformat(cached_ts.replace("Z", "+00:00"))
                        age_seconds = (datetime.now(timezone.utc) - cached_time).total_seconds()
                        if age_seconds < 3600:
                            logger.info(f"Using cached VIX data on error (age: {age_seconds:.0f}s)")
                            return cached_data
                    except (ValueError, TypeError):
                        pass
            # Return default VIX data to allow application to continue
            logger.warning("Returning default VIX data due to fetch failure")
            return {
                "vix": 20.0,
                "vix_change": 0.0,
                "fear_greed_score": 50.0,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "data_points": 0
            }

    async def get_yield_curve_data(self) -> Dict[str, Any]:
        """Get yield curve data (10Y-2Y spread) via FRED."""
        cache_key = "yield_curve_data"
        cached_data = await self.cache.get(cache_key)
        # Validate that cached data is in expected format and timestamp is within 60 minutes
        if cached_data and isinstance(cached_data, dict) and "ten_year_rate" in cached_data:
            cached_ts = cached_data.get("timestamp")
            if cached_ts:
                try:
                    cached_time = datetime.fromisoformat(cached_ts.replace("Z", "+00:00"))
                    age_seconds = (datetime.now(timezone.utc) - cached_time).total_seconds()
                    if age_seconds < 3600:  # Less than 60 minutes old
                        logger.debug(f"Returning cached yield curve data (age: {age_seconds:.0f}s)")
                        return cached_data
                    else:
                        logger.info(f"Yield curve cache expired (age: {age_seconds:.0f}s > 3600s), fetching fresh data")
                except (ValueError, TypeError) as e:
                    logger.warning(f"Failed to parse cached yield curve timestamp: {e}")

        try:
            # Using FRED API for 10Y and 2Y Treasury rates
            # Note: In production, you'd want to use the fredapi package properly
            # For now, we'll simulate with yfinance for treasury ETFs as proxy
            # Alternatively, we can use the fredapi package if installed

            # Using yfinance for Treasury ETFs as proxy (not ideal but functional)
            # TNX = 10Y Treasury yield, ^IRX = 13-week Treasury bill

            # Get 10-year treasury yield
            ten_year_url = "https://query1.finance.yahoo.com/v8/finance/chart/%5ETNX"
            ten_year_params = {"range": "2d", "interval": "1d"}
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }

            session = requests.Session()
            retries = Retry(total=5, backoff_factor=1, status_forcelist=[502, 503, 504])
            session.mount('https://', HTTPAdapter(max_retries=retries))

            logger.info(f"Fetching 10-year treasury data from Yahoo Finance: {ten_year_url}")
            ten_year_response = session.get(ten_year_url, params=ten_year_params, headers=headers)
            logger.info(f"10-year treasury API response status: {ten_year_response.status_code}")

            if ten_year_response.status_code != 200:
                logger.error(f"10-year treasury API returned non-200 status: {ten_year_response.status_code}. Response: {ten_year_response.text[:200]}")
                raise ValueError(f"Yahoo Finance API returned status {ten_year_response.status_code}")

            ten_year_response.raise_for_status()
            ten_year_json = ten_year_response.json()

            logger.info(f"10-year treasury data received: {len(ten_year_json.get('chart', {}).get('result', []))} {len(ten_year_response.text)}")

            if not ten_year_json['chart']['result']:
                raise ValueError("No 10-year treasury data retrieved")

            ten_year_result = ten_year_json['chart']['result'][0]
            ten_year_indicators = ten_year_result['indicators']['quote'][0]
            ten_year_close = ten_year_indicators['close']

            if not ten_year_close or all(x is None for x in ten_year_close):
                raise ValueError("No 10-year treasury price data available")

            # Get the last non-null close price
            ten_year_rate = None
            for price in reversed(ten_year_close):
                if price is not None:
                    ten_year_rate = price
                    break

            if ten_year_rate is None:
                raise ValueError("No valid 10-year treasury rate found")

            # Get 13-week treasury yield (as proxy for 2-year)
            two_year_url = "https://query1.finance.yahoo.com/v8/finance/chart/%5EIRX"
            two_year_params = {"range": "2d", "interval": "1d"}

            two_year_response = session.get(two_year_url, params=two_year_params, headers=headers)
            logger.info(f"Fetching 13-week treasury data from Yahoo Finance: {two_year_url}")
            logger.info(f"13-week treasury API response status: {two_year_response.status_code}")

            if two_year_response.status_code != 200:
                logger.error(f"13-week treasury API returned non-200 status: {two_year_response.status_code}. Response: {len(two_year_response.text)}")
                raise ValueError(f"Yahoo Finance API returned status {two_year_response.status_code}")

            two_year_response.raise_for_status()
            two_year_json = two_year_response.json()

            logger.info(f"13-week treasury data received: {len(two_year_json.get('chart', {}).get('result', []))} {len(two_year_response.text)}")

            if not two_year_json['chart']['result']:
                raise ValueError("No 13-week treasury data retrieved")

            two_year_result = two_year_json['chart']['result'][0]
            two_year_indicators = two_year_result['indicators']['quote'][0]
            two_year_close = two_year_indicators['close']

            if not two_year_close or all(x is None for x in two_year_close):
                raise ValueError("No 13-week treasury price data available")

            # Get the last non-null close price
            two_year_rate = None
            for price in reversed(two_year_close):
                if price is not None:
                    two_year_rate = price
                    break

            if two_year_rate is None:
                raise ValueError("No valid 13-week treasury rate found")

            spread = ten_year_rate - two_year_rate

            data = {
                "ten_year_rate": round(ten_year_rate, 2),
                "two_year_rate": round(two_year_rate, 2),
                "yield_curve_spread": round(spread, 2),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

            logger.info(f"Yield curve data processed: 10Y={ten_year_rate:.2f}, 2Y={two_year_rate:.2f}, spread={spread:.2f}")

            await self.cache.set(cache_key, data, expire=settings.MARKET_DATA_TTL)
            return data

        except Exception as e:
            logger.error(f"Error fetching yield curve data: {e}")
            # Return cached data if available and timestamp is valid (within 60 minutes)
            if cached_data and isinstance(cached_data, dict) and "ten_year_rate" in cached_data:
                cached_ts = cached_data.get("timestamp")
                if cached_ts:
                    try:
                        cached_time = datetime.fromisoformat(cached_ts.replace("Z", "+00:00"))
                        age_seconds = (datetime.now(timezone.utc) - cached_time).total_seconds()
                        if age_seconds < 3600:
                            logger.info(f"Using cached yield curve data on error (age: {age_seconds:.0f}s)")
                            return cached_data
                    except (ValueError, TypeError):
                        pass
            # Return default yield curve data to allow application to continue
            logger.warning("Returning default yield curve data due to fetch failure")
            return {
                "ten_year_rate": 4.5,
                "two_year_rate": 3.0,
                "yield_curve_spread": 1.5,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

    async def get_market_overview(self) -> Dict[str, Any]:
        """Get combined market overview data."""
        try:
            # Run both data fetches concurrently
            vix_task = asyncio.create_task(self.get_vix_data())
            yield_task = asyncio.create_task(self.get_yield_curve_data())

            vix_data, yield_data = await asyncio.gather(vix_task, yield_task)

            return {
                "vix": vix_data,
                "yield_curve": yield_data,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

        except Exception as e:
            logger.error(f"Error fetching market overview: {e}")
            raise


# --- Module-level functions for new data sources (standalone, cached in Redis) ---

# Yahoo Finance API configuration (same pattern as existing VIX/yield curve code)
_YF_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}
_YF_SESSION = requests.Session()
_YF_RETRIES = Retry(total=5, backoff_factor=1, status_forcelist=[502, 503, 504])
_YF_SESSION.mount('https://', HTTPAdapter(max_retries=_YF_RETRIES))


def _fetch_yf_history(ticker: str, period: str = "1y") -> dict:
    """Fetch Yahoo Finance chart data using direct API call (avoids yfinance JSON issues)."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
    params = {"range": period, "interval": "1d"}

    try:
        logger.info("calling yahoo to get history data: %s", url)
        response = _YF_SESSION.get(url, params=params, headers=_YF_HEADERS)
        if response.status_code != 200:
            return {}
        data_json = response.json()
        if not data_json.get('chart', {}).get('result'):
            return {}
        result = data_json['chart']['result'][0]
        close = result['indicators']['quote'][0]['close']
        # Filter None values
        valid_closes = [c for c in close if c is not None]
        return {"close": valid_closes}
    except Exception:
        return {}


INDEX_TICKERS = {
    "SP500":   "^GSPC",
    "NASDAQ":  "^IXIC",
    "DOW":     "^DJI",
    "RUSSELL": "^RUT",
}

INDEX_CACHE_TTL = 900   # 15 minutes


async def fetch_index_data() -> dict:
    """
    For each of the 4 major indexes returns:
      level          — current closing price
      chg_1d_pct     — 1-day change %
      chg_5d_pct     — 5-day change %
      chg_20d_pct    — 20-day change %
      pct_from_52w_high — distance from 52-week high %
      above_200ma    — bool, price above 200-day MA

    Redis key: "data:indexes"  TTL: 15 min
    Returns empty dict on failure — never raises.
    """
    cache_key = "data:indexes"
    cached = await redis_client.get(cache_key)
    if cached and isinstance(cached, dict):
        return cached

    result = {}
   
    for name, ticker in INDEX_TICKERS.items():
        try:   
            logger.info("calling yahoo to get index: %s", ticker)        
            data = _fetch_yf_history(ticker, period="1y")
            logger.info("index returned for %s: len of close list is %s", ticker, len(data["close"]))
            if not data or "close" not in data or len(data["close"]) < 200:
                continue
            close = data["close"]
            current = float(close[-1])
            # Compute 200-day MA and 52-week high using pandas
            df_close = pd.Series(close)
            # ma_200 = df_close.rolling(200).mean().iloc[-1]
            # high_52w = df_close.rolling(252).max().iloc[-1]
            ma_200   = df_close.rolling(200, min_periods=150).mean().iloc[-1]
            high_52w = df_close.rolling(252, min_periods=200).max().iloc[-1]

            # Skip if NaN (insufficient data)
            if pd.isna(high_52w):
                high_52w = float(df_close.max())   # best available high
            if pd.isna(ma_200):
                ma_200 = float(df_close.mean())    # best available average

            result[name] = {
                "level":              round(current, 2),
                "chg_1d_pct":         round((current / float(close[-2]) - 1) * 100, 2)
                                      if len(close) >= 2 else None,
                "chg_5d_pct":         round((current / float(close[-6]) - 1) * 100, 2)
                                      if len(close) >= 6 else None,
                "chg_20d_pct":        round((current / float(close[-21]) - 1) * 100, 2)
                                      if len(close) >= 21 else None,
                "pct_from_52w_high":  round((current / high_52w - 1) * 100, 2),
                "above_200ma":        current > float(ma_200),
            }
        except Exception as exc:
            logger.warning("index fetch failed for %s: %s", ticker, exc)

    await redis_client.set(cache_key, result, expire=INDEX_CACHE_TTL)
    return result


RATE_TICKERS = {
    "US3M":  "^IRX",
    "US10Y": "^TNX",
    "US30Y": "^TYX",
}

RATE_CACHE_TTL = 1800   # 30 minutes


async def fetch_rate_data() -> dict:
    """
    Returns current yield and 1-month change in basis points for:
      US3M   — 3-month T-bill (short end / risk-free rate proxy)
      US10Y  — 10-year Treasury
      US30Y  — 30-year Treasury
      FED_FUNDS — effective Fed funds rate from FRED if key set

    Yield curve spread (10Y-3M) is already computed by existing
    fetch_vix_and_fear_greed — do not duplicate it here.

    Redis key: "data:rates"  TTL: 30 min
    Returns empty dict on failure — never raises.
    """
    cache_key = "data:rates"
    cached = await redis_client.get(cache_key)
    if cached and isinstance(cached, dict):
        return cached

    result = {}

    for name, ticker in RATE_TICKERS.items():
        try:
            data = _fetch_yf_history(ticker, period="3mo")
            if not data or "close" not in data:
                continue
            close = data["close"]
            current = float(close[-1])
            chg_1m = (float(close[-1]) - float(close[-22])) * 100 \
                     if len(close) >= 22 else None
            result[name] = {
                "yield_pct":    round(current, 3),
                "chg_1m_bps":   round(chg_1m, 1) if chg_1m is not None else None,
            }
        except Exception as exc:
            logger.warning("rate fetch failed for %s: %s", ticker, exc)

    # Fed Funds Rate — monthly FRED series, graceful skip if no key
    try:
        if settings.FRED_API_KEY:
            import fredapi
            logger.info("Calling FRED for rates data")
            fred = fredapi.Fred(api_key=settings.FRED_API_KEY)
            ffr = fred.get_series("FEDFUNDS", limit=2)
            if not ffr.empty:
                result["FED_FUNDS"] = {
                    "yield_pct":  round(float(ffr.iloc[-1]), 3),
                    "chg_1m_bps": round(
                        (float(ffr.iloc[-1]) - float(ffr.iloc[-2])) * 100, 1
                    ) if len(ffr) >= 2 else None,
                }
    except Exception as exc:
        logger.warning("FRED fed funds fetch failed: %s", exc)

    await redis_client.set(cache_key, result, expire=RATE_CACHE_TTL)
    return result


FX_TICKERS = {
    "DXY":    "DX-Y.NYB",
    "EURUSD": "EURUSD=X",
    "USDJPY": "JPY=X",
    "GBPUSD": "GBPUSD=X",
    "USDCNY": "CNY=X",
}

FX_CACHE_TTL = 900   # 15 minutes


async def fetch_fx_data() -> dict:
    """
    Returns current rate and 1-month change % for DXY and major pairs.

    DXY rising  → USD strengthening → headwind for commodities,
                  EM equities, multinationals; risk-off signal.
    DXY falling → USD weakening → tailwind for above; risk-on signal.

    Redis key: "data:fx"  TTL: 15 min
    Returns empty dict on failure — never raises.
    """
    cache_key = "data:fx"
    cached = await redis_client.get(cache_key)
    if cached and isinstance(cached, dict):
        return cached

    result = {}
    for name, ticker in FX_TICKERS.items():
        try:
            data = _fetch_yf_history(ticker, period="3mo")
            if not data or "close" not in data:
                continue
            close = data["close"]
            current = float(close[-1])
            chg_1m = (current / float(close[-22]) - 1) * 100 \
                     if len(close) >= 22 else None
            result[name] = {
                "rate":       round(current, 4),
                "chg_1m_pct": round(chg_1m, 2) if chg_1m is not None else None,
            }
        except Exception as exc:
            logger.warning("fx fetch failed for %s: %s", ticker, exc)

    await redis_client.set(cache_key, result, expire=FX_CACHE_TTL)
    return result


INFLATION_CACHE_TTL = 3600   # 1 hour — daily FRED series


async def fetch_inflation_expectations() -> dict:
    """
    Fetches FORWARD-LOOKING inflation data only.
    Deliberately excludes CPI and PCE — both are monthly and lag
    by 3-6 weeks, making them stale signals for daily analysis.

    Sources (most recent to least recent):
    1. 10Y Breakeven Inflation Rate (T10YIE) — FRED, daily.
       Derived from 10Y nominal minus 10Y TIPS yield.
       Represents what the bond market expects inflation to be
       over the next 10 years. Most timely inflation signal available.
    2. 5Y Breakeven Inflation Rate (T5YIE) — FRED, daily.
       Shorter-horizon complement to the 10Y.
    3. TIP ETF momentum — yfinance fallback if no FRED key.
       TIPS price rises when inflation expectations rise.

    Returns empty dict on failure — never raises.
    """
    cache_key = "data:inflation_expectations"
    cached = await redis_client.get(cache_key)
    if cached and isinstance(cached, dict):
        return cached

    result = {
        "breakeven_10y":        None,
        "breakeven_5y":         None,
        "breakeven_10y_chg_1m": None,
        "breakeven_trend":      None,
        "source":               "unavailable",
    }

    # Primary: FRED breakeven rates (daily, forward-looking)
    try:
        if settings.FRED_API_KEY:
            import fredapi
            fred = fredapi.Fred(api_key=settings.FRED_API_KEY)
            logger.info("Calling FRED for inflation data")
            bei_10 = fred.get_series("T10YIE", limit=30)
            bei_5 = fred.get_series("T5YIE", limit=30)

            if not bei_10.empty:
                current_10y = float(bei_10.iloc[-1])
                result["breakeven_10y"] = round(current_10y, 3)
                if len(bei_10) >= 22:
                    chg = (current_10y - float(bei_10.iloc[-22])) * 100
                    result["breakeven_10y_chg_1m"] = round(chg, 1)
                    result["breakeven_trend"] = (
                        "rising"  if chg >  10 else
                        "falling" if chg < -10 else
                        "stable"
                    )

            if not bei_5.empty:
                result["breakeven_5y"] = round(float(bei_5.iloc[-1]), 3)

            result["source"] = "fred"
            await redis_client.set(cache_key, result, expire=INFLATION_CACHE_TTL)
            return result

    except Exception as exc:
        logger.warning("FRED breakeven fetch failed: %s", exc)

    # Fallback: TIP ETF 1-month momentum as inflation expectation proxy
    try:
        tip = _fetch_yf_history("TIP", period="3mo")
        if tip and "close" in tip and len(tip["close"]) >= 22:
            close = tip["close"]
            chg_pct = (float(close[-1]) / float(close[-22]) - 1) * 100
            result["breakeven_trend"] = (
                "rising"  if chg_pct >  1.0 else
                "falling" if chg_pct < -1.0 else
                "stable"
            )
            result["source"] = "tip_proxy"
    except Exception as exc:
        logger.warning("TIP ETF fallback failed: %s", exc)

    await redis_client.set(cache_key, result, expire=INFLATION_CACHE_TTL)
    return result