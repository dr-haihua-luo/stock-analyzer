from typing import Dict, Any
from backend.agents.state import AnalysisState, StockContext
from backend.agents.llm_client import llm_client
from backend.data.stock_data import (
    fetch_ohlcv,
    fetch_latest_price,
    compute_52w_metrics,
    compute_technicals,
    compute_technical_score,
    compute_ma_trends,
    fetch_news_sentiment,
    compute_price_range_projection,
)
from backend.data.fundamentals_data import fetch_fundamentals, FundamentalsResult
from backend.data.earnings_quality_cache import get_earnings_quality
from backend.cache.redis_client import redis_client
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class StockAgent:
    def __init__(self):
        pass

    async def analyze(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze individual stock and return insights.
        Matches the interface expected by the LangGraph.
        """
        try:
            ticker = state.get("ticker")
            if not ticker:
                raise ValueError("Ticker symbol is required for stock analysis")

            logger.info(f"Starting stock analysis for {ticker}")

            # 1. OHLCV (6 months daily bars from Alpaca)
            df = await fetch_ohlcv(ticker)

            # 2. Current price
            current_price = await fetch_latest_price(ticker)

            # 3. 52-week metrics
            w52 = compute_52w_metrics(df, current_price)

            # 4. Technical indicators (RSI, MACD, BB, volume)
            technicals = compute_technicals(df)

            # 5. Technical score
            tech_score = compute_technical_score(
                technicals, w52["pct_from_52w_high"]
            )

            # 6. Moving average trends (informational only)
            ma_trends = compute_ma_trends(df)

            # 6. Statistical price range projection (volatility-based, informational only)
            # VIX regime is derived from market_agent's computed VIX value in state
            vix_val = (state.get("market_data") or {}).get("vix") or {}
            vix_value = vix_val.get("vix")
            vix_regime = None
            if vix_value is not None:
                if vix_value < 20:
                    vix_regime = "low"
                elif vix_value < 25:
                    vix_regime = "normal"
                else:
                    vix_regime = "high"
            price_range = compute_price_range_projection(df, current_price, vix_regime=vix_regime)

            # 6. Fetch real fundamentals from FinViz + TipRanks
            # TipRanks can be skipped via state flag to preserve rate limit
            skip_tipranks = state.get("skip_tipranks", True)
            logger.info(f"StockAgent: skip_tipranks={skip_tipranks} for {ticker}")
            fundamentals = await fetch_fundamentals(ticker, current_price, skip_tipranks=skip_tipranks)

            # 7. News sentiment via Alpaca NewsClient
            news_sentiment, news_summary = fetch_news_sentiment(ticker)

            # Extract clean scalars from FundamentalsResult for the prompt.
            # Use safe fallbacks so missing data shows as "N/A" not crashes.
            fv = fundamentals.finviz if fundamentals and fundamentals.finviz else None
            pe_str          = f"{fv.pe_ratio:.1f}" if fv and fv.pe_ratio else "N/A"
            fwd_pe_str      = f"{fv.forward_pe:.1f}" if fv and fv.forward_pe else "N/A"
            profit_margin   = f"{fv.profit_margin_pct:.1f}%" if fv and fv.profit_margin_pct else "N/A"
            roe_str         = f"{fv.roe_pct:.1f}%" if fv and fv.roe_pct else "N/A"
            eps_growth      = f"{fv.eps_next_5y_pct:.1f}%" if fv and fv.eps_next_5y_pct  else "N/A"
            insider_str     = (
                                f"{fv.net_insider_sentiment:+.0%} net ({fv.insider_buys_90d}B/{fv.insider_sells_90d}S)"
                                    if fv and fv.net_insider_sentiment is not None else "N/A"
                            )

            fund_score_str = f"{fundamentals.fundamental_score:+.3f}" if fundamentals else "N/A"

            ma_trend_summary = (
                f"MA trends — Long(12mo): {ma_trends.get('long_term_ma_trend', 'N/A')} | "
                f"Medium(2mo): {ma_trends.get('medium_term_ma_trend', 'N/A')} | "
                f"Short(2wk): {ma_trends.get('short_term_ma_trend', 'N/A')}"
            )

            # 8. LLM narrative for stock conditions
            # Build canonical input dict for cache key (must capture every
            # value that influences the prompt output)
            llm_input = {
                "prompt_version": "stock_v1",
                "ticker": ticker,
                "current_price": round(current_price, 2),
                "pct_from_52w_high": w52["pct_from_52w_high"],
                "rsi_14": technicals["rsi_14"],
                "macd_signal": technicals["macd_signal"],
                "bb_position": technicals["bb_position"],
                "volume_trend": technicals["volume_trend"],
                "pe_ratio": round(fv.pe_ratio, 1) if fv and fv.pe_ratio else None,
                "forward_pe": round(fv.forward_pe, 1) if fv and fv.forward_pe else None,
                "profit_margin_pct": round(fv.profit_margin_pct, 1) if fv and fv.profit_margin_pct else None,
                "roe_pct": round(fv.roe_pct, 1) if fv and fv.roe_pct else None,
                "eps_next_5y_pct": round(fv.eps_next_5y_pct, 1) if fv and fv.eps_next_5y_pct else None,
                "net_insider_sentiment": round(fv.net_insider_sentiment, 4) if fv and fv.net_insider_sentiment is not None else None,
                "insider_buys_90d": fv.insider_buys_90d if fv and fv.insider_buys_90d else None,
                "insider_sells_90d": fv.insider_sells_90d if fv and fv.insider_sells_90d else None,
                "news_sentiment": round(news_sentiment, 4),
                "fundamental_score": round(fundamentals.fundamental_score, 3) if fundamentals else None,
                "long_term_ma_trend": ma_trends.get("long_term_ma_trend"),
                "long_term_ma_value": ma_trends.get("long_term_ma_value"),
                "medium_term_ma_trend": ma_trends.get("medium_term_ma_trend"),
                "medium_term_ma_value": ma_trends.get("medium_term_ma_value"),
                "short_term_ma_trend": ma_trends.get("short_term_ma_trend"),
                "short_term_ma_value": ma_trends.get("short_term_ma_value"),
            }

            # Try LLM cache first
            narrative = await redis_client.get_llm_narrative("stock", llm_input)

            if narrative is None:
                # Cache miss — build prompt and call the LLM
                prompt = f"""
                You are a concise equity analyst. Respond using ONLY this exact template
                — no intro, no outro, no repetition of input data:

                TECHNICAL: <one sentence on RSI and MACD momentum direction>
                SETUP: <one sentence on Bollinger Band position and volume trend>
                FUNDAMENTALS: <one sentence on valuation and profitability>
                ANALYST VIEW: <one sentence on Wall Street consensus and price target>
                SENTIMENT: <one sentence on insider activity and news tone>

                Ticker: {ticker}  Price: ${current_price:.2f}
                52w-high: {w52['pct_from_52w_high']:+.1f}%\n
                RSI(14): {technicals['rsi_14']:.1f}
                MACD: {technicals['macd_signal']}
                BB: {technicals['bb_position']}
                Volume: {technicals['volume_trend']}
                {ma_trend_summary}\n
                P/E: {pe_str}  Fwd P/E: {fwd_pe_str}
                Profit margin: {profit_margin}  ROE: {roe_str}
                EPS growth 5Y: {eps_growth}\n
                Insider 90d: {insider_str}
                News sentiment: {news_sentiment:+.2f}
                Fundamental score: {fund_score_str}
                """
                logger.info(f"Stock agent prompt {ticker}: {prompt}")

                llm_response = await llm_client.generate_structured_completion(
                    prompt=prompt,
                    max_tokens=500
                )

                # Handle case where LLM returns None or empty response
                if not llm_response:
                    logger.warning(f"LLM returned empty response for {ticker} — using fallback narrative")
                    narrative = (
                        f"RSI {technicals['rsi_14']:.1f}, "
                        f"MACD {technicals['macd_signal']['trend'] if isinstance(technicals['macd_signal'], dict) else technicals['macd_signal']}, "
                        f"fundamental score {fund_score_str}."
                    )
                else:
                    narrative = llm_response.strip()
                    # Store in cache (2 hours TTL)
                    await redis_client.set_llm_narrative("stock", llm_input, narrative, ttl=7200)
                    logger.debug("stock_agent: LLM called and narrative cached")
                logger.info(f"LLM response = {narrative}")
            else:
                logger.debug("stock_agent: LLM narrative served from cache")

            # Use real fundamental score from FinViz/TipRanks, fallback to 0.0
            fund_score = fundamentals.fundamental_score if fundamentals else 0.0

            # 8. Fetch earnings quality from yfinance (informational only)
            earnings_quality = await get_earnings_quality(ticker)

            # Create stock data object (matching StockContext structure)
            stock_data = {
                "ticker": ticker,
                "current_price": current_price,
                "rsi_14": technicals["rsi_14"],
                "macd_signal": technicals["macd_signal"],
                "bb_position": technicals["bb_position"],
                "volume_trend": technicals["volume_trend"],
                "pe_ratio": None,  # not available from Alpaca market data API
                "price_vs_52w_high": w52["pct_from_52w_high"],
                "news_sentiment": news_sentiment,
                "technical_score": tech_score,
                "fundamental_score": fund_score,
                "long_term_ma_trend": ma_trends.get("long_term_ma_trend"),
                "long_term_ma_value": ma_trends.get("long_term_ma_value"),
                "medium_term_ma_trend": ma_trends.get("medium_term_ma_trend"),
                "medium_term_ma_value": ma_trends.get("medium_term_ma_value"),
                "short_term_ma_trend": ma_trends.get("short_term_ma_trend"),
                "short_term_ma_value": ma_trends.get("short_term_ma_value"),
                "price_range_projection": price_range,
            }

            # Analysis result (what the LLM produced)
            analysis = {
                "stock_analysis": narrative,
                "technical_score": tech_score,
                "fundamental_score": fund_score,
                "news_sentiment": news_sentiment,
                "news_summary": news_summary,
            }

            # Build LLM narrative for the reasoning field (stock agent already has narrative)
            # Store news_articles in state for news_sentiment_agent to consume
            result = {
                "stock_data": stock_data,
                "analysis": analysis,
                "fundamentals": fundamentals,
                "earnings_quality": earnings_quality,
                "news_articles": news_summary,  # raw news summaries for news_sentiment_agent
                "timestamp": datetime.utcnow().isoformat(),
                "reasoning": [f"[stock] {narrative}"],
            }

            logger.info(f"Stock analysis completed for {ticker}")
            return result

        except Exception as exc:
            logger.error(f"Error in stock analysis for {ticker}: {exc}")
            # Return error information in the expected format
            return {
                "stock_data": {},
                "analysis": {"error": f"stock_agent failed: {exc}"},
                "timestamp": datetime.utcnow().isoformat(),
            }