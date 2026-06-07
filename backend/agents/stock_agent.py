from backend.agents.state import AnalysisState, StockContext
from backend.agents.llm_client import call_llm
from backend.data.stock_data import (
    fetch_ohlcv,
    fetch_latest_price,
    compute_52w_metrics,
    compute_technicals,
    compute_technical_score,
    compute_fundamental_score,
    fetch_news_sentiment,
)


async def stock_analysis_node(state: AnalysisState) -> AnalysisState:
    """
    LangGraph node — Stage 3: individual stock analysis via Alpaca-py.
    Populates state["stock"] and appends to state["reasoning"].
    On any failure, writes state["error"] and returns with reduced data.
    """
    ticker = state["ticker"]

    try:
        # 1. OHLCV (6 months daily bars from Alpaca)
        df = fetch_ohlcv(ticker)

        # 2. Current price
        current_price = fetch_latest_price(ticker)

        # 3. 52-week metrics
        w52 = compute_52w_metrics(df, current_price)

        # 4. Technical indicators (RSI, MACD, BB, volume)
        technicals = compute_technicals(df)

        # 5. Technical score
        tech_score = compute_technical_score(
            technicals, w52["pct_from_52w_high"]
        )

        # 6. Fundamental proxy score (Alpaca has no P/E; documented as proxy)
        fund_score = compute_fundamental_score(df, w52["pct_from_52w_high"])

        # 7. News sentiment via Alpaca NewsClient
        news_sentiment = fetch_news_sentiment(ticker)

        # 8. LLM narrative for stock conditions
        narrative = await call_llm(
            system=(
                "You are a technical analyst. Write exactly 2 sentences summarising "
                "the stock's technical setup. Be specific about the RSI and MACD."
            ),
            user=(
                f"Ticker: {ticker} | Price: ${current_price:.2f} | "
                f"RSI(14): {technicals['rsi_14']} | "
                f"MACD: {technicals['macd_signal']} | "
                f"BB: {technicals['bb_position']} | "
                f"Volume trend: {technicals['volume_trend']} | "
                f"% from 52w high: {w52['pct_from_52w_high']:.1f}% | "
                f"News sentiment: {news_sentiment:+.2f}"
            ),
            max_tokens=150,
        )

        stock_ctx = StockContext(
            ticker=ticker,
            current_price=current_price,
            rsi_14=technicals["rsi_14"],
            macd_signal=technicals["macd_signal"],
            bb_position=technicals["bb_position"],
            volume_trend=technicals["volume_trend"],
            pe_ratio=None,           # not available from Alpaca market data API
            price_vs_52w_high=w52["pct_from_52w_high"],
            news_sentiment=news_sentiment,
            technical_score=tech_score,
            fundamental_score=fund_score,
        )

        return {
            **state,
            "stock": stock_ctx,
            "reasoning": state["reasoning"] + [f"[stock] {narrative}"],
        }

    except Exception as exc:
        return {
            **state,
            "error": f"stock_agent failed: {exc}",
            "reasoning": state["reasoning"] + [f"[stock] ERROR: {exc}"],
        }