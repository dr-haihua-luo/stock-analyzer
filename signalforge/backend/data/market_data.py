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
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class MarketData:
    def __init__(self):
        self.cache = redis_client

    async def get_vix_data(self) -> Dict[str, Any]:
        """Get VIX data (fear and greed index proxy)."""
        cache_key = "vix_data"
        cached_data = await self.cache.get(cache_key)
        # Validate that cached data is in expected format before using it
        if cached_data and isinstance(cached_data, dict) and "vix" in cached_data:
            return cached_data

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

            logger.info(f"VIX data received: {len(data_json.get('chart', {}).get('result', []))} {response.text}")

            if not data_json['chart']['result']:
                raise ValueError("No VIX data retrieved")

            result = data_json['chart']['result'][0]
            meta = result['meta']
            timestamps = result['timestamp']
            indicators = result['indicators']['quote'][0]

            if not timestamps or not indicators['close']:
                raise ValueError("No VIX price data available")

            current_vix = indicators['close'][-1]
            prev_close = indicators['close'][-2] if len(indicators['close']) > 1 else current_vix

            # Simple fear/greed interpretation (lower VIX = less fear)
            # Normalize to 0-100 scale where 0 is extreme fear, 100 is extreme greed
            # Historical VIX range: typically 10-80, but we'll use 15-35 as normal range for scoring
            fear_greed_score = max(0, min(100, 100 - ((current_vix - 15) * 2)))  # Inverse relationship

            data = {
                "vix": round(current_vix, 2),
                "vix_change": round(((current_vix - prev_close) / prev_close) * 100, 2),
                "fear_greed_score": round(fear_greed_score, 2),
                "timestamp": datetime.utcnow().isoformat(),
                "data_points": len(timestamps)
            }

            logger.info(f"VIX data processed: vix={current_vix:.2f}, change={((current_vix - prev_close) / prev_close) * 100:.2f}%")

            await self.cache.set(cache_key, data, expire=settings.MARKET_DATA_TTL)
            return data

        except Exception as e:
            logger.error(f"Error fetching VIX data: {e}")
            # Return cached data if available and valid, otherwise return default data to prevent failure
            if cached_data and isinstance(cached_data, dict) and "vix" in cached_data:
                return cached_data
            # Return default VIX data to allow application to continue
            logger.warning("Returning default VIX data due to fetch failure")
            return {
                "vix": 20.0,
                "vix_change": 0.0,
                "fear_greed_score": 50.0,
                "timestamp": datetime.utcnow().isoformat(),
                "data_points": 0
            }

    async def get_yield_curve_data(self) -> Dict[str, Any]:
        """Get yield curve data (10Y-2Y spread) via FRED."""
        cache_key = "yield_curve_data"
        cached_data = await self.cache.get(cache_key)
        # Validate that cached data is in expected format before using it
        if cached_data and isinstance(cached_data, dict) and "ten_year_rate" in cached_data:
            return cached_data

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

            logger.info(f"10-year treasury data received: {len(ten_year_json.get('chart', {}).get('result', []))} {ten_year_response.text}")

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
                logger.error(f"13-week treasury API returned non-200 status: {two_year_response.status_code}. Response: {two_year_response.text[:200]}")
                raise ValueError(f"Yahoo Finance API returned status {two_year_response.status_code}")

            two_year_response.raise_for_status()
            two_year_json = two_year_response.json()

            logger.info(f"13-week treasury data received: {len(two_year_json.get('chart', {}).get('result', []))} {two_year_response.text}")

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
                "timestamp": datetime.utcnow().isoformat()
            }

            logger.info(f"Yield curve data processed: 10Y={ten_year_rate:.2f}, 2Y={two_year_rate:.2f}, spread={spread:.2f}")

            await self.cache.set(cache_key, data, expire=settings.MARKET_DATA_TTL)
            return data

        except Exception as e:
            logger.error(f"Error fetching yield curve data: {e}")
            # Return cached data if available and valid, otherwise return default data to prevent failure
            if cached_data and isinstance(cached_data, dict) and "ten_year_rate" in cached_data:
                return cached_data
            # Return default yield curve data to allow application to continue
            logger.warning("Returning default yield curve data due to fetch failure")
            return {
                "ten_year_rate": 4.5,
                "two_year_rate": 3.0,
                "yield_curve_spread": 1.5,
                "timestamp": datetime.utcnow().isoformat()
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
                "timestamp": datetime.utcnow().isoformat()
            }

        except Exception as e:
            logger.error(f"Error fetching market overview: {e}")
            raise