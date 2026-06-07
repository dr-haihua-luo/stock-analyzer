import os
import sys
import unittest
from unittest.mock import patch, MagicMock
import pandas as pd
from datetime import datetime, timedelta, timezone

# Add the backend directory to the path so we can import from it
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'signalforge/backend'))

from backend.data.stock_data import (
    fetch_ohlcv,
    fetch_latest_price,
    _stock_client,
    _news_client
)


class TestStockDataConnectivity(unittest.TestCase):
    """Test cases for verifying Alpaca API connectivity in stock_data.py"""

    def setUp(self):
        """Set up test fixtures before each test method."""
        # Use a well-known ticker for testing
        self.test_ticker = "AAPL"

    def test_stock_client_initialization(self):
        """Test that _stock_client is properly initialized"""
        self.assertIsNotNone(_stock_client)
        # Check that it's a StockHistoricalDataClient instance
        from alpaca.data.historical import StockHistoricalDataClient
        self.assertIsInstance(_stock_client, StockHistoricalDataClient)

    def test_news_client_initialization(self):
        """Test that _news_client is properly initialized"""
        self.assertIsNotNone(_news_client)
        # Check that it's a NewsClient instance
        from alpaca.data.historical.news import NewsClient
        self.assertIsInstance(_news_client, NewsClient)

    @patch('data.stock_data._stock_client')
    def test_fetch_ohlcv_with_mock(self, mock_stock_client):
        """Test fetch_ohlcv function with mocked client"""
        # Create a mock response
        mock_bars = MagicMock()
        mock_df = pd.DataFrame({
            'open': [150.0, 151.0],
            'high': [152.0, 153.0],
            'low': [149.0, 150.0],
            'close': [151.0, 152.0],
            'volume': [1000000, 1100000]
        }, index=pd.date_range('2026-05-01', periods=2, tz='UTC'))
        mock_bars.df = mock_df
        mock_stock_client.get_stock_bars.return_value = mock_bars

        # Call the function
        result = fetch_ohlcv(self.test_ticker)

        # Verify the mock was called correctly
        mock_stock_client.get_stock_bars.assert_called_once()
        # Verify we got a DataFrame back
        self.assertIsInstance(result, pd.DataFrame)
        self.assertFalse(result.empty)
        self.assertListEqual(list(result.columns), ['open', 'high', 'low', 'close', 'volume'])

    @patch('data.stock_data._stock_client')
    def test_fetch_latest_price_with_mock(self, mock_stock_client):
        """Test fetch_latest_price function with mocked client"""
        # Create a mock response
        mock_quote = MagicMock()
        mock_quote.ask_price = 152.50
        mock_quote.bid_price = 152.49

        mock_quotes = {self.test_ticker: mock_quote}
        mock_stock_client.get_stock_latest_quote.return_value = mock_quotes

        # Call the function
        result = fetch_latest_price(self.test_ticker)

        # Verify the mock was called correctly
        mock_stock_client.get_stock_latest_quote.assert_called_once()
        # Verify we got a float back
        self.assertIsInstance(result, float)
        self.assertEqual(result, 152.50)  # Should return ask_price

    @patch('data.stock_data._news_client')
    def test_fetch_news_sentiment_with_mock(self, mock_news_client):
        """Test fetch_news_sentiment function with mocked client"""
        # Create a mock response
        mock_article = MagicMock()
        mock_article.headline = "Apple beats earnings expectations"

        mock_news = MagicMock()
        mock_news.news = [mock_article]
        mock_news_client.get_news.return_value = mock_news

        # Call the function
        from data.stock_data import fetch_news_sentiment
        result = fetch_news_sentiment(self.test_ticker)

        # Verify the mock was called correctly
        mock_news_client.get_news.assert_called_once()
        # Verify we got a float back (sentiment score)
        self.assertIsInstance(result, float)
        # For a positive headline, we expect a positive score
        self.assertGreater(result, 0)

    def test_actual_api_connectivity(self):
        """Test actual connectivity to Alpaca Paper API (skipped if no credentials)"""
        # Skip if no API credentials are available
        if not os.getenv('APCA_API_KEY_ID') or not os.getenv('APCA_API_SECRET_KEY'):
            self.skipTest("Alpaca API credentials not found in environment variables")

        # Test that we can make a simple API call without throwing an exception
        try:
            # Test with a small date range to minimize data transfer
            end = datetime.now(timezone.utc)
            start = end - timedelta(days=2)  # Just 2 days of data

            from alpaca.data.requests import StockBarsRequest
            from alpaca.data.timeframe import TimeFrame

            request = StockBarsRequest(
                symbol_or_symbols=self.test_ticker,
                timeframe=TimeFrame.Day,
                start=start,
                end=end,
                limit=10  # Limit to reduce data transfer
            )

            # This should not raise an exception if credentials are valid
            bars = _stock_client.get_stock_bars(request)
            self.assertIsNotNone(bars)

        except Exception as e:
            self.fail(f"Failed to connect to Alpaca Paper API: {e}")


if __name__ == '__main__':
    unittest.main()