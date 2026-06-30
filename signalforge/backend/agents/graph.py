from typing import Dict, Any
from langgraph.graph import StateGraph, END
from backend.agents.state import AnalysisState
from backend.agents.market_agent import MarketAgent
from backend.agents.sector_agent import SectorAgent
from backend.agents.stock_agent import StockAgent
from backend.agents.news_sentiment_agent import news_sentiment_node
from backend.signal.engine import SignalEngine
import logging

logger = logging.getLogger(__name__)


# Initialize agents
market_agent = MarketAgent()
sector_agent = SectorAgent()
stock_agent = StockAgent()
signal_engine = SignalEngine()


async def market_analysis_node(state: AnalysisState) -> AnalysisState:
    """Node for market analysis."""
    try:
        logger.info("Executing market analysis node")

        # Ensure state is a dict and make a safe copy for the agent
        state_dict = dict(state) if state is not None else {}

        # Get market analysis result
        market_result = await market_agent.analyze(state_dict)

        # Handle case where market_result might be None or invalid
        if market_result is None:
            logger.warning("Market analysis returned None result")
            state["error"] = "Market analysis returned no data"
            return state

        # Ensure market_result is a dictionary
        if not isinstance(market_result, dict):
            logger.warning(f"Market analysis returned unexpected type: {type(market_result)}")
            state["error"] = f"Market analysis returned invalid data type: {type(market_result).__name__}"
            return state

        # Safely extract data from market_result
        market_data = market_result.get("market_data")
        analysis = market_result.get("analysis")
        market_reasoning = market_result.get("reasoning", [])

        # Ensure extracted data is in expected format
        if market_data is not None and not isinstance(market_data, dict):
            logger.warning(f"Market data is not a dict: {type(market_data)}")
            market_data = None

        if analysis is not None and not isinstance(analysis, dict):
            logger.warning(f"Analysis is not a dict: {type(analysis)}")
            analysis = None

        # Update state with safe defaults
        state["market_data"] = market_data if market_data is not None else {}

        # Safely update analysis_result
        current_analysis_result = state.get("analysis_result")
        if not isinstance(current_analysis_result, dict):
            current_analysis_result = {}

        if analysis is not None:
            state["analysis_result"] = {**current_analysis_result, "market": analysis}
        else:
            # Still update analysis_result with empty market analysis to avoid KeyError later
            state["analysis_result"] = {**current_analysis_result, "market": {}}

        # Accumulate reasoning entries
        current_reasoning = state.get("reasoning", [])
        if not isinstance(current_reasoning, list):
            current_reasoning = []
        state["reasoning"] = current_reasoning + market_reasoning if isinstance(market_reasoning, list) else current_reasoning

        return state
    except Exception as e:
        logger.error(f"Error in market analysis node: {e}")
        state["error"] = f"Market analysis failed: {str(e)}"
        return state


async def sector_analysis_node(state: AnalysisState) -> AnalysisState:
    """Node for sector analysis."""
    try:
        logger.info("Executing sector analysis node")

        # Ensure state is a dict and make a safe copy for the agent
        state_dict = dict(state) if state is not None else {}

        # Get sector analysis result
        sector_result = await sector_agent.analyze(state_dict)

        # Handle case where sector_result might be None or invalid
        if sector_result is None:
            logger.warning("Sector analysis returned None result")
            state["error"] = "Sector analysis returned no data"
            return state

        # Ensure sector_result is a dictionary
        if not isinstance(sector_result, dict):
            logger.warning(f"Sector analysis returned unexpected type: {type(sector_result)}")
            state["error"] = f"Sector analysis returned invalid data type: {type(sector_result).__name__}"
            return state

        # Safely extract data from sector_result
        sector_data = sector_result.get("sector_data")
        analysis = sector_result.get("analysis")
        sector_reasoning = sector_result.get("reasoning", [])

        # Ensure extracted data is in expected format
        if sector_data is not None and not isinstance(sector_data, dict):
            logger.warning(f"Sector data is not a dict: {type(sector_data)}")
            sector_data = None

        if analysis is not None and not isinstance(analysis, dict):
            logger.warning(f"Analysis is not a dict: {type(analysis)}")
            analysis = None

        # Update state with safe defaults
        state["sector_data"] = sector_data if sector_data is not None else {}

        # Safely update analysis_result
        current_analysis_result = state.get("analysis_result")
        if not isinstance(current_analysis_result, dict):
            current_analysis_result = {}

        if analysis is not None:
            state["analysis_result"] = {**current_analysis_result, "sector": analysis}
        else:
            # Still update analysis_result with empty sector analysis to avoid KeyError later
            state["analysis_result"] = {**current_analysis_result, "sector": {}}

        # Accumulate reasoning entries
        current_reasoning = state.get("reasoning", [])
        if not isinstance(current_reasoning, list):
            current_reasoning = []
        state["reasoning"] = current_reasoning + sector_reasoning if isinstance(sector_reasoning, list) else current_reasoning

        return state
    except Exception as e:
        logger.error(f"Error in sector analysis node: {e}")
        state["error"] = f"Sector analysis failed: {str(e)}"
        return state


async def stock_analysis_node(state: AnalysisState) -> AnalysisState:
    """Node for stock analysis."""
    try:
        logger.info("Executing stock analysis node")

        # Ensure state is a dict and make a safe copy for the agent
        state_dict = dict(state) if state is not None else {}

        # Get stock analysis result
        stock_result = await stock_agent.analyze(state_dict)

        # Handle case where stock_result might be None or invalid
        if stock_result is None:
            logger.warning("Stock analysis returned None result")
            state["error"] = "Stock analysis returned no data"
            return state

        # Ensure stock_result is a dictionary
        if not isinstance(stock_result, dict):
            logger.warning(f"Stock analysis returned unexpected type: {type(stock_result)}")
            state["error"] = f"Stock analysis returned invalid data type: {type(stock_result).__name__}"
            return state

        # Safely extract data from stock_result
        stock_data = stock_result.get("stock_data")
        analysis = stock_result.get("analysis")
        fundamentals = stock_result.get("fundamentals")
        stock_reasoning = stock_result.get("reasoning", [])

        # Ensure extracted data is in expected format
        if stock_data is not None and not isinstance(stock_data, dict):
            logger.warning(f"Stock data is not a dict: {type(stock_data)}")
            stock_data = None

        if analysis is not None and not isinstance(analysis, dict):
            logger.warning(f"Analysis is not a dict: {type(analysis)}")
            analysis = None

        # Update state with safe defaults
        state["stock_data"] = stock_data if stock_data is not None else {}

        # Safely update analysis_result
        current_analysis_result = state.get("analysis_result")
        if not isinstance(current_analysis_result, dict):
            current_analysis_result = {}

        if analysis is not None:
            state["analysis_result"] = {**current_analysis_result, "stock": analysis}
        else:
            # Still update analysis_result with empty stock analysis to avoid KeyError later
            state["analysis_result"] = {**current_analysis_result, "stock": {}}

        # Update fundamentals in state (dataclass, not dict)
        state["fundamentals"] = fundamentals

        # Pass through news_articles for news_sentiment_node
        stock_news_articles = stock_result.get("news_articles")
        if stock_news_articles is not None:
            state["news_articles"] = stock_news_articles

        # Accumulate reasoning entries
        current_reasoning = state.get("reasoning", [])
        if not isinstance(current_reasoning, list):
            current_reasoning = []
        state["reasoning"] = current_reasoning + stock_reasoning if isinstance(stock_reasoning, list) else current_reasoning

        return state
    except Exception as e:
        logger.error(f"Error in stock analysis node: {e}")
        state["error"] = f"Stock analysis failed: {str(e)}"
        return state


async def signal_generation_node(state: AnalysisState) -> AnalysisState:
    """Node for generating final signal."""
    try:
        logger.info("Executing signal generation node")

        # Ensure state is a dict and make a safe copy
        state_dict = dict(state) if state is not None else {}

        # Safely get data with defaults to prevent None being passed to signal engine
        market_data = state_dict.get("market_data") or {}
        sector_data = state_dict.get("sector_data") or {}
        stock_data = state_dict.get("stock_data") or {}
        analysis_results = state_dict.get("analysis_result", {}) or {}
        ticker = state_dict.get("ticker", "") or ""

        # Ensure all data is in expected dict format
        if not isinstance(market_data, dict):
            market_data = {}
        if not isinstance(sector_data, dict):
            sector_data = {}
        if not isinstance(stock_data, dict):
            stock_data = {}
        if not isinstance(analysis_results, dict):
            analysis_results = {}

        signal_result = await signal_engine.generate_signal(
            market_data=market_data,
            sector_data=sector_data,
            stock_data=stock_data,
            analysis_results=analysis_results,
            ticker=ticker
        )

        # Safely extract results from signal engine
        signal_output = None
        confidence_breakdown = None

        if isinstance(signal_result, dict):
            signal_output = signal_result.get("signal_output")
            confidence_breakdown = signal_result.get("confidence_breakdown")

            # Ensure extracted data is in expected format
            if signal_output is not None and not isinstance(signal_output, dict):
                signal_output = None
            if confidence_breakdown is not None and not isinstance(confidence_breakdown, dict):
                confidence_breakdown = None

        state["signal_output"] = signal_output
        state["confidence_breakdown"] = confidence_breakdown
        return state
    except Exception as e:
        logger.error(f"Error in signal generation node: {e}")
        state["error"] = f"Signal generation failed: {str(e)}"
        return state


def should_continue(state: AnalysisState) -> str:
    """Determine if the graph should continue or end."""
    if state.get("error"):
        logger.warning(f"Graph ending due to error: {state['error']}")
        return "end"
    return "continue"


def create_analysis_graph() -> StateGraph:
    """Create the LangGraph state machine for analysis."""

    # Create the graph
    workflow = StateGraph(AnalysisState)

    # Add nodes
    workflow.add_node("market_analysis", market_analysis_node)
    workflow.add_node("sector_analysis", sector_analysis_node)
    workflow.add_node("stock_analysis", stock_analysis_node)
    workflow.add_node("news_sentiment", news_sentiment_node)
    workflow.add_node("signal_generation", signal_generation_node)

    # Set entry point
    workflow.set_entry_point("market_analysis")

    # Add edges
    workflow.add_edge("market_analysis", "sector_analysis")
    workflow.add_edge("sector_analysis", "stock_analysis")
    workflow.add_edge("stock_analysis", "news_sentiment")
    workflow.add_edge("news_sentiment", "signal_generation")
    workflow.add_edge("signal_generation", END)

    # Add conditional edges for error handling
    workflow.add_conditional_edges(
        "market_analysis",
        should_continue,
        {
            "continue": "sector_analysis",
            "end": END
        }
    )
    workflow.add_conditional_edges(
        "sector_analysis",
        should_continue,
        {
            "continue": "stock_analysis",
            "end": END
        }
    )
    workflow.add_conditional_edges(
        "stock_analysis",
        should_continue,
        {
            "continue": "news_sentiment",
            "end": END
        }
    )
    workflow.add_conditional_edges(
        "news_sentiment",
        should_continue,
        {
            "continue": "signal_generation",
            "end": END
        }
    )
    workflow.add_conditional_edges(
        "signal_generation",
        should_continue,
        {
            "continue": END,  # Actually ends anyway
            "end": END
        }
    )

    return workflow


# Compile the graph
analysis_graph = create_analysis_graph().compile()