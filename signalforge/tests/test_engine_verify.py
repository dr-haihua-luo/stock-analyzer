"""
Quick verification that the three horizon signals work correctly and can disagree.
Run: uv run pytest tests/test_engine_verify.py -v -s
"""
from backend.signal.engine import (
    compute_all_signals,
    compute_swing_signal,
    compute_position_signal,
    compute_day_trade_signal,
    SWING_WEIGHTS,
    POSITION_WEIGHTS,
    DAY_TRADE_WEIGHTS,
)


def _make_mock_state():
    """Scenario: strong technicals, weak fundamentals, oversold RSI, high VIX."""
    return {
        "ticker": "TEST",
        "market": {"market_score": 0.3},
        "sector": {"sector_score": 0.2, "ticker_sector": "Technology"},
        "stock": {
            "technical_score": 0.8,     # very strong technicals
            "fundamental_score": -0.5,  # weak fundamentals
            "rsi_14": 28,                # oversold -> bullish mean-reversion
            "bb_position": "below_lower",
            "volume_trend": "increasing",
            "pe_ratio": 15.0,            # cheap vs sector benchmark 28.0
            "news_sentiment": 0.1,
        },
        "fundamentals": type("F", (), {
            "score_components": {"institutional_flow": 0.4},
            "finviz": None,
        })(),
        "earnings_quality": None,
    }


def test_swings_and_position_can_disagree():
    """Swing should be BUY (strong technicals), position should be SELL (weak fundamentals)."""
    state = _make_mock_state()
    result = compute_all_signals(state)

    swing = result["swing"]
    position = result["position"]
    day_trade = result["day_trade"]

    # Swing: technical-heavy + strong technicals -> BUY
    assert swing["signal"] == "BUY", f"Expected swing BUY, got {swing['signal']}"
    assert swing["status"] == "ok"

    # Position: fundamental-heavy + weak fundamentals -> SELL
    assert position["signal"] == "SELL", f"Expected position SELL, got {position['signal']}"
    assert position["status"] == "ok"

    # They genuinely disagree
    assert swing["signal"] != position["signal"], "Swing and position should disagree"

    # Relative valuation populated on position
    rv = position["relative_valuation"]
    assert rv is not None, "Position should have relative valuation"
    assert rv["pe_ratio"] == 15.0
    assert rv["sector_benchmark"] == 28.0
    assert rv["pct_vs_benchmark"] < -15  # 15.0/28.0 = -46.4% -> "cheap vs sector"
    assert rv["label"] == "cheap vs sector"

    # Day trade: oversold RSI + below lower BB + increasing volume + high VIX -> BUY
    assert day_trade["signal"] == "BUY", f"Expected day_trade BUY, got {day_trade['signal']}"
    assert day_trade["status"] == "experimental"
    assert day_trade["disclaimer"] is not None
    assert "EXPERIMENTAL" in day_trade["disclaimer"]

    print(f"\n  swing:     signal={swing['signal']:5s}  score={swing['composite_score']:+.3f}  conf={swing['confidence']:.3f}")
    print(f"  position:  signal={position['signal']:5s}  score={position['composite_score']:+.3f}  conf={position['confidence']:.3f}")
    print(f"  day_trade: signal={day_trade['signal']:5s}  score={day_trade['composite_score']:+.3f}  conf={day_trade['confidence']:.3f}  [experimental]")
    print(f"  rv:        pe={rv['pe_ratio']} vs bench={rv['sector_benchmark']} -> {rv['pct_vs_benchmark']}% -> {rv['label']}")
    print("\n  ALL ASSERTIONS PASSED — swing BUY + position SELL ✓")


def test_all_signals_present_and_has_required_fields():
    state = _make_mock_state()
    result = compute_all_signals(state)

    for horizon_name, expected_weights in [("swing", SWING_WEIGHTS),
                                            ("position", POSITION_WEIGHTS),
                                            ("day_trade", DAY_TRADE_WEIGHTS)]:
        s = result[horizon_name]
        assert s["horizon"] == horizon_name
        assert s["signal"] in ("BUY", "SELL", "HOLD")
        assert s["confidence"] is not None
        assert s["composite_score"] is not None
        assert s["weights"] == expected_weights
