"""
FinViz fundamental data via finvizfinance package.

Uses curl_cffi session monkey-patching to bypass Cloudflare TLS
fingerprinting. finvizfinance uses requests internally; patching
requests.Session inside the thread pool function routes finvizfinance HTTP
calls through curl_cffi's Chrome-impersonating session without affecting
other modules that use requests.Session.mount().

No API key required. Rate limit: be respectful — cache aggressively.
Redis TTL for fundamentals: 4 hours (data changes slowly intraday).
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime, timezone
import json

logger = logging.getLogger(__name__)


@dataclass
class FinvizFundamentals:
    ticker: str
    # Valuation
    pe_ratio: Optional[float]
    forward_pe: Optional[float]
    peg_ratio: Optional[float]
    ps_ratio: Optional[float]
    pb_ratio: Optional[float]
    price_to_fcf: Optional[float]
    # Growth
    eps_ttm: Optional[float]
    eps_next_year: Optional[float]
    eps_next_5y_pct: Optional[float]   # e.g. 15.2 means 15.2% per year
    eps_past_5y_pct: Optional[float]
    sales_past_5y_pct: Optional[float]
    # Profitability
    gross_margin_pct: Optional[float]
    oper_margin_pct: Optional[float]
    profit_margin_pct: Optional[float]
    roa_pct: Optional[float]
    roe_pct: Optional[float]
    roi_pct: Optional[float]
    # Financial health
    debt_to_equity: Optional[float]
    current_ratio: Optional[float]
    quick_ratio: Optional[float]
    # Ownership
    insider_own_pct: Optional[float]
    insider_trans_pct: Optional[float]
    inst_own_pct: Optional[float]
    short_float_pct: Optional[float]
    # Market
    market_cap_billions: Optional[float]
    beta: Optional[float]
    # Insider activity (derived)
    net_insider_sentiment: Optional[float]  # -1.0 to +1.0
    insider_buys_90d: Optional[int]
    insider_sells_90d: Optional[int]
    # Recent analyst actions from FinViz outer ratings
    recent_analyst_actions: list = field(default_factory=list)
    # Meta
    fetched_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    source: str = "finviz"


def _parse_pct(val: Optional[str]) -> Optional[float]:
    """Parse '15.20%' → 15.20. Returns None for '-' or invalid."""
    if not val or val == "-":
        return None
    try:
        return float(str(val).replace("%", "").replace(",", "").strip())
    except (ValueError, TypeError):
        return None


def _parse_float(val: Optional[str]) -> Optional[float]:
    """Parse '34.26' or '2.5B' → float. Returns None for '-'."""
    if not val or val == "-":
        return None
    try:
        s = str(val).replace(",", "").strip()
        if s.endswith("B"):
            return float(s[:-1]) * 1e9
        if s.endswith("M"):
            return float(s[:-1]) * 1e6
        if s.endswith("K"):
            return float(s[:-1]) * 1e3
        return float(s)
    except (ValueError, TypeError):
        return None


def _parse_market_cap_billions(val: Optional[str]) -> Optional[float]:
    """Parse '2.93T' → 2930.0, '302.10B' → 302.10, '45.2M' → 0.045"""
    if not val or val == "-":
        return None
    try:
        s = str(val).replace(",", "").strip()
        if s.endswith("T"):
            return float(s[:-1]) * 1000
        if s.endswith("B"):
            return float(s[:-1])
        if s.endswith("M"):
            return float(s[:-1]) / 1000
        return float(s) / 1e9
    except (ValueError, TypeError):
        return None


async def fetch_finviz_fundamentals(ticker: str) -> Optional[FinvizFundamentals]:
    """
    Async wrapper around synchronous finvizfinance calls.
    Runs blocking finvizfinance in a thread pool to avoid blocking the
    FastAPI event loop.

    Returns None on any failure — caller must handle gracefully.
    Redis TTL: 4 hours.
    """
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, _fetch_finviz_sync, ticker)
        return result
    except Exception as exc:
        logger.warning("finviz fetch failed for %s: %s", ticker, exc)
        return None


def _fetch_finviz_sync(ticker: str) -> Optional[FinvizFundamentals]:
    """
    Synchronous finvizfinance calls — must run in thread pool.
    Applies curl_cffi patch inside this thread to avoid affecting other modules.
    """
    # Import and apply patch inside thread to avoid interfering with main thread
    import requests as requests_lib
    try:
        from curl_cffi import requests as cffi_requests
        # Only patch for finvizfinance calls
        original_session = requests_lib.Session
        requests_lib.Session = cffi_requests.Session
    except ImportError:
        logger.warning(
            "curl_cffi not available — finvizfinance may get 403 from Cloudflare"
        )
        original_session = None

    try:
        from finvizfinance.quote import finvizfinance

        logger.info("Calling FinVizFinance to scrape fundamental data for %s", ticker)
        stock = finvizfinance(ticker)
        fund = stock.ticker_fundament()
        logger.info("Returned from FinVizFinance for %s", fund)

        # Insider trading
        net_sentiment = None
        buys_90d = 0
        sells_90d = 0
        try:
            insider_df = stock.ticker_inside_trader()
            if insider_df is not None and not insider_df.empty:
                recent = insider_df.copy()
                recent_buys = recent[
                    recent.get("Transaction", recent.get("Relationship", "")).str
                    .contains("Buy|Purchase", case=False, na=False)
                ]
                recent_sells = recent[
                    recent.get("Transaction", recent.get("Relationship", "")).str
                    .contains("Sale|Sell", case=False, na=False)
                ]
                buys_90d = len(recent_buys)
                sells_90d = len(recent_sells)
                total = buys_90d + sells_90d
                if total > 0:
                    net_sentiment = round((buys_90d - sells_90d) / total, 4)
        except Exception as e:
            logger.debug("insider_trader parse error for %s: %s", ticker, e)

        # Outer ratings (analyst actions from FinViz)
        recent_actions = []
        try:
            ratings_df = stock.ticker_outer_ratings()
            if ratings_df is not None and not ratings_df.empty:
                for _, row in ratings_df.head(5).iterrows():
                    recent_actions.append({
                        "date": str(row.get("Date", "")),
                        "status": str(row.get("Status", "")),
                        "firm": str(row.get("Outer Rating", row.get("Firm", ""))),
                        "target": str(row.get("Price Target", "")),
                    })
        except Exception as e:
            logger.error("outer_ratings parse error for %s: %s", ticker, e)

        return FinvizFundamentals(
            ticker=ticker,
            pe_ratio=_parse_float(fund.get("P/E")),
            forward_pe=_parse_float(fund.get("Forward P/E")),
            peg_ratio=_parse_float(fund.get("PEG")),
            ps_ratio=_parse_float(fund.get("P/S")),
            pb_ratio=_parse_float(fund.get("P/B")),
            price_to_fcf=_parse_float(fund.get("P/FCF")),
            eps_ttm=_parse_float(fund.get("EPS (ttm)")),
            eps_next_year=_parse_float(fund.get("EPS next Y")),
            eps_next_5y_pct=_parse_pct(fund.get("EPS next 5Y")),
            eps_past_5y_pct=_parse_pct(fund.get("EPS past 5Y")),
            sales_past_5y_pct=_parse_pct(fund.get("Sales past 5Y")),
            gross_margin_pct=_parse_pct(fund.get("Gross Margin")),
            oper_margin_pct=_parse_pct(fund.get("Oper. Margin")),
            profit_margin_pct=_parse_pct(fund.get("Profit Margin")),
            roa_pct=_parse_pct(fund.get("ROA")),
            roe_pct=_parse_pct(fund.get("ROE")),
            roi_pct=_parse_pct(fund.get("ROI")),
            debt_to_equity=_parse_float(fund.get("Debt/Eq")),
            current_ratio=_parse_float(fund.get("Current Ratio")),
            quick_ratio=_parse_float(fund.get("Quick Ratio")),
            insider_own_pct=_parse_pct(fund.get("Insider Own")),
            insider_trans_pct=_parse_pct(fund.get("Insider Trans")),
            inst_own_pct=_parse_pct(fund.get("Inst Own")),
            short_float_pct=_parse_pct(fund.get("Short Float")),
            market_cap_billions=_parse_market_cap_billions(fund.get("Market Cap")),
            beta=_parse_float(fund.get("Beta")),
            net_insider_sentiment=net_sentiment,
            insider_buys_90d=buys_90d,
            insider_sells_90d=sells_90d,
            recent_analyst_actions=recent_actions,
        )

    except Exception as exc:
        logger.warning("_fetch_finviz_sync failed for %s: %s", ticker, exc)
        return None
    finally:
        # Restore original Session to avoid affecting other code
        if original_session is not None:
            requests_lib.Session = original_session