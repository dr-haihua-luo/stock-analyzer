"""
Orchestrates FinViz + TipRanks concurrent fetch and computes
a real fundamental_score replacing the proxy in stock_data.py.
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field, asdict
from typing import Optional
from datetime import datetime, timezone

from backend.data.finviz_data import fetch_finviz_fundamentals, FinvizFundamentals
from backend.data.tipranks_data import fetch_tipranks_data, TipRanksData
from backend.cache.redis_client import redis_client

logger = logging.getLogger(__name__)

# Cache TTL for fundamentals data
FUNDAMENTALS_CACHE_TTL = 14400   # 4 hours — matches the TTL already
                                   # documented for FinViz/TipRanks data


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
    cache_key = f"data:fundamentals:{ticker.upper()}"

    cached = await redis_client.get_raw(cache_key)
    if cached:
        try:
            data = json.loads(cached)
            return _fundamentals_result_from_dict(data)
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            logger.warning("Failed to parse cached fundamentals for %s: %s", ticker, exc)

    logger.info(f"fetch_fundamentals: skip_tipranks={skip_tipranks} for {ticker}")
    finviz_task   = fetch_finviz_fundamentals(ticker)
    tipranks_task = fetch_tipranks_data(ticker, current_price, skip=skip_tipranks)
    logger.info(f"tipranks_task created with skip={skip_tipranks}")

    finviz_result, tipranks_result = await asyncio.gather(
        finviz_task, tipranks_task, return_exceptions=False
    )

    score, components = _compute_fundamental_score(finviz_result, tipranks_result)

    result = FundamentalsResult(
        ticker=ticker,
        finviz=finviz_result,
        tipranks=tipranks_result,
        fundamental_score=score,
        score_components=components,
    )

    # Cache the result as JSON (convert dataclasses to dicts)
    result_dict = asdict(result)
    await redis_client.set_raw(
        cache_key, json.dumps(result_dict, default=str), ttl=FUNDAMENTALS_CACHE_TTL
    )

    return result


def _fundamentals_result_from_dict(data: dict) -> FundamentalsResult:
    """Reconstruct FundamentalsResult (with nested dataclasses) from cached JSON."""
    fv_data = data.get("finviz")
    tr_data = data.get("tipranks")
    return FundamentalsResult(
        ticker=data["ticker"],
        finviz=_finviz_fundamentals_from_dict(fv_data) if fv_data else None,
        tipranks=_tipranks_data_from_dict(tr_data) if tr_data else None,
        fundamental_score=data["fundamental_score"],
        score_components=data["score_components"],
        fetched_at=data.get("fetched_at", ""),
    )


def _finviz_fundamentals_from_dict(data: dict) -> "FinvizFundamentals":
    """Reconstruct FinvizFundamentals from cached dict."""
    from backend.data.finviz_data import FinvizFundamentals
    return FinvizFundamentals(
        ticker=data.get("ticker", ""),
        pe_ratio=data.get("pe_ratio"),
        forward_pe=data.get("forward_pe"),
        peg_ratio=data.get("peg_ratio"),
        ps_ratio=data.get("ps_ratio"),
        pb_ratio=data.get("pb_ratio"),
        price_to_fcf=data.get("price_to_fcf"),
        eps_ttm=data.get("eps_ttm"),
        eps_next_year=data.get("eps_next_year"),
        eps_next_5y_pct=data.get("eps_next_5y_pct"),
        eps_past_5y_pct=data.get("eps_past_5y_pct"),
        sales_past_5y_pct=data.get("sales_past_5y_pct"),
        gross_margin_pct=data.get("gross_margin_pct"),
        oper_margin_pct=data.get("oper_margin_pct"),
        profit_margin_pct=data.get("profit_margin_pct"),
        roa_pct=data.get("roa_pct"),
        roe_pct=data.get("roe_pct"),
        roi_pct=data.get("roi_pct"),
        debt_to_equity=data.get("debt_to_equity"),
        current_ratio=data.get("current_ratio"),
        quick_ratio=data.get("quick_ratio"),
        insider_own_pct=data.get("insider_own_pct"),
        insider_trans_pct=data.get("insider_trans_pct"),
        inst_own_pct=data.get("inst_own_pct"),
        short_float_pct=data.get("short_float_pct"),
        market_cap_billions=data.get("market_cap_billions"),
        beta=data.get("beta"),
        net_insider_sentiment=data.get("net_insider_sentiment"),
        insider_buys_90d=data.get("insider_buys_90d"),
        insider_sells_90d=data.get("insider_sells_90d"),
        recent_analyst_actions=data.get("recent_analyst_actions", []),
        fetched_at=data.get("fetched_at", ""),
    )


def _tipranks_data_from_dict(data: dict) -> "TipRanksData":
    """Reconstruct TipRanksData from cached dict."""
    from backend.data.tipranks_data import TipRanksData
    return TipRanksData(
        ticker=data.get("ticker", ""),
        analyst_consensus=data.get("analyst_consensus"),
        price_target_mean=data.get("price_target_mean"),
        price_target_high=data.get("price_target_high"),
        price_target_low=data.get("price_target_low"),
        number_of_analysts=data.get("number_of_analysts"),
        buy_count=data.get("buy_count"),
        hold_count=data.get("hold_count"),
        sell_count=data.get("sell_count"),
        smart_score=data.get("smart_score"),
        buy_pct=data.get("buy_pct"),
        hold_pct=data.get("hold_pct"),
        sell_pct=data.get("sell_pct"),
        upside_to_target_pct=data.get("upside_to_target_pct"),
        fetched_at=data.get("fetched_at", ""),
    )


def _compute_fundamental_score(
    fv: Optional[FinvizFundamentals],
    tr: Optional[TipRanksData],
) -> tuple[float, dict]:
    """
    Compute a -1.0 to +1.0 fundamental score from real data.

    Scoring components and weights:
      Valuation (P/E vs benchmark)     0.20 -> 0.25
      Growth (EPS / Sales trajectory)  0.20 -> 0.25
      Profitability (margins, ROE)      0.15 -> 0.25
      Financial health (debt, ratios)   0.10 -> 0.15
      Insider sentiment                 0.10
      Analyst consensus (TipRanks)      0.15 -> 0
      Smart Score (TipRanks)            0.10 -> 0
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
        weights["valuation"] = 0.25

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
        weights["growth"] = 0.25

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
        weights["profitability"] = 0.25

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
        weights["health"] = 0.15

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
        weights["analyst_consensus"] = 0.0

    # --- Smart Score (TipRanks) ---
    if tr and tr.smart_score is not None:
        # Smart Score 1-10 → normalize to -1.0 to +1.0
        ss = (tr.smart_score - 5.5) / 4.5
        components["smart_score"] = round(ss, 4)
        weights["smart_score"] = 0.0

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