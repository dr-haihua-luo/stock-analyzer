from typing import Dict, Any, Optional
from backend.signal.models import SignalOutput, ConfidenceBreakdown
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class SignalEngine:
    def __init__(self):
        # Weights for different analysis components
        self.weights = {
            "market": 0.3,   # Market conditions weight
            "sector": 0.3,   # Sector rotation weight
            "stock": 0.4     # Individual stock analysis weight
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
        analysis_results: Dict[str, Any],
        ticker: str
    ) -> Dict[str, Any]:
        """Generate final signal based on all analysis components."""
        try:
            logger.info(f"Generating signal for {ticker}")

            # Extract signals and confidences from each analysis component
            market_analysis = analysis_results.get("market", {}) if analysis_results else {}
            sector_analysis = analysis_results.get("sector", {}) if analysis_results else {}
            stock_analysis = analysis_results.get("stock", {}) if analysis_results else {}

            market_signal, market_confidence = self._extract_signal_from_analysis(market_analysis)
            sector_signal, sector_confidence = self._extract_signal_from_analysis(sector_analysis)
            stock_signal, stock_confidence = self._extract_signal_from_analysis(stock_analysis)

            # Convert signals to numerical scores for weighting
            # BUY = +1, HOLD = 0, SELL = -1
            signal_scores = {
                "BUY": 1.0,
                "HOLD": 0.0,
                "SELL": -1.0
            }

            market_score = signal_scores.get(market_signal, 0.0) * market_confidence
            sector_score = signal_scores.get(sector_signal, 0.0) * sector_confidence
            stock_score = signal_scores.get(stock_signal, 0.0) * stock_confidence

            # Apply weights
            weighted_score = (
                market_score * self.weights["market"] +
                sector_score * self.weights["sector"] +
                stock_score * self.weights["stock"]
            )

            # Convert weighted score back to signal
            if weighted_score > 0.1:
                final_signal = "BUY"
            elif weighted_score < -0.1:
                final_signal = "SELL"
            else:
                final_signal = "HOLD"

            # Calculate overall confidence as weighted average of component confidences
            total_confidence = (
                market_confidence * self.weights["market"] +
                sector_confidence * self.weights["sector"] +
                stock_confidence * self.weights["stock"]
            )

            # Ensure confidence is in valid range
            total_confidence = max(0.0, min(1.0, total_confidence))

            # Create confidence breakdown with signed contributions
            # Stock factor splits between technical and fundamental (each gets 50% of stock weight)
            # Technical and fundamental both come from stock analysis
            technical_conf = stock_confidence * 0.5
            fundamental_conf = stock_confidence * 0.5
            # Market and sector contributions are signed scores
            market_contrib = market_score  # Already signed (-1 to +1)
            sector_contrib = sector_score  # Already signed (-1 to +1)

            confidence_breakdown = ConfidenceBreakdown(
                market_contribution=market_contrib,
                sector_contribution=sector_contrib,
                technical_contribution=technical_conf,
                fundamental_contribution=fundamental_conf,
            )

            # Create signal output
            signal_output = SignalOutput(
                ticker=ticker,
                signal=final_signal,
                confidence=total_confidence,
                timestamp=datetime.utcnow()
            )

            result = {
                "signal_output": signal_output.model_dump(),
                "confidence_breakdown": confidence_breakdown.model_dump()
            }

            logger.info(f"Generated signal for {ticker}: {final_signal} with confidence {total_confidence:.2f}")
            return result

        except Exception as e:
            logger.error(f"Error generating signal for {ticker}: {e}")
            # Return neutral signal on error
            neutral_signal = SignalOutput(
                ticker=ticker,
                signal="HOLD",
                confidence=0.5,
                timestamp=datetime.utcnow()
            )
            neutral_breakdown = ConfidenceBreakdown(
                market_contribution=0.0,
                sector_contribution=0.0,
                technical_contribution=0.5,
                fundamental_contribution=0.5,
            )
            return {
                "signal_output": neutral_signal.model_dump(),
                "confidence_breakdown": neutral_breakdown.model_dump()
            }