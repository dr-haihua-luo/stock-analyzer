from typing import Dict, Any, Optional
from backend.data.market_data import (
    MarketData,
    fetch_index_data,
    fetch_rate_data,
    fetch_fx_data,
    fetch_inflation_expectations,
)
from backend.agents.llm_client import llm_client
from backend.agents.state import MarketContext
from backend.cache.redis_client import redis_client
from backend.config import settings
import logging
import json
import asyncio

logger = logging.getLogger(__name__)


class MarketAgent:
    def __init__(self):
        self.market_data = MarketData()

    async def analyze(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze market conditions and return insights."""
        try:
            logger.info("Starting market analysis")

            # Fetch all data sources concurrently (existing + new)
            vix_data, index_data, rate_data, fx_data, inflation_data = await asyncio.gather(
                self.market_data.get_vix_data(),
                fetch_index_data(),
                fetch_rate_data(),
                fetch_fx_data(),
                fetch_inflation_expectations(),
                return_exceptions=True,
            )

            # Convert any exceptions to empty dicts (never raise)
            if isinstance(vix_data, Exception):
                logger.warning("VIX fetch failed: %s", vix_data)
                vix_data = {}
            if isinstance(index_data, Exception):
                logger.warning("Index fetch failed: %s", index_data)
                index_data = {}
            if isinstance(rate_data, Exception):
                logger.warning("Rate fetch failed: %s", rate_data)
                rate_data = {}
            if isinstance(fx_data, Exception):
                logger.warning("FX fetch failed: %s", fx_data)
                fx_data = {}
            if isinstance(inflation_data, Exception):
                logger.warning("Inflation fetch failed: %s", inflation_data)
                inflation_data = {}

            # Extract existing values
            vix_value = vix_data.get("vix", 20.0) if isinstance(vix_data, dict) else 20.0
            fear_greed_index = vix_data.get("fear_greed_score", 50) if isinstance(vix_data, dict) else 50

            # Get yield curve spread from the MarketData class (not from rate_data which is separate)
            yield_curve_spread = None
            try:
                yield_curve_raw = await self.market_data.get_yield_curve_data()
                if isinstance(yield_curve_raw, dict):
                    yield_curve_spread = yield_curve_raw.get("yield_curve_spread")
            except Exception:
                pass

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
            if yield_curve_spread is not None:
                if yield_curve_spread > 0:
                    yield_curve_signal = "normal"
                else:
                    yield_curve_signal = "inverted"
            else:
                yield_curve_signal = "unknown"

            # Derive macro regime
            if vix_regime == "high" or fear_greed_label == "fear":
                macro_regime = "risk_off"
            elif vix_regime == "low" and fear_greed_label == "greed":
                macro_regime = "risk_on"
            else:
                macro_regime = "neutral"

            # --- existing VIX + yield curve score (unchanged) ---
            vix_score = max(-1, min(1, (25 - vix_value) / 25))
            yield_score = max(-1, min(1, (yield_curve_spread or 0) / 200))
            score = (vix_score + yield_score) / 2

            # --- index breadth ---
            if index_data:
                above_200 = sum(
                    1 for v in index_data.values()
                    if isinstance(v, dict) and v.get("above_200ma")
                )
                # 4/4 above 200 ma = +0.15, 0/4 = -0.15
                score += (above_200 / 4 - 0.5) * 0.30

                sp5d = index_data.get("SP500", {}).get("chg_5d_pct") if isinstance(index_data, dict) else None
                if sp5d is not None:
                    # Cap contribution at ±0.10
                    score += max(-0.10, min(0.10, sp5d / 5 * 0.10))

            # --- rate environment ---
            if rate_data:
                us10y = rate_data.get("US10Y", {}).get("yield_pct") if isinstance(rate_data, dict) else None
                if us10y is not None:
                    if us10y > 5.0:
                        score -= 0.10   # high rates = valuation headwind
                    elif us10y < 3.5:
                        score += 0.05   # low rates = valuation tailwind

            # --- USD strength ---
            if fx_data:
                dxy_chg = fx_data.get("DXY", {}).get("chg_1m_pct") if isinstance(fx_data, dict) else None
                if dxy_chg is not None:
                    if dxy_chg > 3.0:
                        score -= 0.10   # sharp USD rise = risk-off
                    elif dxy_chg < -3.0:
                        score += 0.05   # USD weakness = modest risk-on

            # --- inflation expectations ---
            if inflation_data:
                bei = inflation_data.get("breakeven_10y") if isinstance(inflation_data, dict) else None
                if bei is not None:
                    if bei > 3.0:
                        score -= 0.10   # elevated inflation expectations = hawkish
                    elif bei < 2.0:
                        score += 0.05   # anchored expectations = benign

            market_score = round(max(-1.0, min(1.0, score)), 4)

            # Build extended MarketContext
            sp    = index_data.get("SP500",  {}) if isinstance(index_data, dict) else {}
            nq    = index_data.get("NASDAQ", {}) if isinstance(index_data, dict) else {}
            r10y  = rate_data.get("US10Y",   {}) if isinstance(rate_data, dict) else {}
            r30y  = rate_data.get("US30Y",   {}) if isinstance(rate_data, dict) else {}
            ffr   = rate_data.get("FED_FUNDS",{}) if isinstance(rate_data, dict) else {}
            dxy   = fx_data.get("DXY",       {}) if isinstance(fx_data, dict) else {}

            above_200 = sum(
                1 for v in index_data.values() if isinstance(v, dict) and v.get("above_200ma")
            ) if isinstance(index_data, dict) else None

            market_ctx = MarketContext(
                # existing fields
                vix_value=vix_value,
                vix_regime=vix_regime,
                fear_greed_index=fear_greed_index,
                fear_greed_label=fear_greed_label,
                yield_curve_spread=yield_curve_spread or 0.0,
                yield_curve_signal=yield_curve_signal or "unknown",
                macro_regime=macro_regime,
                market_score=market_score,
                # indexes
                sp500_level=sp.get("level"),
                sp500_chg_1d_pct=sp.get("chg_1d_pct"),
                sp500_chg_5d_pct=sp.get("chg_5d_pct"),
                sp500_chg_20d_pct=sp.get("chg_20d_pct"),
                nasdaq_chg_20d_pct=nq.get("chg_20d_pct"),
                indexes_above_200ma=above_200,
                # rates
                us10y_yield=r10y.get("yield_pct"),
                us10y_chg_1m_bps=r10y.get("chg_1m_bps"),
                us30y_yield=r30y.get("yield_pct"),
                fed_funds_rate=ffr.get("yield_pct"),
                # fx
                dxy_rate=dxy.get("rate"),
                dxy_chg_1m_pct=dxy.get("chg_1m_pct"),
                # inflation expectations
                breakeven_10y=inflation_data.get("breakeven_10y") if isinstance(inflation_data, dict) else None,
                breakeven_5y=inflation_data.get("breakeven_5y") if isinstance(inflation_data, dict) else None,
                breakeven_10y_chg_1m_bps=inflation_data.get("breakeven_10y_chg_1m") if isinstance(inflation_data, dict) else None,
                breakeven_trend=inflation_data.get("breakeven_trend") if isinstance(inflation_data, dict) else None,
                inflation_data_source=inflation_data.get("source") if isinstance(inflation_data, dict) else "unavailable",
            )

            # Build LLM input with new prompt version
            def _fmt(val, unit: str = "", signed: bool = False) -> str:
                if val is None:
                    return "N/A"
                prefix = "+" if signed and val > 0 else ""
                return f"{prefix}{val:.2f}{unit}"

            llm_input = {
                "prompt_version":          "market_v2",
                # existing
                "vix_value":               market_ctx.vix_value,
                "vix_regime":              market_ctx.vix_regime,
                "fear_greed_index":        market_ctx.fear_greed_index,
                "fear_greed_label":        market_ctx.fear_greed_label,
                "yield_curve_spread":      round(market_ctx.yield_curve_spread, 2),
                "yield_curve_signal":      market_ctx.yield_curve_signal,
                "macro_regime":            market_ctx.macro_regime,
                "market_score":            market_ctx.market_score,
                # new
                "sp500_1d":              market_ctx.sp500_chg_1d_pct,
                "sp500_5d":              market_ctx.sp500_chg_5d_pct,
                "sp500_20d":             market_ctx.sp500_chg_20d_pct,
                "nasdaq_20d":            market_ctx.nasdaq_chg_20d_pct,
                "indexes_above_200ma":    market_ctx.indexes_above_200ma,
                "us10y":                   market_ctx.us10y_yield,
                "us10y_chg_bps":         market_ctx.us10y_chg_1m_bps,
                "us30y":                   market_ctx.us30y_yield,
                "fed_funds":               market_ctx.fed_funds_rate,
                "dxy_chg_1m":              market_ctx.dxy_chg_1m_pct,
                "breakeven_10y":          market_ctx.breakeven_10y,
                "breakeven_5y":           market_ctx.breakeven_5y,
                "breakeven_trend":        market_ctx.breakeven_trend,
            }

            # Try LLM cache first
            llm_response = await redis_client.get_llm_narrative("market", llm_input)

            if llm_response is None:
                # Cache miss — call the LLM
                prompt = f"""
Analyze the following market data and provide insights on market conditions:

VOLATILITY & SENTIMENT
VIX {_fmt(llm_input['vix_value'])} ({llm_input['vix_regime']}) | Fear & Greed {llm_input['fear_greed_index']} ({llm_input['fear_greed_label']})

MAJOR INDEXES
S&P500 1d {_fmt(llm_input['sp500_1d'],'%',True)} | 5d {_fmt(llm_input['sp500_5d'],'%',True)} | 20d {_fmt(llm_input['sp500_20d'],'%',True)} | Nasdaq 20d {_fmt(llm_input['nasdaq_20d'],'%',True)} | {llm_input['indexes_above_200ma'] or 'N/A'}/4 indexes above 200ma

INTEREST RATES
10Y {_fmt(llm_input['us10y'],'%')} ({_fmt(llm_input['us10y_chg_bps'],'bps',True)} 1m) | 30Y {_fmt(llm_input['us30y'],'%')} | Fed funds {_fmt(llm_input['fed_funds'],'%')}

FX
DXY 1m {_fmt(llm_input['dxy_chg_1m'],'%',True)}

INFLATION EXPECTATIONS (forward-looking)
10Y breakeven {_fmt(llm_input['breakeven_10y'],'%')} ({llm_input['breakeven_trend'] or 'N/A'}) | 5Y breakeven {_fmt(llm_input['breakeven_5y'],'%')}

Yield curve {llm_input['yield_curve_spread']:.0f}bps ({llm_input['yield_curve_signal']}) | Regime: {llm_input['macro_regime']} | Score: {llm_input['market_score']:+.4f}

---
Reply with exactly 3 lines. Interpret what the data means — do not restate numbers.
MACRO:
RATES & FX:
REGIME:
"""
                logger.info("Calling LLM for market analysis ...")
                llm_response = await llm_client.generate_structured_completion(prompt, system_message="You are a macro market analyst.")

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
                "market_data": {
                    "vix": vix_data if isinstance(vix_data, dict) else {},
                    "index_data": index_data if isinstance(index_data, dict) else {},
                    "rate_data": rate_data if isinstance(rate_data, dict) else {},
                    "fx_data": fx_data if isinstance(fx_data, dict) else {},
                    "inflation_data": inflation_data if isinstance(inflation_data, dict) else {},
                },
                "analysis": {
                    **analysis,
                    "market_score": market_score,
                },
                "market_ctx": market_ctx.model_dump(),
                "timestamp": vix_data.get("timestamp", "") if isinstance(vix_data, dict) else "",
                "reasoning": [narrative]
            }

            logger.info("Market analysis completed")
            return result

        except Exception as e:
            logger.error(f"Error in market analysis: {e}")
            raise