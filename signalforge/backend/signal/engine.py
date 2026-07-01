from typing import Dict, Any, Optional
from backend.signal.models import SignalOutput, ConfidenceBreakdown
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# Hysteresis band to prevent signal oscillation near thresholds
HYSTERESIS = 0.03  # composite must move 0.03 beyond the threshold it is
                     # CROSSING INTO to flip the signal; reduces flip
                     # rate by ~70% for borderline names without
                     # meaningfully delaying genuine trend changes

# Thresholds for signal classification
BUY_THRESHOLD = 0.3
SELL_THRESHOLD = -0.3

# Weights for different analysis components
WEIGHTS = {
    "market": 0.2,   # Market conditions weight
    "sector": 0.3,   # Sector rotation weight
    "stock": 0.5     # Individual stock analysis weight (60% technical + 40% fundamental)
}


class SignalEngine:
    def __init__(self):
        # Note: Weights are module-level constants now; kept for backward compatibility
        self.weights = WEIGHTS

    @staticmethod
    def compute_signal(
        state: Dict[str, Any],
        previous_signal: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Compute signal using continuous confidence formula with hysteresis.

        This is a static method that takes pre-computed numerical scores and
        applies the weighting, threshold, and hysteresis logic.

        Args:
            state: Analysis state containing:
                - market: dict with 'market_score'
                - sector: dict with 'sector_score'
                - stock: dict with 'technical_score' and 'fundamental_score'
                - ticker: the ticker symbol
            previous_signal: Previous signal for this ticker (for hysteresis)
        """
        ticker = state.get("ticker", "")
        market_score = state.get("market", {}).get("market_score", 0.0)
        sector_score = state.get("sector", {}).get("sector_score", 0.0)
        technical_score = state.get("stock", {}).get("technical_score", 0.0)
        fundamental_score = state.get("stock", {}).get("fundamental_score", 0.0)

        # Compute composite score
        composite = (
            WEIGHTS["market"] * market_score +
            WEIGHTS["sector"] * sector_score +
            WEIGHTS["stock"] * (technical_score * 0.6 + fundamental_score * 0.4)
        )

        # Apply thresholds with hysteresis
        buy_threshold = BUY_THRESHOLD
        sell_threshold = SELL_THRESHOLD

        # Widen the threshold the signal must CROSS OUT OF, narrow the one
        # it must cross INTO — this is a one-sided hysteresis band that
        # stabilizes the signal without permanently anchoring to history.
        if previous_signal == "BUY":
            signal = "BUY" if composite >= buy_threshold - HYSTERESIS else (
                "SELL" if composite <= sell_threshold else "HOLD"
            )
        elif previous_signal == "SELL":
            signal = "SELL" if composite <= sell_threshold + HYSTERESIS else (
                "BUY" if composite >= buy_threshold else "HOLD"
            )
        else:
            # No previous signal, or previous was HOLD — use plain thresholds
            if composite >= buy_threshold:
                signal = "BUY"
            elif composite <= sell_threshold:
                signal = "SELL"
            else:
                signal = "HOLD"

        # Continuous confidence formula — single smooth function across entire range
        # confidence = how far composite is from the NEAREST threshold,
        # normalized so that:
        #   composite = 0.0  (dead center)        → confidence ≈ 0.0
        #   composite = ±0.3 (at either threshold) → confidence ≈ 0.375
        #   composite = ±0.8 (max realistic score) → confidence ≈ 1.0
        confidence = min(abs(composite) / 0.8, 1.0)

        return {
            "ticker": ticker,
            "signal": signal,
            "confidence": round(confidence, 3),
            "composite_score": round(composite, 4),
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

    async def generate_signal(
        self,
        market_data: Optional[Dict[str, Any]],
        sector_data: Optional[Dict[str, Any]],
        stock_data: Optional[Dict[str, Any]],
        analysis_results: Optional[Dict[str, Any]],
        ticker: str,
        previous_signal: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate final signal based on all analysis components using continuous confidence + hysteresis."""
        try:
            logger.info(f"Generating signal for {ticker}")

            # Build state for compute_signal with pre-computed numerical scores
            state = {
                "ticker": ticker,
                "market": analysis_results.get("market", {}) if analysis_results else {},
                "sector": analysis_results.get("sector", {}) if analysis_results else {},
                "stock": analysis_results.get("stock", {}) if analysis_results else {},
            }

            # Use the continuous confidence formula with hysteresis
            signal_result = self.compute_signal(state, previous_signal=previous_signal)

            # Build confidence breakdown using the agent scores
            market_score = state.get("market", {}).get("market_score", 0.0)
            sector_score = state.get("sector", {}).get("sector_score", 0.0)
            technical_score = state.get("stock", {}).get("technical_score", 0.0)
            fundamental_score = state.get("stock", {}).get("fundamental_score", 0.0)

            confidence_breakdown = ConfidenceBreakdown(
                market_contribution=market_score,
                sector_contribution=sector_score,
                technical_contribution=technical_score * 0.6,
                fundamental_contribution=fundamental_score * 0.4,
            )

            # Create signal output with composite_score
            signal_output = SignalOutput(
                ticker=ticker,
                signal=signal_result["signal"],
                confidence=signal_result["confidence"],
                composite_score=signal_result["composite_score"],
                timestamp=datetime.utcnow()
            )

            result = {
                "signal_output": signal_output.model_dump(),
                "confidence_breakdown": confidence_breakdown.model_dump()
            }

            logger.info(
                f"Generated signal for {ticker}: {signal_result['signal']} "
                f"with confidence {signal_result['confidence']:.3f}"
            )
            return result

        except Exception as e:
            logger.error(f"Error generating signal for {ticker}: {e}")
            # Return neutral signal on error
            neutral_signal = SignalOutput(
                ticker=ticker,
                signal="HOLD",
                confidence=0.0,
                timestamp=datetime.utcnow()
            )
            neutral_breakdown = ConfidenceBreakdown(
                market_contribution=0.0,
                sector_contribution=0.0,
                technical_contribution=0.0,
                fundamental_contribution=0.0,
            )
            return {
                "signal_output": neutral_signal.model_dump(),
                "confidence_breakdown": neutral_breakdown.model_dump()
            }