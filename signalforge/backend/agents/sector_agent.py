from typing import Dict, Any, Optional
from backend.data.sector_data import SectorData
from backend.data.finviz_data import (
    fetch_finviz_fundamentals,
    normalize_sector_to_spdr,
)
from backend.agents.llm_client import llm_client
from backend.cache.redis_client import redis_client
import logging
import json
import re

logger = logging.getLogger(__name__)


class SectorAgent:
    def __init__(self):
        self.sector_data = SectorData()

    def _strip_markdown_fence(self, text: str) -> str:
        if not text:
            return text
        text = text.strip()
        
        match = re.match(r"^```(?:json)?\s*\n?(.*?)\n?```$", text, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()

        return text

    async def analyze(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze sector rotation and return insights."""
        try:
            logger.info("Starting sector analysis")

            ticker = state.get("ticker", "")

            # 1. Determine the ticker's sector via FinViz (independent call —
            #    no dependency on stock_agent's state)
            fv = await fetch_finviz_fundamentals(ticker)
            finviz_sector = fv.sector if fv else None
            spdr_sector = normalize_sector_to_spdr(finviz_sector)

            if spdr_sector is None:
                logger.warning(
                    "sector_agent: could not determine sector for %s "
                    "(FinViz returned: %r) — falling back to overall "
                    "market rotation only",
                    ticker, finviz_sector,
                )

            # 2. Fetch the ticker's specific sector ETF data (if sector known)
            ticker_sector_etf_data = None
            sector_etf_symbol = None
            if spdr_sector:
                logger.info(f"Fetching data for target sector: {spdr_sector}")
                ticker_sector_etf_data = await self.sector_data.get_sector_etf_data_by_sector(
                    spdr_sector
                )
                sector_etf_symbol = self.sector_data.etf_by_sector.get(spdr_sector)

            # 3. Fetch overall sector rotation context (all 11 sectors ranked)
            overall_rotation = await self.sector_data.get_sector_performance()

            # 4. Determine this sector's rank within the rotation
            ranking = overall_rotation.get("rotation_signals", {}).get("ranking", [])
            sector_rank = None
            if sector_etf_symbol and sector_etf_symbol in ranking:
                sector_rank = ranking.index(sector_etf_symbol) + 1
            sector_etf_data = ticker_sector_etf_data

            # Build sector_performance to preserve the existing variable name
            # used throughout the rest of this method. When we have sector-
            # specific data, use that; otherwise fall back to overall rotation.
            if sector_etf_data and "name" in sector_etf_data:
                sector_performance = sector_etf_data
            else:
                sector_performance = overall_rotation

            # Build LLM input — always use the ticker's specific sector ETF
            # data for momentum/RS/score, and the overall rotation for rank.
            sector_momentum_1m = 0.0
            if sector_etf_data and isinstance(sector_etf_data, dict):
                sector_momentum_1m = sector_etf_data.get("1m_return", 0.0)
            sector_rs_vs_spy = sector_momentum_1m  # Simplified — using momentum as RS proxy

            llm_input = {
                "prompt_version": "sector_v1",
                "ticker": ticker,
                "ticker_sector": spdr_sector or "Unknown",
                "sector_etf": sector_etf_symbol or "N/A",
                "sector_momentum_1m": round(sector_momentum_1m, 4),
                "sector_rs_vs_spy": round(sector_rs_vs_spy, 4),
                "sector_rank": sector_rank if sector_rank is not None else 6,  # default to mid-rank
                "sector_score": round(sector_momentum_1m / 100, 4),  # Normalize to -1..1 range
            }

            # Try LLM cache first
            llm_response = await redis_client.get_llm_narrative("sector", llm_input)

            if llm_response is None:
                # Cache miss — call the LLM
                prompt = f"""
                You are a sector rotation analyst. Respond with raw JSON only — no markdown code fences, 
                no ```json wrapper, no explanatory text before or after.
                
                Analyze the following sector performance data and provide insights on sector rotation:

                Sector Performance Summary:
                """

                # Show the ticker's specific sector ETF data (always available now)
                target_sector = spdr_sector or "Unknown"
                if sector_etf_data and isinstance(sector_etf_data, dict):
                    prompt += f"\nTarget Sector ({target_sector}): {sector_etf_data.get('name', target_sector)}"
                    if "1m_return" in sector_etf_data:
                        prompt += f" - 1-month return: {sector_etf_data.get('1m_return', 0.0):+.2f}%"
                    if sector_rank:
                        prompt += f" - sector rank: {sector_rank}/11"
                else:
                    prompt += f"\nTarget Sector: {target_sector} (sector ETF data unavailable)"

                # Add overall sector rotation context for relative positioning
                rotation_signals = overall_rotation.get("rotation_signals", {})
                ranking = rotation_signals.get("ranking", [])
                if ranking:
                    top_3 = ranking[:3] if len(ranking) >= 3 else ranking
                    bottom_3 = ranking[-3:] if len(ranking) >= 3 else []
                    prompt += f"\nTop Performing Sectors: {', '.join(top_3)}"
                    prompt += f"\nBottom Performing Sectors: {', '.join(bottom_3)}"

                    prompt += "\n\nDetailed Sector Data (1-month returns):\n"
                    for symbol, data in overall_rotation.items():
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
                logger.info("Calling LLM for sector analysis ...")
                llm_response = await llm_client.generate_structured_completion(prompt)

                # Handle empty string gracefully - don't cache, use fallback
                if not llm_response:
                    logger.warning(
                        "sector_agent: LLM returned empty response for %s sector",
                        llm_input.get('ticker_sector', 'all')
                    )
                    llm_response = json.dumps({
                        "rotation_momentum": "monitoring",
                        "economic_implications": "insufficient data",
                        "momentum_assessment": "caution",
                        "outlook": f"{llm_input.get('ticker_sector', 'Tech')} sector ranks {llm_input.get('sector_rank', 1)}/11 with score {llm_input.get('sector_score', 0):.3f}"
                    })
                else:
                    # Store in cache
                    await redis_client.set_llm_narrative("sector", llm_input, llm_response)
                    logger.debug("sector_agent: LLM called and narrative cached")
            else:
                logger.debug("sector_agent: LLM narrative served from cache")

            # Parse LLM response
            try:
                cleaned_response = self._strip_markdown_fence(llm_response)
                logger.info("LLM response for sector analysis: %s", cleaned_response)
                analysis = json.loads(cleaned_response)
            except json.JSONDecodeError as ex:
                logger.error("error LLM response for sector analysis: %s", ex)
                # Fallback analysis
                analysis = {
                    "rotation_momentum": "mixed",
                    "economic_implications": "monitor sector leadership changes",
                    "momentum_assessment": "moderate",
                    "outlook": "sector rotation patterns warrant continued observation"
                }

            # Build LLM narrative for the reasoning field
            outlook = analysis.get('outlook', '')
            sector_score = analysis.get("sector_score", llm_input.get("sector_score", 0.0))
            ticker_sector = llm_input.get("ticker_sector", "Unknown")
            sector_rank = llm_input.get("sector_rank", 6)
            narrative = f"[sector] {outlook}" if outlook else f"[sector] {ticker_sector} sector ranks {sector_rank}/11 with a score of {sector_score:+.3f}."
            # Get sector_score from llm_input (already computed)
            sector_score = llm_input.get("sector_score", 0.0)
            result = {
                "sector_data": sector_performance,
                "analysis": {
                    **analysis,
                    "sector_score": sector_score,
                    "ticker_sector": ticker_sector,
                    "sector_etf": llm_input.get("sector_etf", "N/A"),
                    "sector_rank": sector_rank,
                },
                "timestamp": sector_performance.get("timestamp", None),
                "reasoning": [narrative]
            }

            logger.info("Sector analysis completed")
            return result

        except Exception as e:
            logger.error(f"Error in sector analysis: {e}")
            raise