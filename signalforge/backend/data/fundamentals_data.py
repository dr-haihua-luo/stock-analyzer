"""
Orchestrates FinViz + TipRanks concurrent fetch and computes
a real fundamental_score replacing the proxy in stock_data.py.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime, timezone

from backend.data.finviz_data import fetch_finviz_fundamentals, FinvizFundamentals
from backend.data.tipranks_data import fetch_tipranks_data, TipRanksData

logger = logging.getLogger(__name__)


@dataclass
class FundamentalsResult:
    ticker: str
    finviz: Optional[FinvizFundamentals]
    tipranks: Optional[TipRanksData]
    fundamental_score: float            # -1.0 to +1.0, replaces proxy
    score_components: dict              # breakdown for display
    fetched_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


async def fetch_fundamentals(
    ticker: str, current_price: Optional[float] = None, skip_tipranks: bool = True
) -> FundamentalsResult:
    """
    Fetch FinViz and TipRanks concurrently, then score.
    Never raises — returns FundamentalsResult with score=0.0 on full failure.
    Redis TTL: 4 hours.

    Args:
        ticker: Stock ticker symbol
        current_price: Current stock price for upside calculation
        skip_tipranks: If True, skip TipRanks API call (preserve rate limit)
    """
    logger.info(f"fetch_fundamentals: skip_tipranks={skip_tipranks} for {ticker}")
    finviz_task   = fetch_finviz_fundamentals(ticker)
    tipranks_task = fetch_tipranks_data(ticker, current_price, skip=skip_tipranks)
    logger.info(f"tipranks_task created with skip={skip_tipranks}")

    finviz_result, tipranks_result = await asyncio.gather(
        finviz_task, tipranks_task, return_exceptions=False
    )

    score, components = _compute_fundamental_score(finviz_result, tipranks_result)

    return FundamentalsResult(
        ticker=ticker,
        finviz=finviz_result,
        tipranks=tipranks_result,
        fundamental_score=score,
        score_components=components,
    )


def _compute_fundamental_score(
    fv: Optional[FinvizFundamentals],
    tr: Optional[TipRanksData],
) -> tuple[float, dict]:
    """
    Compute a -1.0 to +1.0 fundamental score from real data.

    Scoring components and weights:
      Valuation (P/E vs benchmark)     0.20
      Growth (EPS / Sales trajectory)  0.20
      Profitability (margins, ROE)      0.15
      Financial health (debt, ratios)   0.10
      Insider sentiment                 0.10
      Analyst consensus (TipRanks)      0.15
      Smart Score (TipRanks)            0.10
    Total: 1.00

    All components normalize to -1.0 to +1.0 before weighting.
    If a component's data is unavailable, its weight redistributes
    proportionally to available components.
    """
    components = {}
    weights    = {}

    # --- Valuation ---
    val_score = None
    if fv and fv.pe_ratio is not None:
        # Reasonable P/E range: <15=undervalued, 15-25=fair, 25-40=stretched, >40=expensive
        pe = fv.pe_ratio
        if pe <= 0:
            val_score = -0.5           # negative earnings
        elif pe < 15:
            val_score = 0.8
        elif pe < 25:
            val_score = 0.4
        elif pe < 35:
            val_score = 0.0
        elif pe < 50:
            val_score = -0.4
        else:
            val_score = -0.8

        # Adjust with forward P/E trend
        if fv.forward_pe and fv.forward_pe > 0 and pe > 0:
            if fv.forward_pe < pe * 0.85:   # forward P/E much lower = earnings growth expected
                val_score = min(1.0, val_score + 0.2)
            elif fv.forward_pe > pe * 1.15:  # forward P/E higher = earnings deterioration
                val_score = max(-1.0, val_score - 0.2)

    if val_score is not None:
        components["valuation"] = round(val_score, 4)
        weights["valuation"] = 0.20

    # --- Growth ---
    growth_score = None
    growth_signals = []
    if fv:
        if fv.eps_next_5y_pct is not None:
            # >20% annual growth = excellent, <0% = bad
            g = fv.eps_next_5y_pct
            growth_signals.append(max(-1.0, min(1.0, (g - 10) / 15)))
        if fv.eps_past_5y_pct is not None:
            g = fv.eps_past_5y_pct
            growth_signals.append(max(-1.0, min(1.0, (g - 5) / 15)))
        if fv.sales_past_5y_pct is not None:
            g = fv.sales_past_5y_pct
            growth_signals.append(max(-1.0, min(1.0, (g - 3) / 10)))

    if growth_signals:
        growth_score = sum(growth_signals) / len(growth_signals)
        components["growth"] = round(growth_score, 4)
        weights["growth"] = 0.20

    # --- Profitability ---
    prof_score = None
    prof_signals = []
    if fv:
        if fv.profit_margin_pct is not None:
            # >20% excellent, 10-20% good, 0-10% fair, <0% bad
            m = fv.profit_margin_pct
            prof_signals.append(max(-1.0, min(1.0, (m - 5) / 15)))
        if fv.roe_pct is not None:
            # >20% = strong return on equity
            prof_signals.append(max(-1.0, min(1.0, (fv.roe_pct - 10) / 15)))
        if fv.roa_pct is not None:
            prof_signals.append(max(-1.0, min(1.0, (fv.roa_pct - 5) / 10)))

    if prof_signals:
        prof_score = sum(prof_signals) / len(prof_signals)
        components["profitability"] = round(prof_score, 4)
        weights["profitability"] = 0.15

    # --- Financial health ---
    health_score = None
    health_signals = []
    if fv:
        if fv.current_ratio is not None:
            # >2 = healthy, 1-2 = OK, <1 = stress
            cr = fv.current_ratio
            health_signals.append(max(-1.0, min(1.0, (cr - 1) / 1.5)))
        if fv.debt_to_equity is not None:
            # <0.5 = low leverage, 0.5-1.5 = moderate, >1.5 = high
            de = fv.debt_to_equity
            health_signals.append(max(-1.0, min(1.0, (1.0 - de) / 0.75)))

    if health_signals:
        health_score = sum(health_signals) / len(health_signals)
        components["health"] = round(health_score, 4)
        weights["health"] = 0.10

    # --- Insider sentiment ---
    if fv and fv.net_insider_sentiment is not None:
        components["insider"] = round(fv.net_insider_sentiment, 4)
        weights["insider"] = 0.10

    # --- Analyst consensus (TipRanks) ---
    consensus_map = {
        "Strong Buy":  1.0,
        "Buy":         0.6,
        "Moderate Buy": 0.3,
        "Hold":        0.0,
        "Moderate Sell": -0.4,
        "Sell":       -0.7,
        "Strong Sell": -1.0,
    }
    if tr and tr.analyst_consensus:
        cs = consensus_map.get(tr.analyst_consensus, 0.0)
        components["analyst_consensus"] = round(cs, 4)
        weights["analyst_consensus"] = 0.15

    # --- Smart Score (TipRanks) ---
    if tr and tr.smart_score is not None:
        # Smart Score 1-10 → normalize to -1.0 to +1.0
        ss = (tr.smart_score - 5.5) / 4.5
        components["smart_score"] = round(ss, 4)
        weights["smart_score"] = 0.10

    # --- Weighted composite ---
    if not weights:
        return 0.0, {}

    # Redistribute weights proportionally if some components are missing
    total_weight = sum(weights.values())
    final_score = sum(
        components[k] * (weights[k] / total_weight)
        for k in components
    )
    final_score = round(max(-1.0, min(1.0, final_score)), 4)

    components["_total_weight_coverage"] = round(total_weight, 4)
    components["_final_score"] = final_score

    return final_score, components