"""Async cache wrapper for fetch_earnings_quality."""
import json
import logging
from typing import Optional
from dataclasses import asdict

from backend.data.earnings_quality_data import (
    fetch_earnings_quality, EarningsQuality,
    EARNINGS_QUALITY_TTL, QuarterlyPoint,
)
from backend.cache.redis_client import redis_client

logger = logging.getLogger(__name__)


async def get_earnings_quality(ticker: str) -> Optional[EarningsQuality]:
    """
    Async entry point. Checks Redis first, fetches via Yahoo quoteSummary on miss.
    Returns None on any failure — never raises.
    """
    cache_key = f"data:earnings_quality:{ticker.upper()}"

    try:
        cached = await redis_client.get_raw(cache_key)
        if cached:
            return _from_dict(json.loads(cached))
    except Exception as exc:
        logger.debug("earnings quality cache read error: %s", exc)

    try:
        # fetch_earnings_quality is now async — call directly
        result = await fetch_earnings_quality(ticker)
        if result:
            try:
                await redis_client.set_raw(
                    cache_key,
                    json.dumps(asdict(result), default=str),
                    ttl=EARNINGS_QUALITY_TTL,
                )
            except Exception as exc:
                logger.debug("earnings quality cache write error: %s", exc)
        return result
    except Exception as exc:
        logger.warning("get_earnings_quality failed for %s: %s", ticker, exc)
        return None


def _from_dict(data: dict) -> EarningsQuality:
    """Reconstruct EarningsQuality from cached JSON dict."""
    eq = EarningsQuality(ticker=data.get("ticker", ""))
    # Scalar fields
    for f in [
        "revenue_yoy_pct", "revenue_trend", "gross_margin_pct",
        "operating_margin_pct", "net_margin_pct", "margin_trend",
        "fcf_margin_pct", "fcf_to_net_income", "fcf_trend",
        "cash_billions", "total_debt_billions", "net_cash_billions",
        "current_ratio", "debt_to_equity", "cash_trend",
        "earnings_quality_score",
        "fetched_at", "source", "quality_components",
    ]:
        setattr(eq, f, data.get(f))

    # List fields
    eq.revenue_qtrs = [
        QuarterlyPoint(**p) for p in (data.get("revenue_qtrs") or [])
    ]
    eq.gross_margin_qtrs = [
        QuarterlyPoint(**p) for p in (data.get("gross_margin_qtrs") or [])
    ]
    eq.operating_margin_qtrs = [
        QuarterlyPoint(**p) for p in (data.get("operating_margin_qtrs") or [])
    ]
    eq.fcf_qtrs = [
        QuarterlyPoint(**p) for p in (data.get("fcf_qtrs") or [])
    ]
    return eq