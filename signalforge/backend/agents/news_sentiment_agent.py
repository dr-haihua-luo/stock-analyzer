"""
News & Sentiment Agent — LangGraph node.

Reads from state:
  - state["news_articles"]   list of dicts from Alpaca (set by stock_agent)
  - state["stocktwits_raw"]    SentimentResult dataclass (set by router)

Calls the LLM once to synthesize both into a cohesive narrative.
Writes to state["news_sentiment_narrative"].

No new API calls — purely a synthesis node over already-fetched data.
LLM response is cached in Redis with the same hash-based key strategy
used by market_agent and sector_agent (60 min TTL).
"""

import logging
from typing import Optional

from backend.agents.state import AnalysisState
from backend.agents.llm_client import llm_client
from backend.cache.redis_client import redis_client

logger = logging.getLogger(__name__)


async def news_sentiment_node(state: AnalysisState) -> AnalysisState:
    """
    LangGraph node — synthesizes Alpaca news + StockTwits sentiment.
    On failure writes error to state and passes through without blocking
    the signal engine.
    """
    ticker = state["ticker"]
    news_articles = state.get("news_articles") or []
    stocktwits_raw = state.get("stocktwits_raw")

    try:
        # Build LLM input dict for cache key and prompt
        llm_input = _build_llm_input(ticker, news_articles, stocktwits_raw)

        # Try cache first
        narrative = await redis_client.get_llm_narrative("news_sentiment", llm_input)

        if narrative is None:
            narrative = await _call_llm(llm_input)

            if narrative:
                await redis_client.set_llm_narrative(
                    "news_sentiment", llm_input, narrative
                )
                logger.debug("news_sentiment_agent: LLM called and cached")
        else:
            logger.info("news_sentiment_agent: narrative served from cache")

        return {
            **state,
            "news_sentiment_narrative": narrative or "",
            "reasoning": state["reasoning"] + [
                f"[news_sentiment] {narrative or 'No narrative generated'}"
            ],
        }

    except Exception as exc:
        logger.warning("news_sentiment_agent failed for %s: %s", ticker, exc)
        return {
            **state,
            "news_sentiment_narrative": "",
            "reasoning": state["reasoning"] + [
                f"[news_sentiment] ERROR: {exc}"
            ],
        }


def _build_llm_input(
    ticker: str,
    articles: list,
    stocktwits_raw,
) -> dict:
    """
    Build the canonical dict used both as the cache key and the
    prompt data. All values must be JSON-serialisable and rounded
    to avoid floating-point cache misses.

    Article headlines are sorted and deduped before hashing so
    minor ordering differences don't bust the cache.
    """
    # Distill articles to headline + source for hashing
    # (full summaries could vary in whitespace etc.)
    article_fingerprints = sorted(set(
        a.get("summary", "")[:80] for a in articles if a.get("summary")
    ))

    st = stocktwits_raw
    has_st = st and getattr(st, "source", "unavailable") != "unavailable"

    return {
        "prompt_version": "news_sentiment_v1",
        "ticker": ticker,
        "article_count": len(articles),
        "article_headlines": article_fingerprints,
        "st_source": getattr(st, "source", "unavailable"),
        "st_bullish_pct": round(st.bullish_pct or 0, 1) if has_st else None,
        "st_bearish_pct": round(st.bearish_pct or 0, 1) if has_st else None,
        "st_neutral_pct": round(st.neutral_pct or 0, 1) if has_st else None,
        "st_label": getattr(st, "sentiment_label", None) if has_st else None,
        "st_messages": getattr(st, "total_messages_sampled", None),
        "st_labeled": getattr(st, "labeled_messages", None),
    }


async def _call_llm(llm_input: dict) -> str:
    """Build prompt from llm_input dict and call the LLM."""

    ticker = llm_input["ticker"]
    articles = llm_input.get("article_headlines", [])
    article_count = llm_input.get("article_count", 0)

    # Format article list for the prompt
    if articles:
        articles_text = "\n".join(
            f"  {i+1}. {h}" for i, h in enumerate(articles[:15])
        )
    else:
        articles_text = "  No recent news articles available."

    # StockTwits block
    st_label = llm_input.get("st_label")
    st_bullish = llm_input.get("st_bullish_pct")
    st_bearish = llm_input.get("st_bearish_pct")
    st_neutral = llm_input.get("st_neutral_pct")
    st_msgs = llm_input.get("st_messages")
    st_labeled = llm_input.get("st_labeled")

    if st_label:
        st_text = (
            f"Overall: {st_label} | "
            f"Bullish {st_bullish}% / Neutral {st_neutral}% / Bearish {st_bearish}%"
        )
        if st_msgs:
            coverage = f"{st_labeled}/{st_msgs}" if st_labeled else str(st_msgs)
            st_text += f" | Posts sampled: {coverage}"
    else:
        st_text = "StockTwits data unavailable."

    return await llm_client.generate_structured_completion(
        prompt=(
            f"Stock: {ticker}\n\n"
            f"RECENT NEWS ({article_count} articles, past 10 days)\n"
            f"{articles_text}\n\n"
            f"STOCKTWITS SOCIAL SENTIMENT\n"
            f"{st_text}\n\n"
            f"Write 3 lines using exactly these labels:\n"
            f"NEWS: <one sentence on the dominant news theme and what it signals>\n"
            f"SENTIMENT: <one sentence interpreting the social mood and "
            f"whether retail investors are aligned with or diverging from the news>\n"
            f"OUTLOOK: <one sentence on what the combined news and sentiment "
            f"picture implies for near-term price action>"
        ),
        system_message=(
            "You are a market intelligence analyst specialising in retail "
            "investor sentiment and news flow. Given recent news headlines "
            "and social sentiment data for a stock, provide genuine insight "
            "into what the market narrative is and whether news and social "
            "sentiment are aligned or diverging. "
            "Never restate the raw numbers as your analysis. "
            "Identify the dominant theme in the news and what it signals."
        ),
        max_tokens=200,
    )