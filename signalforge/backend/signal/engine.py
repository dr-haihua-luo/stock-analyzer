"""
Signal engine — three independent horizon-specific signals computed
from the same AnalysisState. Each has its own weighting, thresholds,
and confidence calculation appropriate to its time horizon.

SWING   (3-5 weeks): technical-heavy, sector rotation, near-term
                      catalysts (earnings proximity flag)
POSITION (6 months):  fundamentals/earnings-quality-heavy, macro,
                      institutional flow, relative valuation
DAY_TRADE (intraday): EXPERIMENTAL — built on DAILY bars only.
                      See module docstring warning below.
"""

import logging
from typing import Optional, Dict, Any
from datetime import datetime, timezone

from backend.signal.models import SignalOutput, ConfidenceBreakdown

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sector P/E benchmarks — rough, stable, widely-cited averages used for
# relative valuation without requiring a new data fetch. These are
# approximate long-run sector averages, not live data — update
# periodically if sector valuation regimes shift materially.
# ---------------------------------------------------------------------------
SECTOR_PE_BENCHMARKS = {
    "Technology":              28.0,
    "Financial":                14.0,
    "Energy":                    12.0,
    "Healthcare":                 20.0,
    "Industrial":                  20.0,
    "Consumer Discretionary":       22.0,
    "Consumer Staples":              21.0,
    "Materials":                      16.0,
    "Utilities":                       18.0,
    "Real Estate":                      17.0,
    "Communication Services":            19.0,
}


# ===========================================================================
# SWING SIGNAL — 3 to 5 week horizon
# ===========================================================================

SWING_WEIGHTS = {
    "technical":       0.45,   # RSI/MACD/BB/volume/MA trends — dominant
    "sector":          0.20,   # near-term sector rotation
    "market":          0.15,   # current vol regime, short-term macro
    "news_sentiment":  0.10,   # news/social tone over past ~10 days
    "fundamental":     0.10,   # light touch — not the point at this horizon
}
SWING_BUY_THRESHOLD  = 0.30
SWING_SELL_THRESHOLD = -0.30
SWING_HYSTERESIS      = 0.03

# Earnings date falling within this many trading days of "now" triggers
# an explicit warning flag on the swing signal — gap risk from an
# earnings print is categorically different from normal swing risk.
SWING_HORIZON_TRADING_DAYS = (15, 25)   # 3-5 weeks


def compute_swing_signal(state: Dict[str, Any], previous_signal: Optional[str] = None) -> dict:
    """
    3-5 week swing signal. Technical-dominant, light fundamental touch.
    Flags earnings-date proximity as a risk warning (does not change
    the signal direction, but materially changes risk and should be
    shown prominently).
    """
    market = state.get("market") or {}
    sector = state.get("sector") or {}
    stock  = state.get("stock") or {}

    if not (market and sector and stock):
        return _unavailable_signal("swing", "missing required analysis data")

    # News sentiment score proxy: derive a -1..1 score from the
    # stock's news_sentiment field already computed in stock_agent
    news_score = stock.get("news_sentiment", 0.0)
    if news_score is None:
        news_score = 0.0

    composite = (
        SWING_WEIGHTS["technical"]      * _score(stock.get("technical_score")) +
        SWING_WEIGHTS["sector"]         * _score(sector.get("sector_score")) +
        SWING_WEIGHTS["market"]         * _score(market.get("market_score")) +
        SWING_WEIGHTS["news_sentiment"] * _score(news_score) +
        SWING_WEIGHTS["fundamental"]    * _score(stock.get("fundamental_score"))
    )

    signal = _classify_with_hysteresis(
        composite, SWING_BUY_THRESHOLD, SWING_SELL_THRESHOLD,
        SWING_HYSTERESIS, previous_signal
    )
    confidence = min(abs(composite) / 0.8, 1.0)

    # Earnings proximity warning — uses next_earnings_date from earnings_quality
    # dataclass if available (dormant until Phase 2 adds earnings date data).
    earnings_warning = None
    eq = state.get("earnings_quality")
    if eq is not None:
        next_earnings = getattr(eq, "next_earnings_date", None)
        if next_earnings:
            days_out = _trading_days_until(next_earnings)
            if days_out is not None and SWING_HORIZON_TRADING_DAYS[0] <= days_out <= SWING_HORIZON_TRADING_DAYS[1]:
                earnings_warning = (
                    f"Earnings report expected in ~{days_out} trading days — "
                    f"falls within this swing window. Expect elevated gap risk "
                    f"around {next_earnings}."
                )
            elif days_out is not None and days_out < SWING_HORIZON_TRADING_DAYS[0]:
                earnings_warning = (
                    f"Earnings report expected in ~{days_out} trading days — "
                    f"BEFORE this swing trade would typically close. "
                    f"High gap risk if holding through the print."
                )

    return {
        "horizon":          "swing",
        "horizon_label":    "3-5 Week Swing",
        "signal":           signal,
        "confidence":       round(confidence, 3),
        "composite_score":  round(composite, 4),
        "earnings_warning": earnings_warning,
        "weights":          dict(SWING_WEIGHTS),
        "status":           "ok",
    }


# ===========================================================================
# POSITION SIGNAL — 6 month horizon
# ===========================================================================

POSITION_WEIGHTS = {
    "fundamental_blend": 0.40,   # fundamentals + earnings quality combined
    "market":            0.20,   # macro regime matters more here
    "sector":            0.15,   # sector cycle positioning
    "institutional":     0.15,   # institutional flow direction
    "technical":         0.10,   # light touch — noise at 6mo horizon
}
POSITION_BUY_THRESHOLD  = 0.30
POSITION_SELL_THRESHOLD = -0.30
POSITION_HYSTERESIS      = 0.03


def compute_position_signal(state: Dict[str, Any], previous_signal: Optional[str] = None) -> dict:
    """
    6-month position signal. Fundamentals/earnings-quality-dominant,
    with institutional flow and relative valuation. Technicals are a
    light touch — largely noise at this horizon.
    """
    market = state.get("market") or {}
    sector = state.get("sector") or {}
    stock  = state.get("stock") or {}
    eq     = state.get("earnings_quality")
    fund   = state.get("fundamentals")

    if not (market and sector and stock):
        return _unavailable_signal("position", "missing required analysis data")

    # Blend fundamental_score with earnings_quality_score if available
    eq_score = getattr(eq, "earnings_quality_score", None) if eq else None
    if eq_score is not None:
        fundamental_blend = (_score(stock.get("fundamental_score")) * 0.5) + (_score(eq_score) * 0.5)
    else:
        fundamental_blend = _score(stock.get("fundamental_score"))

    # Institutional flow component — reuse the institutional_flow
    # sub-score already computed inside _compute_fundamental_score()
    # (stored in score_components dict on FundamentalsResult).
    inst_score = 0.0
    if fund and getattr(fund, "score_components", None):
        inst_score = fund.score_components.get("institutional_flow", 0.0) or 0.0
        inst_score = _score(inst_score)

    composite = (
        POSITION_WEIGHTS["fundamental_blend"] * fundamental_blend +
        POSITION_WEIGHTS["market"]            * _score(market.get("market_score")) +
        POSITION_WEIGHTS["sector"]            * _score(sector.get("sector_score")) +
        POSITION_WEIGHTS["institutional"]     * inst_score +
        POSITION_WEIGHTS["technical"]         * _score(stock.get("technical_score"))
    )

    signal = _classify_with_hysteresis(
        composite, POSITION_BUY_THRESHOLD, POSITION_SELL_THRESHOLD,
        POSITION_HYSTERESIS, previous_signal
    )
    confidence = min(abs(composite) / 0.8, 1.0)

    # Relative valuation vs sector benchmark P/E
    relative_valuation = None
    pe = stock.get("pe_ratio")
    sector_name = sector.get("ticker_sector")
    if pe and pe > 0 and sector_name in SECTOR_PE_BENCHMARKS:
        benchmark = SECTOR_PE_BENCHMARKS[sector_name]
        pct_vs_benchmark = round((pe / benchmark - 1) * 100, 1)
        relative_valuation = {
            "pe_ratio":          round(pe, 1),
            "sector_benchmark":  benchmark,
            "pct_vs_benchmark":  pct_vs_benchmark,
            "label": (
                "cheap vs sector"      if pct_vs_benchmark < -15 else
                "rich vs sector"       if pct_vs_benchmark >  15 else
                "in line with sector"
            ),
        }

    return {
        "horizon":            "position",
        "horizon_label":      "6-Month Position",
        "signal":             signal,
        "confidence":         round(confidence, 3),
        "composite_score":    round(composite, 4),
        "relative_valuation": relative_valuation,
        "weights":            dict(POSITION_WEIGHTS),
        "status":             "ok",
    }


# ===========================================================================
# DAY TRADE SIGNAL — EXPERIMENTAL, Phase 2 placeholder
# ===========================================================================

DAY_TRADE_WEIGHTS = {
    "volatility_regime": 0.40,   # VIX regime — today's environment
    "mean_reversion":    0.40,   # RSI/BB extremes — bounce setups
    "volume":            0.20,   # volume trend
}
DAY_TRADE_BUY_THRESHOLD  = 0.35
DAY_TRADE_SELL_THRESHOLD = -0.35

DAY_TRADE_DISCLAIMER = (
    "EXPERIMENTAL: This signal is computed from DAILY bar data only — "
    "it has no access to intraday price action, order book depth, "
    "bid-ask spread, opening range, or options dealer positioning, "
    "all of which are standard inputs for genuine day-trade decisions. "
    "Treat this as a rough 'is today's setup stretched' indicator at "
    "best, NOT a substitute for real intraday analysis. See Phase 2."
)


def compute_day_trade_signal(state: Dict[str, Any]) -> dict:
    """
    EXPERIMENTAL day-trade proxy signal using only daily-bar-derived
    data (VIX regime, RSI/BB extremes, volume trend). This is
    explicitly a mean-reversion / 'is this stretched' proxy, not a
    genuine intraday signal. See DAY_TRADE_DISCLAIMER.
    """
    market = state.get("market") or {}
    stock  = state.get("stock") or {}

    if not (market and stock):
        return _unavailable_signal("day_trade", "missing required analysis data")

    # Volatility regime component — higher VIX = more intraday opportunity
    # (not direction, just "more movement expected today")
    # Note: market_agent uses "low"/"normal"/"high", not the spec's
    # "elevated"/"extreme" — using actual values here.
    vix_regime_score = {
        "low":    -0.3,
        "normal":  0.2,
        "high":    0.6,
    }.get(market.get("vix_regime"), 0.0)

    # Mean reversion component — extreme RSI/BB suggests a bounce setup
    # Oversold (low RSI, below lower BB) = bullish mean-reversion setup
    # Overbought (high RSI, above upper BB) = bearish mean-reversion setup
    mr_score = 0.0
    rsi = stock.get("rsi_14")
    if rsi is not None:
        if rsi < 30:
            mr_score += 0.5
        elif rsi > 70:
            mr_score -= 0.5
    bb_pos = stock.get("bb_position")
    if bb_pos == "below_lower":
        mr_score += 0.4
    elif bb_pos == "above_upper":
        mr_score -= 0.4
    mr_score = max(-1.0, min(1.0, mr_score))

    vol_score = {
        "increasing":  0.3,
        "decreasing": -0.2,
        "neutral":     0.0,
    }.get(stock.get("volume_trend"), 0.0)

    composite = (
        DAY_TRADE_WEIGHTS["volatility_regime"] * vix_regime_score +
        DAY_TRADE_WEIGHTS["mean_reversion"]     * mr_score +
        DAY_TRADE_WEIGHTS["volume"]              * vol_score
    )

    if composite >= DAY_TRADE_BUY_THRESHOLD:
        signal = "BUY"
    elif composite <= DAY_TRADE_SELL_THRESHOLD:
        signal = "SELL"
    else:
        signal = "HOLD"

    confidence = min(abs(composite) / 0.7, 1.0) * 0.6   # capped lower —
    # confidence deliberately scaled down for this experimental signal;
    # never show high confidence on a signal this data-starved

    return {
        "horizon":           "day_trade",
        "horizon_label":     "Day Trade (Experimental)",
        "signal":            signal,
        "confidence":        round(confidence, 3),
        "composite_score":   round(composite, 4),
        "disclaimer":        DAY_TRADE_DISCLAIMER,
        "weights":           dict(DAY_TRADE_WEIGHTS),
        "status":            "experimental",
    }


# ===========================================================================
# Shared helpers
# ===========================================================================

def _score(val: Optional[float]) -> float:
    """Safely coerce a value to float, defaulting to 0.0."""
    if val is None:
        return 0.0
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0


def _classify_with_hysteresis(
    composite: float, buy_th: float, sell_th: float,
    hysteresis: float, previous_signal: Optional[str],
) -> str:
    """
    Classify a composite score into BUY/SELL/HOLD using one-sided
    hysteresis to reduce signal flip-rate near thresholds.
    """
    if previous_signal == "BUY":
        if composite >= buy_th - hysteresis:
            return "BUY"
        return "SELL" if composite <= sell_th else "HOLD"
    if previous_signal == "SELL":
        if composite <= sell_th + hysteresis:
            return "SELL"
        return "BUY" if composite >= buy_th else "HOLD"
    # No previous signal, or previous was HOLD — use plain thresholds
    if composite >= buy_th:
        return "BUY"
    if composite <= sell_th:
        return "SELL"
    return "HOLD"


def _unavailable_signal(horizon: str, reason: str) -> dict:
    """Return a standardized 'unavailable' result for a horizon."""
    return {
        "horizon":         horizon,
        "horizon_label":   horizon.replace("_", " ").title(),
        "signal":          None,
        "confidence":      None,
        "composite_score": None,
        "status":          "unavailable",
        "reason":          reason,
    }


def _trading_days_until(date_str: str) -> Optional[int]:
    """Rough trading-day count from today to a YYYY-MM-DD date string."""
    try:
        target = datetime.strptime(date_str[:10], "%Y-%m-%d").date()
        today  = datetime.now(timezone.utc).date()
        calendar_days = (target - today).days
        if calendar_days < 0:
            return None
        return round(calendar_days * 5 / 7)   # rough weekday approximation
    except Exception:
        return None


# ===========================================================================
# Top-level entry point — computes all three signals
# ===========================================================================

def compute_all_signals(
    state: Dict[str, Any],
    previous_swing_signal: Optional[str] = None,
    previous_position_signal: Optional[str] = None,
) -> dict:
    """
    Computes swing, position, and day_trade signals from one AnalysisState.
    Returns {"swing": {...}, "position": {...}, "day_trade": {...}}
    """
    return {
        "swing":     compute_swing_signal(state, previous_swing_signal),
        "position":  compute_position_signal(state, previous_position_signal),
        "day_trade": compute_day_trade_signal(state),
    }


# ===========================================================================
# Backward-compatible wrapper
# ===========================================================================

class SignalEngine:
    """
    DEPRECATED — kept for backward compatibility. New code should call
    compute_all_signals() directly. The generate_signal() method now
    delegates to compute_all_signals() and returns the position signal
    (6-month horizon) as the primary signal_output, since the
    overall_analysis_agent produces a 6-month outlook.
    """

    def __init__(self):
        self.weights = {
            "market": 0.2,
            "sector": 0.3,
            "stock": 0.5,
        }

    @staticmethod
    def compute_signal(
        state: Dict[str, Any],
        previous_signal: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        DEPRECATED — delegates to compute_swing_signal for backward compat.
        """
        return compute_swing_signal(state, previous_signal)

    async def generate_signal(
        self,
        market_data: Optional[Dict[str, Any]],
        sector_data: Optional[Dict[str, Any]],
        stock_data: Optional[Dict[str, Any]],
        analysis_results: Optional[Dict[str, Any]],
        ticker: str,
        previous_signal: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        DEPRECATED — delegates to compute_all_signals. Returns the
        position signal as signal_output (6-month outlook alignment)
        plus a confidence_breakdown derived from the position weights.
        """
        try:
            logger.info(f"Generating signal for {ticker}")

            market = analysis_results.get("market", {}) if analysis_results else {}
            sector = analysis_results.get("sector", {}) if analysis_results else {}
            stock  = stock_data or {}

            engine_state = {
                "ticker": ticker,
                "market": market,
                "sector": sector,
                "stock": stock,
                "fundamentals": None,
                "earnings_quality": None,
            }

            all_signals = compute_all_signals(
                engine_state,
                previous_swing_signal=previous_signal,
                previous_position_signal=previous_signal,
            )

            position = all_signals.get("position", {})
            signal = position.get("signal", "HOLD")
            confidence = position.get("confidence", 0.0)
            composite_score = position.get("composite_score", 0.0)

            confidence_breakdown = ConfidenceBreakdown(
                market_contribution=_score(market.get("market_score")),
                sector_contribution=_score(sector.get("sector_score")),
                technical_contribution=_score(stock.get("technical_score")),
                fundamental_contribution=_score(stock.get("fundamental_score")),
            )

            signal_output = SignalOutput(
                ticker=ticker,
                signal=signal,
                confidence=confidence or 0.0,
                composite_score=composite_score or 0.0,
                timestamp=datetime.utcnow(),
            )

            result = {
                "signal_output": signal_output.model_dump(),
                "confidence_breakdown": confidence_breakdown.model_dump(),
            }

            logger.info(
                f"Generated signal for {ticker}: {signal} "
                f"with confidence {confidence or 0.0:.3f}"
            )
            return result

        except Exception as e:
            logger.error(f"Error generating signal for {ticker}: {e}")
            neutral_signal = SignalOutput(
                ticker=ticker,
                signal="HOLD",
                confidence=0.0,
                composite_score=0.0,
                timestamp=datetime.utcnow(),
            )
            neutral_breakdown = ConfidenceBreakdown(
                market_contribution=0.0,
                sector_contribution=0.0,
                technical_contribution=0.0,
                fundamental_contribution=0.0,
            )
            return {
                "signal_output": neutral_signal.model_dump(),
                "confidence_breakdown": neutral_breakdown.model_dump(),
            }

    def _extract_signal_from_analysis(self, analysis: Dict[str, Any]) -> tuple[str, float]:
        """
        Extract a signal direction and strength from analysis text.
        Returns: (signal_direction, strength) where signal_direction is BUY/SELL/HOLD and strength is 0.0-1.0
        """
        if not analysis or not isinstance(analysis, dict):
            return "HOLD", 0.5

        # Combine all analysis text for keyword matching
        analysis_text = ""
        if isinstance(analysis, dict):
            for key, value in analysis.items():
                if isinstance(value, str):
                    analysis_text += " " + value.lower()
                elif isinstance(value, dict):
                    for k, v in value.items():
                        if isinstance(v, str):
                            analysis_text += " " + v.lower()

        # Bullish/bearish keywords
        bullish_keywords = [
            "bullish", "positive", "optimistic", "upward", "gain", "strength",
            "buy", "accumulate", "overweight", "expansion", "growth", "momentum"
        ]

        bearish_keywords = [
            "bearish", "negative", "pessimistic", "downward", "loss", "weakness",
            "sell", "reduce", "underweight", "contraction", "decline", "correction"
        ]

        # Count keyword matches
        bullish_count = sum(1 for keyword in bullish_keywords if keyword in analysis_text)
        bearish_count = sum(1 for keyword in bearish_keywords if keyword in analysis_text)

        # Determine signal based on keyword balance
        total_keywords = bullish_count + bearish_count
        if total_keywords == 0:
            return "HOLD", 0.5  # Neutral if no clear signals

        bullish_ratio = bullish_count / total_keywords if total_keywords > 0 else 0.5

        if bullish_ratio > 0.6:
            signal = "BUY"
            confidence = 0.5 + (bullish_ratio - 0.5)  # Scale to 0.5-1.0 range
        elif bullish_ratio < 0.4:
            signal = "SELL"
            confidence = 0.5 + ((0.5 - bullish_ratio) / 0.5) * 0.5  # Scale to 0.5-1.0 range
        else:
            signal = "HOLD"
            confidence = 0.5  # Neutral confidence

        return signal, min(max(confidence, 0.0), 1.0)  # Clamp to 0-1 range
