"""
Earnings quality data via Financial Modeling Prep (FMP) free API.

FMP is a proper REST API: API key in query param, no cookie/crumb/
session management required. curl_cffi with Chrome impersonation
is used for all requests consistent with the rest of the project.

Free tier: 250 calls/day — sufficient for personal use.
This module makes 5 calls per ticker analysis (cached for 4 hours,
so each ticker only costs 5 calls per 4-hour window).

Sign up: https://financialmodelingprep.com/developer/docs
Redis TTL: 4 hours (data changes only at earnings releases).
Cache key: "data:earnings_quality:{TICKER}"
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from curl_cffi.requests import AsyncSession

logger = logging.getLogger(__name__)

EARNINGS_QUALITY_TTL = 14400   # 4 hours
FMP_BASE = "https://financialmodelingprep.com/stable"
TIMEOUT = 12.0


# ---------------------------------------------------------------------------
# Data classes (unchanged from previous version)
# ---------------------------------------------------------------------------

@dataclass
class QuarterlyPoint:
    period: str
    value: Optional[float]


@dataclass
class EarningsSurprise:
    period: str
    eps_estimate: Optional[float]
    eps_actual: Optional[float]
    surprise_pct: Optional[float]


@dataclass
class EarningsQuality:
    ticker: str
    revenue_qtrs: list = field(default_factory=list)
    revenue_yoy_pct: Optional[float] = None
    revenue_trend: Optional[str] = None
    gross_margin_pct: Optional[float] = None
    operating_margin_pct: Optional[float] = None
    net_margin_pct: Optional[float] = None
    gross_margin_qtrs: list = field(default_factory=list)
    operating_margin_qtrs: list = field(default_factory=list)
    margin_trend: Optional[str] = None
    fcf_qtrs: list = field(default_factory=list)
    fcf_margin_pct: Optional[float] = None
    fcf_to_net_income: Optional[float] = None
    fcf_trend: Optional[str] = None
    cash_billions: Optional[float] = None
    total_debt_billions: Optional[float] = None
    net_cash_billions: Optional[float] = None
    current_ratio: Optional[float] = None
    debt_to_equity: Optional[float] = None
    cash_trend: Optional[str] = None
    surprise_history: list = field(default_factory=list)
    avg_surprise_pct: Optional[float] = None
    beat_streak: Optional[int] = None
    next_earnings_date: Optional[str] = None
    guidance_signal: Optional[str] = None
    earnings_quality_score: Optional[float] = None
    quality_components: dict = field(default_factory=dict)
    fetched_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    source: str = "fmp"


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def fetch_earnings_quality(ticker: str) -> Optional[EarningsQuality]:
    """
    Fetch all earnings quality data from FMP free API.
    Makes 5 concurrent HTTP calls. Returns None on complete failure.
    Never raises.
    """
    from backend.config import settings
    api_key = settings.FMP_API_KEY

    if not api_key or api_key.startswith("your_"):
        logger.debug(
            "FMP_API_KEY not set — earnings quality unavailable. "
            "Sign up free at https://financialmodelingprep.com/developer/docs"
        )
        return None

    ticker = ticker.upper()
    eq = EarningsQuality(ticker=ticker)

    try:
        import asyncio

        async with AsyncSession(impersonate="chrome", timeout=TIMEOUT) as session:
            (
                income_data,
                cashflow_data,
                balance_data,
                surprise_data,
                calendar_data,
                estimates_data,
            ) = await asyncio.gather(
                _get(session, f"{FMP_BASE}/income-statement?symbol={ticker}",
                     {"period": "quarter", "limit": 5, "apikey": api_key}),
                _get(session, f"{FMP_BASE}/cash-flow-statement?symbol={ticker}",
                     {"period": "quarter", "limit": 5, "apikey": api_key}),
                _get(session, f"{FMP_BASE}/balance-sheet-statement?symbol={ticker}",
                     {"period": "quarter", "limit": 5, "apikey": api_key}),
                _get(session, f"{FMP_BASE}/earnings-surprises?symbol={ticker}",
                     {"apikey": api_key}),
                _get(session, f"{FMP_BASE}/historical/earning_calendar?symbol={ticker}",
                     {"limit": 5, "apikey": api_key}),
                _get(session, f"{FMP_BASE}/analyst-estimates?symbol={ticker}",
                     {"period": "quarter", "limit": 4, "apikey": api_key}),
                return_exceptions=True,
            )

        _parse_income(income_data, eq)
        _parse_cashflow(cashflow_data, income_data, eq)
        _parse_balance_sheet(balance_data, eq)
        _parse_surprises(surprise_data, eq)
        _parse_calendar(calendar_data, eq)
        _parse_estimates(estimates_data, eq)
        _compute_quality_score(eq)

        logger.info(
            "EarningsQuality (FMP) for %s: score=%s revenue_qtrs=%d",
            ticker, eq.earnings_quality_score, len(eq.revenue_qtrs)
        )
        return eq

    except Exception as exc:
        logger.warning("fetch_earnings_quality failed for %s: %s", ticker, exc)
        return None


# ---------------------------------------------------------------------------
# HTTP helper
# ---------------------------------------------------------------------------

async def _get(session: AsyncSession, url: str, params: dict):
    """Single GET call. Returns parsed JSON list/dict or [] on error."""
    try:
        logger.info("calling %s ", url)
        resp = await session.get(url, params=params)
        if resp.status_code == 401:
            logger.error("FMP: 401 Unauthorized — check FMP_API_KEY")
            return []
        if resp.status_code == 403:
            logger.error("FMP: 403 Forbidden — free tier limit may be exceeded")
            return []
        if resp.status_code == 429:
            logger.error("FMP: 429 rate limited — 250 calls/day free tier")
            return []
        if resp.status_code != 200:
            logger.error("FMP: status %s for %s", resp.status_code, url)
            return []
        data = resp.json()
        logger.info("%s returned data is: %s", url, len(data))
        if isinstance(data, dict) and "Error Message" in data:
            logger.error("FMP error: %s", data["Error Message"])
            return []
        return data if isinstance(data, list) else []
    except Exception as exc:
        logger.error("FMP _get error (%s): %s", url, exc)
        return []


# ---------------------------------------------------------------------------
# Income statement parser
# ---------------------------------------------------------------------------

def _parse_income(data: list, eq: EarningsQuality) -> None:
    if not data:
        return
    try:
        rev_vals, gm_vals, om_vals = [], [], []

        for item in data[:4]:
            date = str(item.get("date", ""))[:7]
            rev = item.get("revenue")
            gp = item.get("grossProfit")
            oi = item.get("operatingIncome")
            ni = item.get("netIncome")
            gm_r = item.get("grossProfitRatio")
            om_r = item.get("operatingIncomeRatio")

            if rev and rev != 0:
                rev_vals.append(QuarterlyPoint(date, round(rev / 1e9, 3)))
            if gm_r is not None:
                gm_vals.append(QuarterlyPoint(date, round(gm_r * 100, 2)))
            if om_r is not None:
                om_vals.append(QuarterlyPoint(date, round(om_r * 100, 2)))

        eq.revenue_qtrs = list(reversed(rev_vals))
        eq.gross_margin_qtrs = list(reversed(gm_vals))
        eq.operating_margin_qtrs = list(reversed(om_vals))

        if eq.gross_margin_qtrs:
            eq.gross_margin_pct = eq.gross_margin_qtrs[-1].value
        if eq.operating_margin_qtrs:
            eq.operating_margin_pct = eq.operating_margin_qtrs[-1].value

        ni_r = data[0].get("netIncomeRatio")
        if ni_r is not None:
            eq.net_margin_pct = round(ni_r * 100, 2)

        if len(data) >= 5:
            r0 = data[0].get("revenue")
            r4 = data[4].get("revenue")
            if r0 and r4 and r4 != 0:
                eq.revenue_yoy_pct = round((r0 / r4 - 1) * 100, 2)
        elif len(data) >= 4:
            r0 = data[0].get("revenue")
            r3 = data[3].get("revenue")
            if r0 and r3 and r3 != 0:
                eq.revenue_yoy_pct = round((r0 / r3 - 1) * 100, 2)

        rv = eq.revenue_qtrs
        if len(rv) >= 3 and rv[-2].value and rv[-3].value and rv[-2].value != 0:
            g1 = (rv[-1].value / rv[-2].value - 1) if rv[-1].value else None
            g2 = rv[-2].value / rv[-3].value - 1
            if g1 is not None:
                eq.revenue_trend = (
                    "accelerating" if g1 > g2 * 1.05 else
                    "decelerating" if g1 < g2 * 0.95 else
                    "stable"
                )

        gm = eq.gross_margin_qtrs
        if len(gm) >= 4 and gm[0].value and gm[-1].value:
            eq.margin_trend = (
                "expanding" if gm[-1].value > gm[0].value + 0.5 else
                "contracting" if gm[-1].value < gm[0].value - 0.5 else
                "stable"
            )

    except Exception as exc:
        logger.debug("income parse skip: %s", exc)


# ---------------------------------------------------------------------------
# Cash flow parser
# ---------------------------------------------------------------------------

def _parse_cashflow(cf_data: list, inc_data: list, eq: EarningsQuality) -> None:
    if not cf_data:
        return
    try:
        rev_map = {qp.period: qp.value for qp in eq.revenue_qtrs}
        fcf_vals = []
        ni_latest = None

        for item in cf_data[:4]:
            date = str(item.get("date", ""))[:7]
            fcf = item.get("freeCashFlow")
            ocf = item.get("operatingCashFlow")
            capex = item.get("capitalExpenditure")
            ni = item.get("netIncome")

            val = fcf if fcf is not None else (
                (ocf + capex) if (ocf is not None and capex is not None) else None
            )
            if val is not None:
                fcf_vals.append(QuarterlyPoint(date, round(val / 1e9, 3)))

            if ni_latest is None and ni is not None:
                ni_latest = ni

        eq.fcf_qtrs = list(reversed(fcf_vals))

        if eq.fcf_qtrs:
            latest_fcf = eq.fcf_qtrs[-1].value
            latest_label = eq.fcf_qtrs[-1].period
            latest_rev = rev_map.get(latest_label)
            if latest_rev and latest_rev != 0:
                eq.fcf_margin_pct = round(latest_fcf / latest_rev * 100, 2)

        if eq.fcf_qtrs and ni_latest and ni_latest != 0:
            eq.fcf_to_net_income = round(
                eq.fcf_qtrs[-1].value * 1e9 / ni_latest, 3
            )

        fv = eq.fcf_qtrs
        if len(fv) >= 3 and fv[-3].value and fv[-1].value:
            eq.fcf_trend = (
                "improving" if fv[-1].value > fv[-3].value else
                "deteriorating" if fv[-1].value < fv[-3].value else
                "stable"
            )

    except Exception as exc:
        logger.debug("cashflow parse skip: %s", exc)


# ---------------------------------------------------------------------------
# Balance sheet parser
# ---------------------------------------------------------------------------

def _parse_balance_sheet(data: list, eq: EarningsQuality) -> None:
    if not data:
        return
    try:
        most_recent = data[0]

        cash = (most_recent.get("cashAndCashEquivalents") or
                most_recent.get("cashAndShortTermInvestments"))
        debt = most_recent.get("totalDebt")
        ca = most_recent.get("totalCurrentAssets")
        cl = most_recent.get("totalCurrentLiabilities")
        equity = most_recent.get("totalStockholdersEquity")

        if cash is not None:
            eq.cash_billions = round(cash / 1e9, 3)
        if debt is not None:
            eq.total_debt_billions = round(debt / 1e9, 3)
        if cash is not None and debt is not None:
            eq.net_cash_billions = round((cash - debt) / 1e9, 3)
        if ca and cl and cl != 0:
            eq.current_ratio = round(ca / cl, 3)
        if debt and equity and equity != 0:
            eq.debt_to_equity = round(debt / equity, 3)

        if len(data) >= 4:
            cash_old = (data[3].get("cashAndCashEquivalents") or
                        data[3].get("cashAndShortTermInvestments"))
            if cash and cash_old and cash_old != 0:
                eq.cash_trend = (
                    "growing" if cash > cash_old * 1.05 else
                    "shrinking" if cash < cash_old * 0.95 else
                    "stable"
                )

    except Exception as exc:
        logger.debug("balance sheet parse skip: %s", exc)


# ---------------------------------------------------------------------------
# Earnings surprises
# ---------------------------------------------------------------------------

def _parse_surprises(data: list, eq: EarningsQuality) -> None:
    if not data:
        return
    try:
        surprises = []
        for item in data[:4]:
            date = str(item.get("date", ""))[:10]
            est = item.get("estimatedEarning")
            act = item.get("actualEarningResult")
            surp = None
            if est is not None and act is not None and est != 0:
                surp = round((act - est) / abs(est) * 100, 2)
            surprises.append(EarningsSurprise(
                period=date,
                eps_estimate=round(float(est), 3) if est is not None else None,
                eps_actual=round(float(act), 3) if act is not None else None,
                surprise_pct=surp,
            ))

        eq.surprise_history = surprises

        valid = [s.surprise_pct for s in surprises if s.surprise_pct is not None]
        if valid:
            eq.avg_surprise_pct = round(sum(valid) / len(valid), 2)

        streak = 0
        for s in surprises:
            if s.surprise_pct is None:
                break
            if s.surprise_pct > 0:
                streak = streak + 1 if streak >= 0 else 0
                if streak == 0:
                    break
            else:
                streak = streak - 1 if streak <= 0 else 0
                if streak == 0:
                    break
        eq.beat_streak = streak

    except Exception as exc:
        logger.debug("surprise parse skip: %s", exc)


# ---------------------------------------------------------------------------
# Next earnings date
# ---------------------------------------------------------------------------

def _parse_calendar(data: list, eq: EarningsQuality) -> None:
    if not data:
        return
    try:
        today = datetime.now(timezone.utc).date()
        for item in data:
            date_str = str(item.get("date", ""))[:10]
            try:
                d = datetime.strptime(date_str, "%Y-%m-%d").date()
                if d >= today:
                    eq.next_earnings_date = date_str
                    break
            except Exception:
                continue
    except Exception as exc:
        logger.debug("calendar parse skip: %s", exc)


# ---------------------------------------------------------------------------
# Analyst estimates → guidance proxy
# ---------------------------------------------------------------------------

def _parse_estimates(data: list, eq: EarningsQuality) -> None:
    if not data or len(data) < 2:
        eq.guidance_signal = "unavailable"
        return
    try:
        current_eps = data[0].get("estimatedEpsAvg")
        previous_eps = data[1].get("estimatedEpsAvg")

        if current_eps is None or previous_eps is None or previous_eps == 0:
            eq.guidance_signal = "unavailable"
            return

        change_pct = (current_eps - previous_eps) / abs(previous_eps) * 100
        eq.guidance_signal = (
            "raised" if change_pct > 2.0 else
            "cut" if change_pct < -2.0 else
            "neutral"
        )

    except Exception as exc:
        logger.debug("estimates parse skip: %s", exc)
        eq.guidance_signal = "unavailable"


# ---------------------------------------------------------------------------
# Composite earnings quality score
# ---------------------------------------------------------------------------

def _compute_quality_score(eq: EarningsQuality) -> None:
    components = {}
    weights = {}

    if eq.revenue_yoy_pct is not None:
        s = max(-1.0, min(1.0, (eq.revenue_yoy_pct - 5) / 20))
        if eq.revenue_trend == "accelerating":
            s = min(1.0, s + 0.15)
        elif eq.revenue_trend == "decelerating":
            s = max(-1.0, s - 0.15)
        components["revenue_growth"] = round(s, 4)
        weights["revenue_growth"] = 0.20

    if eq.gross_margin_pct is not None:
        s = max(-1.0, min(1.0, (eq.gross_margin_pct - 30) / 30))
        if eq.margin_trend == "expanding":
            s = min(1.0, s + 0.20)
        elif eq.margin_trend == "contracting":
            s = max(-1.0, s - 0.20)
        components["margin_quality"] = round(s, 4)
        weights["margin_quality"] = 0.20

    if eq.fcf_margin_pct is not None:
        s = max(-1.0, min(1.0, (eq.fcf_margin_pct - 5) / 15))
        if eq.fcf_to_net_income is not None:
            s = min(1.0, s + 0.20) if eq.fcf_to_net_income > 1.1 \
                else max(-1.0, s - 0.20) if eq.fcf_to_net_income < 0.5 \
                else s
        components["fcf_quality"] = round(s, 4)
        weights["fcf_quality"] = 0.20

    bs_signals = []
    if eq.net_cash_billions is not None:
        bs_signals.append(0.4 if eq.net_cash_billions > 0 else -0.4)
    if eq.current_ratio is not None:
        bs_signals.append(max(-0.3, min(0.3, (eq.current_ratio - 1.5) / 2)))
    if eq.debt_to_equity is not None:
        bs_signals.append(max(-0.3, min(0.3, (1.0 - eq.debt_to_equity) / 1.5)))
    if bs_signals:
        components["balance_sheet"] = round(sum(bs_signals) / len(bs_signals), 4)
        weights["balance_sheet"] = 0.15

    if eq.avg_surprise_pct is not None:
        s = max(-1.0, min(1.0, eq.avg_surprise_pct / 10))
        if eq.beat_streak and eq.beat_streak >= 3:
            s = min(1.0, s + 0.15)
        elif eq.beat_streak and eq.beat_streak <= -2:
            s = max(-1.0, s - 0.15)
        components["earnings_surprise"] = round(s, 4)
        weights["earnings_surprise"] = 0.15

    guidance_map = {"raised": 0.8, "neutral": 0.0, "cut": -0.8}
    if eq.guidance_signal in guidance_map:
        components["guidance"] = guidance_map[eq.guidance_signal]
        weights["guidance"] = 0.10

    if not weights:
        return

    total_w = sum(weights.values())
    score = sum(components[k] * (weights[k] / total_w) for k in components)
    eq.earnings_quality_score = round(max(-1.0, min(1.0, score)), 4)
    components["_coverage"] = round(total_w, 4)
    components["_score"] = eq.earnings_quality_score
    eq.quality_components = components