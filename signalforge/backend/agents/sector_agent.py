from typing import Dict, Any, Optional
from backend.data.sector_data import SectorData
from backend.agents.llm_client import llm_client
from backend.cache.redis_client import redis_client
import logging
import json

logger = logging.getLogger(__name__)


class SectorAgent:
    def __init__(self):
        self.sector_data = SectorData()

    async def analyze(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze sector rotation and return insights."""
        try:
            logger.info("Starting sector analysis")

            # Get the stock's sector from fundamentals if available
            stock_data = state.get("stock_data", {})
            target_sector = None
            ticker = state.get("ticker", "")
            if stock_data and isinstance(stock_data, dict):
                fundamentals = stock_data.get("fundamentals", {})
                if fundamentals and isinstance(fundamentals, dict):
                    target_sector = fundamentals.get("sector")

            # Get sector data - if we have a target sector, only get that sector's data
            if target_sector:
                logger.info(f"Fetching data for target sector: {target_sector}")
                sector_performance = await self.sector_data.get_sector_etf_data_by_sector(target_sector)
            else:
                logger.info("Fetching data for all sectors (no target sector specified)")
                sector_performance = await self.sector_data.get_sector_performance()

            # Build LLM input with all values that influence the prompt
            # For specific sector analysis (target_sector case)
            if target_sector and isinstance(sector_performance, dict) and "name" in sector_performance:
                sector_momentum_1m = sector_performance.get("1m_return", 0.0)
                sector_rs_vs_spy = sector_momentum_1m  # Simplified - using momentum as RS proxy

                llm_input = {
                    "prompt_version": "sector_v1",
                    "ticker": ticker,
                    "ticker_sector": target_sector,
                    "sector_etf": sector_performance.get("symbol", ""),
                    "sector_momentum_1m": round(sector_momentum_1m, 4),
                    "sector_rs_vs_spy": round(sector_rs_vs_spy, 4),
                    "sector_rank": 0,  # Not applicable for single sector
                    "sector_score": round(sector_momentum_1m / 100, 4),  # Normalize to -1..1 range
                }
            else:
                # For all-sector analysis
                ranking = sector_performance.get("rotation_signals", {}).get("ranking", [])
                top_3 = ranking[:3] if len(ranking) >= 3 else ranking
                bottom_3 = ranking[-3:] if len(ranking) >= 3 else []

                # Compute sector score from top sector performance
                top_sector_data = {}
                if top_3:
                    top_sector_symbol = top_3[0]
                    top_sector_data = sector_performance.get(top_sector_symbol, {})

                llm_input = {
                    "prompt_version": "sector_v1",
                    "ticker": ticker,
                    "ticker_sector": target_sector or "all",
                    "sector_etf": top_sector_data.get("name", "") if top_sector_data else "",
                    "sector_momentum_1m": round(top_sector_data.get("1m_return", 0.0), 4),
                    "sector_rs_vs_spy": round(top_sector_data.get("1m_return", 0.0), 4),
                    "sector_rank": 1,  # Top sector rank
                    "sector_score": round(top_sector_data.get("1m_return", 0.0) / 100, 4),
                }

            # Try LLM cache first
            llm_response = await redis_client.get_llm_narrative("sector", llm_input)

            if llm_response is None:
                # Cache miss — call the LLM
                prompt = f"""
                Analyze the following sector performance data and provide insights on sector rotation:

                Sector Performance Summary:
                """

                # If we have sector data for a specific sector, show just that
                if target_sector and isinstance(sector_performance, dict) and "name" in sector_performance:
                    prompt += f"\nTarget Sector ({target_sector}): {sector_performance.get('name', target_sector)}"
                    if "1m_return" in sector_performance:
                        prompt += f" - 1-month return: {sector_performance.get('1m_return', 0.0):+.2f}%"
                else:
                    # Add top 3 and bottom 3 sectors for brevity
                    rotation_signals = sector_performance.get("rotation_signals", {})
                    ranking = rotation_signals.get("ranking", [])
                    if ranking:
                        top_3 = ranking[:3] if len(ranking) >= 3 else ranking
                        bottom_3 = ranking[-3:] if len(ranking) >= 3 else []
                        prompt += f"\nTop Performing Sectors: {', '.join(top_3)}"
                        prompt += f"\nBottom Performing Sectors: {', '.join(bottom_3)}"

                    # Add specific sector data for context
                    prompt += "\n\nDetailed Sector Data (1-month returns):\n"
                    for symbol, data in sector_performance.items():
                        if symbol != "rotation_signals" and isinstance(data, dict) and "1m_return" in data:
                            prompt += f"- {data.get('name', symbol)} ({symbol}): {data.get('1m_return', 0.0):+.2f}%\n"

                prompt += """

                Based on this data, provide analysis on:
                1. Current sector rotation momentum (which sectors are leading/lagging)
                2. Economic cycle implications
                3. Sector momentum persistence assessment
                4. One-sentence sector outlook

                Format your response as JSON with keys: rotation_momentum, economic_implications, momentum_assessment, outlook
                """

                llm_response = await llm_client.generate_structured_completion(prompt)

                # Store in cache
                await redis_client.set_llm_narrative("sector", llm_input, llm_response)
                logger.debug("sector_agent: LLM called and narrative cached")
            else:
                logger.debug("sector_agent: LLM narrative served from cache")

            # Parse LLM response
            try:
                analysis = json.loads(llm_response)
            except json.JSONDecodeError:
                # Fallback analysis
                analysis = {
                    "rotation_momentum": "mixed",
                    "economic_implications": "monitor sector leadership changes",
                    "momentum_assessment": "moderate",
                    "outlook": "sector rotation patterns warrant continued observation"
                }

            # Build LLM narrative for the reasoning field
            narrative = f"[sector] {analysis.get('outlook', 'Sector rotation requires continued observation.')}"
            # Get sector_score from llm_input (already computed)
            sector_score = llm_input.get("sector_score", 0.0)
            result = {
                "sector_data": sector_performance,
                "analysis": {
                    **analysis,
                    "sector_score": sector_score,
                },
                "timestamp": sector_performance.get("timestamp", None),
                "reasoning": [narrative]
            }

            logger.info("Sector analysis completed")
            return result

        except Exception as e:
            logger.error(f"Error in sector analysis: {e}")
            raise