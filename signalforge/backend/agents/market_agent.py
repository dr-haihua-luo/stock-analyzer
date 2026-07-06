from typing import Dict, Any, Optional
from backend.data.market_data import MarketData
from backend.agents.llm_client import llm_client
from backend.cache.redis_client import redis_client
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

            # Compute derived values for LLM cache key and scoring
            vix_value = market_data['vix']['vix']
            fear_greed_index = market_data['vix']['fear_greed_score']
            yield_curve_spread = market_data['yield_curve']['yield_curve_spread']

            # Derive VIX regime
            if vix_value < 20:
                vix_regime = "low"
            elif vix_value < 25:
                vix_regime = "normal"
            else:
                vix_regime = "high"

            # Derive fear/greed label
            if fear_greed_index < 25:
                fear_greed_label = "fear"
            elif fear_greed_index < 75:
                fear_greed_label = "neutral"
            else:
                fear_greed_label = "greed"

            # Derive yield curve signal
            if yield_curve_spread > 0:
                yield_curve_signal = "normal"
            else:
                yield_curve_signal = "inverted"

            # Derive macro regime
            if vix_regime == "high" or fear_greed_label == "fear":
                macro_regime = "risk_off"
            elif vix_regime == "low" and fear_greed_label == "greed":
                macro_regime = "risk_on"
            else:
                macro_regime = "neutral"

            # Compute market score: combine VIX and yield curve signals
            # VIX score: lower is better, map to -1 to +1 range
            vix_score = max(-1, min(1, (25 - vix_value) / 25))
            # Yield curve score: positive spread is good
            yield_score = max(-1, min(1, yield_curve_spread / 200))
            market_score = round((vix_score + yield_score) / 2, 4)

            # Build LLM input with all values that influence the prompt
            llm_input = {
                "prompt_version": "market_v1",
                "vix_value": vix_value,
                "vix_regime": vix_regime,
                "fear_greed_index": fear_greed_index,
                "fear_greed_label": fear_greed_label,
                "yield_curve_spread": yield_curve_spread,
                "yield_curve_signal": yield_curve_signal,
                "macro_regime": macro_regime,
                "market_score": market_score,
            }

            # Try LLM cache first
            llm_response = await redis_client.get_llm_narrative("market", llm_input)

            if llm_response is None:
                # Cache miss — call the LLM
                prompt = f"""
                Analyze the following market data and provide insights on market conditions:

                VIX Data:
                - VIX Level: {llm_input['vix_value']}
                - VIX Change: {market_data['vix']['vix_change']}%
                - Fear/Greed Score: {llm_input['fear_greed_index']}/100

                Yield Curve Data:
                - 10Y Rate: {market_data['yield_curve']['ten_year_rate']}%
                - 2Y Rate: {market_data['yield_curve']['two_year_rate']}%
                - Spread (10Y-2Y): {llm_input['yield_curve_spread']}%

                Provide a concise analysis covering:
                1. Overall market sentiment (fearful, neutral, greedy)
                2. Interest rate environment implications
                3. Market volatility expectations
                4. One-sentence market outlook

                Format your response as JSON with keys: sentiment, rate_implications, volatility_expectation, outlook
                """

                llm_response = await llm_client.generate_structured_completion(prompt)

                # Handle empty string gracefully - don't cache, use fallback
                if not llm_response:
                    logger.warning(
                        "market_agent: LLM returned empty response for VIX %.1f, yield spread %.2f",
                        llm_input['vix_value'], llm_input['yield_curve_spread']
                    )
                    llm_response = json.dumps({
                        "sentiment": "neutral",
                        "rate_implications": "monitor closely",
                        "volatility_expectation": "moderate",
                        "outlook": f"Market regime is {macro_regime} with VIX at {vix_value:.1f}"
                    })
                else:
                    # Store in cache
                    await redis_client.set_llm_narrative("market", llm_input, llm_response)
                    logger.debug("market_agent: LLM called and narrative cached")
            else:
                logger.debug("market_agent: LLM narrative served from cache")

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

            # Build LLM narrative for the reasoning field
            outlook = analysis.get('outlook', '')
            narrative = f"[market] {outlook}" if outlook else f"[market] VIX at {vix_value:.1f} ({vix_regime}), regime is {macro_regime}."
            result = {
                "market_data": market_data,
                "analysis": {
                    **analysis,
                    "market_score": market_score,
                },
                "timestamp": market_data["timestamp"],
                "reasoning": [narrative]
            }

            logger.info("Market analysis completed")
            return result

        except Exception as e:
            logger.error(f"Error in market analysis: {e}")
            raise