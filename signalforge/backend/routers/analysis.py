from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from backend.db.session import get_db, AsyncSessionLocal
from backend.db.models import Signal
from backend.signal.models import (
    AnalysisRequest,
    AnalysisResponse,
    StockTwitsSentiment,
    FundamentalsDisplay,
    FinvizSnapshot,
    TipRanksSnapshot,
)
from backend.agents.graph import analysis_graph
from backend.data.stocktwits_data import fetch_stocktwits_sentiment
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/analyze", response_model=AnalysisResponse)
async def analyze_ticker(
    request: AnalysisRequest,
    background_tasks: BackgroundTasks
):
    """
    Analyze a ticker and generate a trading signal.
    """
    try:
        logger.info(f"Received analysis request for {request.ticker}")
        logger.info(f"Request skip_tipranks value: {request.skip_tipranks}")

        # Initialize state for the graph
        initial_state = {
            "ticker": request.ticker.upper(),
            "skip_tipranks": request.skip_tipranks,
            "market_data": None,
            "sector_data": None,
            "stock_data": None,
            "fundamentals": None,
            "analysis_result": None,
            "signal_output": None,
            "confidence_breakdown": None,
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
                    profit_margin_pct=fv.profit_margin_pct,
                    roe_pct=fv.roe_pct,
                    debt_to_equity=fv.debt_to_equity,
                    insider_own_pct=fv.insider_own_pct,
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

        # Fetch StockTwits sentiment (non-blocking, informational only)
        sentiment_raw = await fetch_stocktwits_sentiment(request.ticker.upper())
        signal_output["stocktwits_sentiment"] = StockTwitsSentiment(**sentiment_raw.__dict__) if sentiment_raw else None

        # Save signal to database (background task)
        background_tasks.add_task(
            save_signal_to_db,
            signal_output
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


async def save_signal_to_db(signal_output: dict):
    """Save signal output to database. Creates own session to handle background task safely."""
    try:
        # Create our own session for the background task
        # The passed session may be closed by the time this runs
        async with AsyncSessionLocal() as session:
            signal = Signal(
                ticker=signal_output["ticker"],
                signal=signal_output["signal"],
                confidence=signal_output["confidence"],
                timestamp=signal_output["timestamp"]
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