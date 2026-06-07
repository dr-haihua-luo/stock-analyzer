from typing import Dict, Any
from backend.data.sector_data import SectorData
from backend.agents.llm_client import llm_client
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

            # Use LLM to interpret sector rotation
            prompt = f"""
            Analyze the following sector performance data and provide insights on sector rotation:

            Sector Performance Summary:
            """

            # If we have sector data for a specific sector, show just that
            if target_sector and isinstance(sector_performance, dict) and "name" in sector_performance:
                prompt += f"\nTarget Sector ({target_sector}): {sector_performance['name']}"
                if "1m_return" in sector_performance:
                    prompt += f" - 1-month return: {sector_performance['1m_return']:+.2f}%"
            else:
                # Add top 3 and bottom 3 sectors for brevity
                if "rotation_signals" in sector_performance:
                    ranking = sector_performance["rotation_signals"]["ranking"]
                    if ranking:
                        top_3 = ranking[:3] if len(ranking) >= 3 else ranking
                        bottom_3 = ranking[-3:] if len(ranking) >= 3 else []
                        prompt += f"\nTop Performing Sectors: {', '.join(top_3)}"
                        prompt += f"\nBottom Performing Sectors: {', '.join(bottom_3)}"

                # Add specific sector data for context
                prompt += "\n\nDetailed Sector Data (1-month returns):\n"
                for symbol, data in sector_performance.items():
                    if symbol != "rotation_signals" and isinstance(data, dict) and "1m_return" in data:
                        prompt += f"- {data['name']} ({symbol}): {data['1m_return']:+.2f}%\n"

            prompt += """

            Based on this data, provide analysis on:
            1. Current sector rotation momentum (which sectors are leading/lagging)
            2. Economic cycle implications
            3. Sector momentum persistence assessment
            4. One-sentence sector outlook

            Format your response as JSON with keys: rotation_momentum, economic_implications, momentum_assessment, outlook
            """

            llm_response = await llm_client.generate_structured_completion(prompt)

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

            result = {
                "sector_data": sector_performance,
                "analysis": analysis,
                "timestamp": sector_performance.get("timestamp", None)
            }

            logger.info("Sector analysis completed")
            return result

        except Exception as e:
            logger.error(f"Error in sector analysis: {e}")
            raise