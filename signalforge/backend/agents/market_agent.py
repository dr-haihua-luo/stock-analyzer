from typing import Dict, Any
from backend.data.market_data import MarketData
from backend.agents.llm_client import llm_client
from backend.config import settings
import logging
import json

logger = logging.getLogger(__name__)


class MarketAgent:
    def __init__(self):
        self.market_data = MarketData()

    async def analyze(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze market conditions and return insights."""
        try:
            logger.info("Starting market analysis")

            # Get market data
            market_data = await self.market_data.get_market_overview()

            # Use LLM to interpret market conditions
            prompt = f"""
            Analyze the following market data and provide insights on market conditions:

            VIX Data:
            - VIX Level: {market_data['vix']['vix']}
            - VIX Change: {market_data['vix']['vix_change']}%
            - Fear/Greed Score: {market_data['vix']['fear_greed_score']}/100

            Yield Curve Data:
            - 10Y Rate: {market_data['yield_curve']['ten_year_rate']}%
            - 2Y Rate: {market_data['yield_curve']['two_year_rate']}%
            - Spread (10Y-2Y): {market_data['yield_curve']['yield_curve_spread']}%

            Provide a concise analysis covering:
            1. Overall market sentiment (fearful, neutral, greedy)
            2. Interest rate environment implications
            3. Market volatility expectations
            4. One-sentence market outlook

            Format your response as JSON with keys: sentiment, rate_implications, volatility_expectation, outlook
            """

            llm_response = await llm_client.generate_structured_completion(prompt)

            # Parse LLM response (handle potential formatting issues)
            try:
                analysis = json.loads(llm_response)
            except json.JSONDecodeError:
                # Fallback if LLM doesn't return valid JSON
                analysis = {
                    "sentiment": "neutral",
                    "rate_implications": "monitor closely",
                    "volatility_expectation": "moderate",
                    "outlook": "market conditions require careful monitoring"
                }

            result = {
                "market_data": market_data,
                "analysis": analysis,
                "timestamp": market_data["timestamp"]
            }

            logger.info("Market analysis completed")
            return result

        except Exception as e:
            logger.error(f"Error in market analysis: {e}")
            raise