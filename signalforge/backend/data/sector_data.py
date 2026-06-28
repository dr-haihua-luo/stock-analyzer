import yfinance as yf
import pandas as pd
from typing import Dict, Any, List, Optional
import asyncio
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from backend.config import settings
from backend.cache.redis_client import redis_client
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class SectorData:
    def __init__(self):
        self.cache = redis_client
        # Major sector ETFs
        self.sector_etfs = {
            "XLK": "Technology",
            "XLF": "Financial",
            "XLE": "Energy",
            "XLV": "Healthcare",
            "XLI": "Industrial",
            "XLY": "Consumer Discretionary",
            "XLP": "Consumer Staples",
            "XLB": "Materials",
            "XLU": "Utilities",
            "XLRE": "Real Estate",
            "XLC": "Communication Services"
        }
        # Reverse mapping from sector name to ETF symbol
        self.etf_by_sector = {v: k for k, v in self.sector_etfs.items()}

    async def get_sector_performance(self) -> Dict[str, Any]:
        """Get performance data for all major sectors."""
        cache_key = "sector_performance"
        cached_data = await self.cache.get(cache_key)
        # Validate that cached data has valid timestamp within last 60 minutes
        if cached_data:
            cached_ts = cached_data.get("timestamp")
            if cached_ts:
                try:
                    cached_time = datetime.fromisoformat(cached_ts.replace("Z", "+00:00"))
                    age_seconds = (datetime.now(timezone.utc) - cached_time).total_seconds()
                    if age_seconds < 3600:  # Less than 60 minutes old
                        logger.info(f"Returning cached sector performance data (age: {age_seconds:.0f}s)")
                        return cached_data
                    else:
                        logger.info(f"Sector performance cache expired (age: {age_seconds:.0f}s > 3600s), fetching fresh data")
                except (ValueError, TypeError) as e:
                    logger.warning(f"Failed to parse cached sector timestamp: {e}")

        try:
            sector_data = {}

            # Fetch data for all sector ETFs concurrently
            tasks = []
            for etf_symbol in self.sector_etfs.keys():
                task = asyncio.create_task(self._get_etf_data(etf_symbol))
                tasks.append((etf_symbol, task))

            # Wait for all tasks to complete
            results = await asyncio.gather(*[task for _, task in tasks], return_exceptions=True)

            # Process results
            for i, (etf_symbol, _) in enumerate(tasks):
                result = results[i]
                if isinstance(result, Exception):
                    logger.warning(f"Failed to fetch data for {etf_symbol}: {result}")
                    continue

                if result:
                    sector_data[etf_symbol] = {
                        "name": self.sector_etfs[etf_symbol],
                        **result
                    }

            # Calculate sector rankings based on 1-month performance
            sorted_sectors = sorted(
                [(symbol, data.get("1m_return", 0)) for symbol, data in sector_data.items() if "1m_return" in data],
                key=lambda x: x[1],
                reverse=True
            )

            # Add rotation signals and timestamp for cache validation
            sector_data["rotation_signals"] = {
                "strongest": sorted_sectors[0][0] if sorted_sectors else None,
                "weakest": sorted_sectors[-1][0] if sorted_sectors else None,
                "ranking": [symbol for symbol, _ in sorted_sectors]
            }
            sector_data["timestamp"] = datetime.now(timezone.utc).isoformat()

            await self.cache.set(cache_key, sector_data, expire=settings.SECTOR_DATA_TTL)
            return sector_data

        except Exception as e:
            logger.error(f"Error fetching sector performance: {e}")
            # Return cached data if available and timestamp is valid, otherwise return default data
            if cached_data:
                cached_ts = cached_data.get("timestamp")
                if cached_ts:
                    try:
                        cached_time = datetime.fromisoformat(cached_ts.replace("Z", "+00:00"))
                        age_seconds = (datetime.now(timezone.utc) - cached_time).total_seconds()
                        if age_seconds < 3600:
                            logger.info(f"Using cached sector performance data on error (age: {age_seconds:.0f}s)")
                            return cached_data
                    except (ValueError, TypeError):
                        pass
            # Return default sector data to allow application to continue
            logger.warning("Returning default sector data due to fetch failure")
            return {
                "rotation_signals": {
                    "strongest": None,
                    "weakest": None,
                    "ranking": []
                }
            }

    async def _get_etf_data(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get data for a single sector ETF."""
        try:
            # Use direct Yahoo Finance API call with proper headers to avoid JSON decode errors
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
            params = {
                "range": "3mo",
                "interval": "1d"
            }
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }

            session = requests.Session()
            retries = Retry(total=5, backoff_factor=1, status_forcelist=[502, 503, 504])
            session.mount('https://', HTTPAdapter(max_retries=retries))

            logger.info(f"Fetching ETF data for {symbol} from Yahoo Finance: {url}")
            response = session.get(url, params=params, headers=headers)
            logger.info(f"ETF {symbol} API response status: {response.status_code}")

            if response.status_code != 200:
                logger.error(f"ETF {symbol} API returned non-200 status: {response.status_code}. Response: {response.text[:200]}")
                # Still try to process if we got some data, but log the error
                # Don't raise exception here as we might still get partial data

            response.raise_for_status()
            data_json = response.json()

            logger.info(f"ETF {symbol} data received length: {len(data_json.get('chart', {}).get('result', []))} {len(response.text)}")

            if not data_json['chart']['result']:
                logger.warning(f"No data found for {symbol}")
                # Return default data to allow application to continue
                return {
                    "symbol": symbol,
                    "name": self.sector_etfs.get(symbol, symbol),
                    "current_price": 0.0,
                    "volume": 0,
                    "market_cap": 0,
                    "1d_return": 0.0,
                    "1w_return": 0.0,
                    "1m_return": 0.0,
                    "3m_return": 0.0,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }

            result = data_json['chart']['result'][0]
            meta = result['meta']
            timestamps = result['timestamp']
            indicators = result['indicators']['quote'][0]

            if not timestamps or not indicators['close']:
                logger.warning(f"No price data available for {symbol}")
                # Return default data to allow application to continue
                return {
                    "symbol": symbol,
                    "name": self.sector_etfs.get(symbol, symbol),
                    "current_price": 0.0,
                    "volume": 0,
                    "market_cap": 0,
                    "1d_return": 0.0,
                    "1w_return": 0.0,
                    "1m_return": 0.0,
                    "3m_return": 0.0,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }

            # Get close prices (filter out None values)
            close_prices = [price for price in indicators['close'] if price is not None]
            if not close_prices:
                logger.warning(f"No valid close prices for {symbol}")
                # Return default data to allow application to continue
                return {
                    "symbol": symbol,
                    "name": self.sector_etfs.get(symbol, symbol),
                    "current_price": 0.0,
                    "volume": 0,
                    "market_cap": 0,
                    "1d_return": 0.0,
                    "1w_return": 0.0,
                    "1m_return": 0.0,
                    "3m_return": 0.0,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }

            current_price = close_prices[-1]

            # Calculate returns for different timeframes
            returns = {}
            periods = {
                "1d": 1,
                "1w": 5,
                "1m": 21,  # Approximate trading days
                "3m": 63
            }

            for period, days in periods.items():
                if len(close_prices) > days:
                    past_price = close_prices[-days-1]
                    returns[f"{period}_return"] = ((current_price - past_price) / past_price) * 100
                else:
                    returns[f"{period}_return"] = 0.0

            # Additional metrics
            data = {
                "symbol": symbol,
                "current_price": round(current_price, 2),
                "volume": int(indicators['volume'][-1]) if indicators['volume'] and indicators['volume'][-1] is not None else 0,
                "market_cap": meta.get("marketCap", 0),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                **returns
            }

            logger.info(f"ETF {symbol} data processed: price={current_price:.2f}, volume={data['volume']}")

            return data

        except Exception as e:
            logger.error(f"Error fetching ETF data for {symbol}: {e}")
            # Return default ETF data to allow application to continue
            logger.warning(f"Returning default ETF data for {symbol} due to fetch failure")
            return {
                "symbol": symbol,
                "name": self.sector_etfs.get(symbol, symbol),
                "current_price": 0.0,
                "sma_20": 0.0,
                "sma_50": 0.0,
                "rsi": 50.0,
                "pe_ratio": None,
                "dividend_yield": None,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

    async def get_sector_etf_data(self, symbol: str) -> Dict[str, Any]:
        """Get detailed data for a specific sector ETF."""
        cache_key = f"sector_etf_{symbol}"
        cached_data = await self.cache.get(cache_key)
        # Validate that cached data has valid timestamp within last 60 minutes
        if cached_data:
            cached_ts = cached_data.get("timestamp")
            if cached_ts:
                try:
                    cached_time = datetime.fromisoformat(cached_ts.replace("Z", "+00:00"))
                    age_seconds = (datetime.now(timezone.utc) - cached_time).total_seconds()
                    if age_seconds < 3600:  # Less than 60 minutes old
                        logger.debug(f"Returning cached ETF {symbol} data (age: {age_seconds:.0f}s)")
                        return cached_data
                    else:
                        logger.info(f"ETF {symbol} cache expired (age: {age_seconds:.0f}s > 3600s), fetching fresh data")
                except (ValueError, TypeError) as e:
                    logger.warning(f"Failed to parse cached ETF {symbol} timestamp: {e}")

        try:
            # Use direct Yahoo Finance API call with proper headers to avoid JSON decode errors
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
            params = {
                "range": "1y",
                "interval": "1d"
            }
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }

            session = requests.Session()
            retries = Retry(total=5, backoff_factor=1, status_forcelist=[502, 503, 504])
            session.mount('https://', HTTPAdapter(max_retries=retries))

            response = session.get(url, params=params, headers=headers)
            response.raise_for_status()
            data_json = response.json()
            logger.info(f"Sector ETF {symbol} data received: {len(data_json.get('chart', {}).get('result', []))} {response.text}")

            if not data_json['chart']['result']:
                raise ValueError(f"No data found for {symbol}")

            result = data_json['chart']['result'][0]
            meta = result['meta']
            timestamps = result['timestamp']
            indicators = result['indicators']['quote'][0]

            if not timestamps or not indicators['close']:
                raise ValueError(f"No price data available for {symbol}")

            # Get close prices (filter out None values)
            close_prices = [price for price in indicators['close'] if price is not None]
            if not close_prices:
                raise ValueError(f"No valid close prices for {symbol}")

            current_price = close_prices[-1]

            # Calculate various technical indicators
            # Simple moving averages
            sma_20 = sum(close_prices[-20:]) / 20 if len(close_prices) >= 20 else current_price
            sma_50 = sum(close_prices[-50:]) / 50 if len(close_prices) >= 50 else current_price

            # Relative Strength Index (RSI) - simplified
            if len(close_prices) >= 14:
                delta = [close_prices[i] - close_prices[i-1] for i in range(1, len(close_prices))]
                gain = [max(d, 0) for d in delta]
                loss = [max(-d, 0) for d in delta]

                avg_gain = sum(gain[-14:]) / 14
                avg_loss = sum(loss[-14:]) / 14

                if avg_loss == 0:
                    rsi = 100
                else:
                    rs = avg_gain / avg_loss
                    rsi = 100 - (100 / (1 + rs))
            else:
                rsi = 50

            data = {
                "symbol": symbol,
                "name": self.sector_etfs.get(symbol, symbol),
                "current_price": round(current_price, 2),
                "sma_20": round(sma_20, 2),
                "sma_50": round(sma_50, 2),
                "rsi": round(rsi, 2),
                "pe_ratio": meta.get("trailingPE"),
                "dividend_yield": meta.get("dividendYield"),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

            await self.cache.set(cache_key, data, expire=settings.SECTOR_DATA_TTL)
            return data

        except Exception as e:
            logger.error(f"Error fetching detailed ETF data for {symbol}: {e}")
            # Return cached data if available and timestamp is valid (within 60 minutes)
            if cached_data:
                cached_ts = cached_data.get("timestamp")
                if cached_ts:
                    try:
                        cached_time = datetime.fromisoformat(cached_ts.replace("Z", "+00:00"))
                        age_seconds = (datetime.now(timezone.utc) - cached_time).total_seconds()
                        if age_seconds < 3600:
                            logger.info(f"Using cached ETF {symbol} data on error (age: {age_seconds:.0f}s)")
                            return cached_data
                    except (ValueError, TypeError):
                        pass
            # Return default ETF data to allow application to continue
            logger.warning(f"Returning default ETF data for {symbol} due to fetch failure")
            return {
                "symbol": symbol,
                "name": self.sector_etfs.get(symbol, symbol),
                "current_price": 0.0,
                "sma_20": 0.0,
                "sma_50": 0.0,
                "rsi": 50.0,
                "pe_ratio": None,
                "dividend_yield": None,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

    async def get_sector_etf_data_by_sector(self, sector_name: str) -> Dict[str, Any]:
        """Get ETF data for a specific sector name."""
        # Find the ETF symbol for the given sector name
        etf_symbol = self.etf_by_sector.get(sector_name)
        if not etf_symbol:
            logger.warning(f"No ETF found for sector: {sector_name}")
            # Return default data
            return {
                "symbol": "",
                "name": sector_name,
                "current_price": 0.0,
                "sma_20": 0.0,
                "sma_50": 0.0,
                "rsi": 50.0,
                "pe_ratio": None,
                "dividend_yield": None,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

        # Get data for the ETF symbol
        logger.info(f"Fetching ETF data for sector {sector_name} (symbol: {etf_symbol})")
        result = await self.get_sector_etf_data(etf_symbol)
        logger.info(f"Completed fetching ETF data for sector {sector_name}")
        return result