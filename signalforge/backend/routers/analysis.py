from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from backend.db.session import get_db, AsyncSessionLocal
from backend.db.models import Signal
from backend.signal.models import (
    AnalysisRequest,
    AnalysisResponse,
    StockTwitsSentiment,
    FundamentalsDisplay,
    FinvizSnapshot,
    TipRanksSnapshot,
    EarningsQualityDisplay,
    QuarterlyDataPoint,
    StockContextDisplay,
    PriceRangeProjection, PriceRangeHorizon, PriceRangeLevel,
)
from backend.agents.graph import analysis_graph
from backend.data.stocktwits_data import fetch_stocktwits_sentiment
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestTradeRequest
from alpaca.data.enums import DataFeed
from backend.config import settings

logger = logging.getLogger(__name__)


async def _get_previous_signal(db: AsyncSession, ticker: str) -> Optional[str]:
    """
    Fetch the most recent signal for a ticker from PostgreSQL.
    Returns the signal string (BUY/HOLD/SELL) or None if no previous signal exists.
    """
    stmt = (
        select(Signal.signal)
        .where(Signal.ticker == ticker.upper())
        .order_by(desc(Signal.timestamp))
        .limit(1)
    )
    result = await db.execute(stmt)
    row = result.scalar_one_or_none()
    return row


def _extract_narrative(reasoning: list, agent: str) -> Optional[str]:
    """
    Extract narrative from reasoning list for a given agent.

    Args:
        reasoning: List of reasoning strings (e.g., "[market] outlook text")
        agent: Agent name to filter by (e.g., "market", "sector", "stock")

    Returns:
        The narrative text without the agent prefix, or None if not found.
    """
    for entry in reasoning or []:
        if isinstance(entry, str) and entry.startswith(f"[{agent}]"):
            return entry[len(f"[{agent}]"):].strip()
    return None


def _build_price_range_projection(raw: dict) -> Optional[PriceRangeProjection]:
    """Build a PriceRangeProjection model from the raw dict from stock_agent."""
    ranges = raw.get("ranges", {})

    def _to_horizon(h: dict) -> PriceRangeHorizon:
        return PriceRangeHorizon(
            **{
                "68pct": PriceRangeLevel(**h["68pct"]),
                "90pct": PriceRangeLevel(**h["90pct"]),
                "95pct": PriceRangeLevel(**h["95pct"]),
            }
        )

    return PriceRangeProjection(
        daily_volatility_pct=raw.get("daily_volatility_pct"),
        vix_adjustment_applied=raw.get("vix_adjustment_applied", False),
        vix_multiplier=raw.get("vix_multiplier"),
        two_week=_to_horizon(ranges["2_week"]) if "2_week" in ranges else None,
        one_month=_to_horizon(ranges["1_month"]) if "1_month" in ranges else None,
    )

router = APIRouter()


@router.post("/analyze", response_model=AnalysisResponse)
async def analyze_ticker(
    request: AnalysisRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Analyze a ticker and generate a trading signal.
    """
    try:
        logger.info(f"Received analysis request for {request.ticker}")
        logger.info(f"Request skip_tipranks value: {request.skip_tipranks}")

        # Fetch StockTwits BEFORE running the pipeline
        sentiment_raw = await fetch_stocktwits_sentiment(request.ticker.upper())

        # Fetch previous signal for hysteresis
        previous_signal = await _get_previous_signal(db, request.ticker)
        logger.info(f"Previous signal for {request.ticker}: {previous_signal}")

        # Initialize state for the graph
        initial_state = {
            "ticker": request.ticker.upper(),
            "skip_tipranks": request.skip_tipranks,
            "previous_signal": previous_signal,
            "market_data": None,
            "sector_data": None,
            "stock_data": None,
            "fundamentals": None,
            "earnings_quality": None,
            "news_articles": None,
            "stocktwits_raw": sentiment_raw,
            "news_sentiment_narrative": None,
            "analysis_result": None,
            "signal_output": None,
            "confidence_breakdown": None,
            "reasoning": [],
            "error": None,
            "timestamp": datetime.utcnow(),
            "retry_count": 0
        }
        logger.info(f"Initial state skip_tipranks: {initial_state.get('skip_tipranks')}")

        # Run the analysis graph
        final_state = await analysis_graph.ainvoke(initial_state)

        # Check for errors
        if final_state.get("error"):
            logger.error(f"Analysis failed for {request.ticker}: {final_state['error']}")
            raise HTTPException(status_code=500, detail=final_state["error"])

        # Extract results
        signal_output = final_state.get("signal_output")
        confidence_breakdown = final_state.get("confidence_breakdown")
        analysis_details = final_state.get("analysis_result", {})

        if not signal_output or not confidence_breakdown:
            logger.error(f"Missing signal output or confidence breakdown for {request.ticker}")
            raise HTTPException(status_code=500, detail="Analysis completed but results are incomplete")

        # Extract narratives and detailed LLM fields from analysis_result
        analysis_result = final_state.get("analysis_result", {})
        market_analysis = analysis_result.get("market", {})
        sector_analysis = analysis_result.get("sector", {})
        stock_analysis = analysis_result.get("stock", {})

        # Extract narratives from reasoning list (authoritative source)
        signal_output["market_narrative"] = market_analysis.get("OUTLOOK") or _extract_narrative(final_state.get("reasoning"), "market")
        signal_output["sector_narrative"] = sector_analysis.get("outlook") or _extract_narrative(final_state.get("reasoning"), "sector")
        signal_output["stock_narrative"] = stock_analysis.get("stock_analysis") or _extract_narrative(final_state.get("reasoning"), "stock")
        signal_output["overall_analysis_narrative"] = _extract_narrative(final_state.get("reasoning"), "overall")

        # Debug: confirm all three narratives are populated
        logger.info(
            "Narratives extracted — market: %s chars, sector: %s chars, stock: %s chars",
            len(signal_output["market_narrative"] or ""),
            len(signal_output["sector_narrative"] or ""),
            len(signal_output["stock_narrative"] or ""),
        )

        # Extract market LLM fields
        signal_output["market_macro"] = market_analysis.get("MACRO")
        signal_output["market_rates_fx"] = market_analysis.get("RATES & FX")
        signal_output["market_regime"] = market_analysis.get("REGIME")

        # Extract sector LLM fields (sector_narrative already set above)
        # rotation_momentum may be a dict with leading/lagging sector lists
        # — convert to a readable string to match the Optional[str] model field
        rotation_momentum = sector_analysis.get("rotation_momentum")
        if isinstance(rotation_momentum, dict):
            leading = rotation_momentum.get("leading", [])
            lagging = rotation_momentum.get("lagging", [])
            _parts = []
            if leading:
                _parts.append("Leading: " + ", ".join(
                    f"{s.get('sector', '?')} ({s.get('return', '?')})" for s in leading))
            if lagging:
                _parts.append("Lagging: " + ", ".join(
                    f"{s.get('sector', '?')} ({s.get('return', '?')})" for s in lagging))
            signal_output["sector_rotation_momentum"] = (
                "; ".join(_parts) if _parts else str(rotation_momentum))
        else:
            signal_output["sector_rotation_momentum"] = rotation_momentum
        signal_output["sector_economic_implications"] = sector_analysis.get("economic_implications")
        signal_output["sector_momentum_assessment"] = sector_analysis.get("momentum_assessment")
        signal_output["sector_outlook"] = sector_analysis.get("outlook")

        # Build FundamentalsDisplay from state
        raw_fund = final_state.get("fundamentals")
        if raw_fund:
            fv_snap = None
            if raw_fund.finviz:
                fv = raw_fund.finviz
                fv_snap = FinvizSnapshot(
                    pe_ratio=fv.pe_ratio,
                    forward_pe=fv.forward_pe,
                    peg_ratio=fv.peg_ratio,
                    ps_ratio=fv.ps_ratio,
                    pb_ratio=fv.pb_ratio,
                    profit_margin_pct=fv.profit_margin_pct,
                    roa_pct=fv.roa_pct,
                    roe_pct=fv.roe_pct,
                    roi_pct=fv.roi_pct,
                    gross_margin_pct=fv.gross_margin_pct,
                    oper_margin_pct=fv.oper_margin_pct,
                    debt_to_equity=fv.debt_to_equity,
                    insider_own_pct=fv.insider_own_pct,
                    inst_own_pct=fv.inst_own_pct,
                    inst_trans_pct=fv.inst_trans_pct,
                    net_insider_sentiment=fv.net_insider_sentiment,
                    insider_buys_90d=fv.insider_buys_90d,
                    insider_sells_90d=fv.insider_sells_90d,
                    eps_next_5y_pct=fv.eps_next_5y_pct,
                    market_cap_billions=fv.market_cap_billions,
                    beta=fv.beta,
                    recent_analyst_actions=fv.recent_analyst_actions,
                )
            tr_snap = None
            if raw_fund.tipranks:
                tr = raw_fund.tipranks
                tr_snap = TipRanksSnapshot(
                    analyst_consensus=tr.analyst_consensus,
                    price_target_mean=tr.price_target_mean,
                    price_target_high=tr.price_target_high,
                    price_target_low=tr.price_target_low,
                    number_of_analysts=tr.number_of_analysts,
                    buy_pct=tr.buy_pct,
                    hold_pct=tr.hold_pct,
                    sell_pct=tr.sell_pct,
                    buy_count=tr.buy_count,
                    hold_count=tr.hold_count,
                    sell_count=tr.sell_count,
                    smart_score=tr.smart_score,
                    upside_to_target_pct=tr.upside_to_target_pct,
                )
            signal_output["fundamentals"] = FundamentalsDisplay(
                ticker=request.ticker.upper(),
                fundamental_score=raw_fund.fundamental_score,
                score_components=raw_fund.score_components,
                finviz=fv_snap,
                tipranks=tr_snap,
            ).model_dump()

        # Build EarningsQualityDisplay from state
        raw_eq = final_state.get("earnings_quality")
        if raw_eq:
            from dataclasses import asdict
            d  = asdict(raw_eq)
            signal_output["earnings_quality"] = EarningsQualityDisplay(
                ticker=d["ticker"],
                revenue_qtrs=[QuarterlyDataPoint(**p)
                              for p in d.get("revenue_qtrs", [])],
                revenue_yoy_pct=d.get("revenue_yoy_pct"),
                revenue_trend=d.get("revenue_trend"),
                gross_margin_pct=d.get("gross_margin_pct"),
                operating_margin_pct=d.get("operating_margin_pct"),
                net_margin_pct=d.get("net_margin_pct"),
                gross_margin_qtrs=[QuarterlyDataPoint(**p)
                                   for p in d.get("gross_margin_qtrs", [])],
                operating_margin_qtrs=[QuarterlyDataPoint(**p)
                                       for p in d.get("operating_margin_qtrs", [])],
                margin_trend=d.get("margin_trend"),
                fcf_qtrs=[QuarterlyDataPoint(**p)
                          for p in d.get("fcf_qtrs", [])],
                fcf_margin_pct=d.get("fcf_margin_pct"),
                fcf_to_net_income=d.get("fcf_to_net_income"),
                fcf_trend=d.get("fcf_trend"),
                cash_billions=d.get("cash_billions"),
                total_debt_billions=d.get("total_debt_billions"),
                net_cash_billions=d.get("net_cash_billions"),
                current_ratio=d.get("current_ratio"),
                debt_to_equity=d.get("debt_to_equity"),
                cash_trend=d.get("cash_trend"),
                earnings_quality_score=d.get("earnings_quality_score"),
                quality_components=d.get("quality_components", {}),
            ).model_dump()

        # Attach StockTwits sentiment to response (already fetched before pipeline)
        signal_output["stocktwits_sentiment"] = StockTwitsSentiment(**sentiment_raw.__dict__) if sentiment_raw else None

        # Attach news_sentiment_narrative to response
        signal_output["news_sentiment_narrative"] = final_state.get(
            "news_sentiment_narrative"
        )

        # Attach price_at_signal to signal_output from stock_data in final_state
        stock_data = final_state.get("stock_data", {})
        signal_output["price_at_signal"] = stock_data.get("current_price") if stock_data else None

        # Attach stock_context (including MA trends) for the frontend
        if stock_data:
            signal_output["stock_context"] = StockContextDisplay(
                ticker=stock_data.get("ticker", request.ticker.upper()),
                current_price=stock_data.get("current_price"),
                rsi_14=stock_data.get("rsi_14"),
                macd_signal=stock_data.get("macd_signal"),
                bb_position=stock_data.get("bb_position"),
                volume_trend=stock_data.get("volume_trend"),
                price_vs_52w_high=stock_data.get("price_vs_52w_high"),
                news_sentiment=stock_data.get("news_sentiment"),
                technical_score=stock_data.get("technical_score"),
                fundamental_score=stock_data.get("fundamental_score"),
                long_term_ma_trend=stock_data.get("long_term_ma_trend"),
                long_term_ma_value=stock_data.get("long_term_ma_value"),
                medium_term_ma_trend=stock_data.get("medium_term_ma_trend"),
                medium_term_ma_value=stock_data.get("medium_term_ma_value"),
                short_term_ma_trend=stock_data.get("short_term_ma_trend"),
                short_term_ma_value=stock_data.get("short_term_ma_value"),
                price_range_projection=_build_price_range_projection(
                    stock_data.get("price_range_projection")
                ) if stock_data.get("price_range_projection") else None,
            ).model_dump()

        # Attach price_range_projection to top-level SignalOutput
        signal_output["price_range_projection"] = _build_price_range_projection(
            stock_data.get("price_range_projection")
        ) if stock_data.get("price_range_projection") else None

        # Save signal to database (background task)
        background_tasks.add_task(
            save_signal_to_db,
            signal_output,
            final_state
        )

        # Return response
        response = AnalysisResponse(
            signal=signal_output,
            confidence_breakdown=confidence_breakdown,
            analysis_details=analysis_details
        )

        logger.info(f"Analysis completed for {request.ticker}: {signal_output['signal']}")
        return response

    except Exception as e:
        logger.error(f"Error in analyze_ticker endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def save_signal_to_db(signal_output: dict, state: dict = None):
    """Save signal output to database. Creates own session to handle background task safely."""
    try:
        # Create our own session for the background task
        # The passed session may be closed by the time this runs
        async with AsyncSessionLocal() as session:
            # Extract price from stock_data in state
            stock_data = state.get("stock_data", {}) if state else {}
            price_at_signal = stock_data.get("current_price") if stock_data else None

            signal = Signal(
                ticker=signal_output["ticker"],
                signal=signal_output["signal"],
                confidence=signal_output["confidence"],
                timestamp=signal_output["timestamp"],
                price_at_signal=price_at_signal,
                composite_score=signal_output.get("composite_score"),
            )
            session.add(signal)
            await session.commit()
            logger.info(f"Saved signal for {signal_output['ticker']} to database")
    except Exception as e:
        logger.error(f"Error saving signal to database: {e}")
        # Silently fail - don't raise in background task to avoid affecting the main response
        # The signal was already generated successfully


@router.get("/signals/history")
async def get_signal_history(
    limit: int = 100,
    db: AsyncSession = Depends(get_db)
):
    """Get historical signals."""
    try:
        from sqlalchemy import select
        from sqlalchemy.exc import SQLAlchemyError

        query = select(Signal).order_by(Signal.timestamp.desc()).limit(limit)
        result = await db.execute(query)
        signals = result.scalars().all()

        return {
            "signals": [
                {
                    "id": s.id,
                    "ticker": s.ticker,
                    "signal": s.signal,
                    "confidence": s.confidence,
                    "timestamp": s.timestamp.isoformat()
                }
                for s in signals
            ]
        }
    except SQLAlchemyError as e:
        logger.error(f"Database error retrieving signal history: {e}")
        raise HTTPException(status_code=500, detail="Database error")
    except Exception as e:
        logger.error(f"Error retrieving signal history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _compute_outcome(signal: str, pct_change: Optional[float]) -> Optional[str]:
    """
    correct  — price moved in the predicted direction
    incorrect — price moved against the prediction
    pending  — no price data available yet
    """
    if pct_change is None:
        return "pending"
    if signal == "BUY" and pct_change > 0:
        return "correct"
    if signal == "SELL" and pct_change < 0:
        return "correct"
    if signal == "HOLD":
        return "neutral"
    return "incorrect"


@router.get("/performance/{ticker}")
async def get_performance(
    ticker: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Returns all signals for a ticker in the past 12 months,
    each with its historical price, signal type, composite score,
    and the current price fetched live from Alpaca.
    """
    ticker = ticker.upper()
    cutoff = datetime.utcnow() - timedelta(days=365)

    # Fetch historical signals from PostgreSQL
    stmt = (
        select(Signal)
        .where(
            Signal.ticker == ticker,
            Signal.timestamp >= cutoff,
        )
        .order_by(Signal.timestamp.asc())
    )
    rows = (await db.execute(stmt)).scalars().all()

    # Fetch current price from Alpaca
    current_price = None
    try:
        stock_client = StockHistoricalDataClient(
            api_key=settings.APCA_API_KEY_ID,
            secret_key=settings.APCA_API_SECRET_KEY,
        )
        trade_req = StockLatestTradeRequest(
            symbol_or_symbols=ticker,
            feed=DataFeed.IEX,
        )
        trades = stock_client.get_stock_latest_trade(trade_req)
        current_price = float(trades[ticker].price)
    except Exception as exc:
        logger.warning("performance: could not fetch current price: %s", exc)

    # Build response
    data_points = []
    for r in rows:
        price = r.price_at_signal
        pct_change = None
        if price and current_price and price > 0:
            pct_change = round((current_price - price) / price * 100, 2)

        data_points.append({
            "id": str(r.id),
            "date": r.timestamp.isoformat(),
            "signal": r.signal,
            "confidence": r.confidence,
            "price_at_signal": price,
            "composite_score": r.composite_score,
            "current_price": current_price,
            "pct_change": pct_change,
            # outcome: did price move in the direction predicted?
            "outcome": _compute_outcome(r.signal, pct_change),
        })

    # Summary stats
    buys = [d for d in data_points if d["signal"] == "BUY" and d["pct_change"] is not None]
    sells = [d for d in data_points if d["signal"] == "SELL" and d["pct_change"] is not None]

    return {
        "ticker": ticker,
        "current_price": current_price,
        "period": "12 months",
        "total_signals": len(data_points),
        "summary": {
            "buy_signals": len(buys),
            "buy_correct": sum(1 for d in buys if d["outcome"] == "correct"),
            "buy_avg_return_pct": round(sum(d["pct_change"] for d in buys) / len(buys), 2) if buys else None,
            "sell_signals": len(sells),
            "sell_correct": sum(1 for d in sells if d["outcome"] == "correct"),
            "sell_avg_return_pct": round(sum(d["pct_change"] for d in sells) / len(sells), 2) if sells else None,
        },
        "signals": data_points,
    }