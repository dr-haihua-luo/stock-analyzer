"""
Overall Trading Analysis Agent — LangGraph node, runs last.

Synthesizes all prior agent outputs into one concise 6-month outlook:
  - market_narrative        (macro conditions)
  - sector_narrative        (sector rotation)
  - stock_narrative         (technical + fundamental)
  - news_sentiment_narrative (news + StockTwits synthesis)
  - signal, confidence, composite_score (quantitative result)

Produces a single verdict: BUY / HOLD / SELL with a 6-month outlook
window and concise reasoning (3-4 sentences max).

LLM response cached in Redis for 1 hour using the same key strategy
as market_agent/sector_agent/news_sentiment_agent — if none of the
inputs changed, the cached response is reused and the LLM is not called
again.
"""

import logging

from backend.agents.state import AnalysisState
from backend.agents.llm_client import llm_client
from backend.cache.redis_client import redis_client

logger = logging.getLogger(__name__)

OVERALL_ANALYSIS_TTL = 3600  # 1 hour


async def overall_analysis_node(state: AnalysisState) -> AnalysisState:
    """
    LangGraph node — final synthesis across all four prior narratives
    plus the computed signal. Runs after signal_generation_node.

    On failure, writes a fallback narrative and does not block the
    pipeline — this node never causes the overall analysis to fail.
    """
    ticker = state["ticker"]

    try:
        llm_input = _build_llm_input(state)

        narrative = await redis_client.get_llm_narrative("overall", llm_input)

        if narrative is None:
            narrative = await _call_llm(llm_input)

            if narrative:
                await redis_client.set_llm_narrative(
                    "overall", llm_input, narrative, ttl=OVERALL_ANALYSIS_TTL
                )
                logger.info("overall_analysis_agent: LLM called and cached --> %s", narrative)
            else:
                logger.warning(
                    "overall_analysis_agent: LLM returned empty response for %s",
                    ticker,
                )
        else:
            logger.info("overall_analysis_agent: narrative served from cache")

        if not narrative:
            narrative = _fallback_narrative(state)

        return {
            **state,
            "overall_analysis_narrative": narrative,
            "reasoning": state["reasoning"] + [f"[overall] {narrative}"],
        }

    except Exception as exc:
        logger.warning("overall_analysis_agent failed for %s: %s", ticker, exc)
        fallback = _fallback_narrative(state)
        return {
            **state,
            "overall_analysis_narrative": fallback,
            "reasoning": state["reasoning"] + [f"[overall] {fallback}"],
        }


def _build_llm_input(state: AnalysisState) -> dict:
    """
    Canonical dict used both as the Redis cache key and the prompt data.
    Includes all four upstream narratives plus the quantitative signal.
    Cache naturally busts whenever ANY upstream narrative or the
    signal/composite score changes — no manual invalidation needed.
    """
    def _extract(prefix: str) -> str:
        tag = f"[{prefix}]"
        for entry in state.get("reasoning", []) or []:
            if entry and entry.startswith(tag):
                return entry[len(tag):].strip()
        return ""

    signal_output = state.get("signal_output") or {}
    confidence = signal_output.get("confidence")
    composite = signal_output.get("composite_score")

    return {
        "prompt_version": "overall_v1",
        "ticker": state["ticker"],
        "market_narrative": _extract("market")[:500],
        "sector_narrative": _extract("sector")[:500],
        "stock_narrative": _extract("stock")[:800],
        "news_narrative": _extract("news_sentiment")[:500],
        "signal": signal_output.get("signal"),
        "confidence": round(confidence, 3) if confidence is not None else None,
        "composite_score": round(composite, 4) if composite is not None else None,
    }


async def _call_llm(llm_input: dict) -> str:
    """Build prompt from llm_input dict and call the LLM."""
    ticker = llm_input["ticker"]
    signal = llm_input.get("signal") or "N/A"
    confidence = llm_input.get("confidence")
    composite = llm_input.get("composite_score")

    confidence_str = f"{confidence:.0%}" if confidence is not None else "N/A"
    composite_str = f"{composite:+.4f}" if composite is not None else "N/A"

    logger.info("Calling LLM for overall analysis")
    return await llm_client.generate_structured_completion(
        prompt=(
            f"Ticker: {ticker}\n"
            f"Computed signal: {signal} "
            f"(confidence {confidence_str}, composite {composite_str})\n\n"
            f"MARKET ANALYSIS\n{llm_input['market_narrative'] or 'N/A'}\n\n"
            f"SECTOR ANALYSIS\n{llm_input['sector_narrative'] or 'N/A'}\n\n"
            f"STOCK ANALYSIS\n{llm_input['stock_narrative'] or 'N/A'}\n\n"
            f"NEWS & SENTIMENT\n{llm_input['news_narrative'] or 'N/A'}\n\n"
            f"---\n"
            f"Write a 6-MONTH outlook in exactly this format, "
            f"3-4 sentences total, concise:\n\n"
            f"VERDICT: <BUY, HOLD, or SELL — state it as the first two words>\n"
            f"REASONING: <2-3 sentences integrating the strongest signals "
            f"across all four inputs, and any conflicts between them>\n"
            f"WATCH: <one sentence on the single biggest risk or catalyst "
            f"to monitor over the next 6 months>"
        ),
        system_message=(
            "You are an elite, quantitative-leaning Senior Equity Research Analyst writing a final, "
            "concise verdict for a client. You have four independent "
            "analyses (macro, sector, stock technicals/fundamentals, "
            "news/social sentiment) plus a computed quantitative signal. "
            "Synthesize them into ONE clear 6-month outlook. "
            "Do not restate each input separately — integrate them into "
            "a single coherent view. Flag any tension between inputs "
            "(e.g. strong stock fundamentals but weak macro backdrop; "
            "Is social/news hype aligned with underlying financial reality, or is there a divergence (anomaly/trap)?) "
            "if present, since that materially affects conviction.  "
            "Cross-reference Sentiment/Technicals with Fundamentals. Provide a clear Risk/Reward asymmetric setup."
            "Final Action Bias: [BUY / HOLD / SELL / WATCH] with a specific thesis invalidation (stop-loss logic) "
            "price point and 6-to-12-month horizon target."
            "Be precise, avoid generic disclaimers, flag data gaps immediately, and prioritize downside risk protection."
        ),
        max_tokens=2000,
    )


def _fallback_narrative(state: AnalysisState) -> str:
    """Deterministic fallback if the LLM is unavailable — never blocks the pipeline."""
    signal_output = state.get("signal_output") or {}
    signal = signal_output.get("signal") or "HOLD"
    confidence = signal_output.get("confidence") or 0.0
    return (
        f"VERDICT: {signal}\n"
        f"REASONING: Computed signal is {signal} with {confidence:.0%} confidence "
        f"based on combined market, sector, and stock analysis.\n"
        f"WATCH: Monitor for changes in the underlying market, sector, "
        f"or company-specific data."
    )
