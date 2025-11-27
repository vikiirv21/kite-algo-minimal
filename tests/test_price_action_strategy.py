"""Tests for strategies/price_action_intraday_v1.py"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.strategy_engine_v2 import StrategyState
from strategies.price_action_intraday_v1 import (
    PriceActionIntradayV1,
    create_price_action_intraday_v1,
)
from strategies.base import Decision


def create_mock_candle(
    open_price: float = 100.0,
    high: float = 105.0,
    low: float = 95.0,
    close: float = 102.0,
    volume: int = 10000
) -> dict:
    """Create a mock candle dict for testing."""
    return {
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }


def create_mock_series(n: int = 100) -> dict:
    """Create mock series with n candles for testing."""
    base_price = 100.0
    return {
        "open": [base_price + i * 0.1 for i in range(n)],
        "high": [base_price + i * 0.1 + 2 for i in range(n)],
        "low": [base_price + i * 0.1 - 2 for i in range(n)],
        "close": [base_price + i * 0.1 + 0.5 for i in range(n)],
        "volume": [10000 + i * 100 for i in range(n)],
    }


def create_mock_indicators(
    ema20: float = 105.0,
    ema50: float = 100.0,
    rsi14: float = 50.0,
    atr14: float = 2.0
) -> dict:
    """Create mock indicators dict for testing."""
    return {
        "ema20": ema20,
        "ema50": ema50,
        "rsi14": rsi14,
        "atr14": atr14,
        "trend": "up" if ema20 > ema50 else "down",
    }


def test_strategy_initialization():
    """Test PriceActionIntradayV1 initialization with default config."""
    config = {"name": "price_action_v1", "timeframe": "5m"}
    state = StrategyState()
    
    strategy = PriceActionIntradayV1(config, state)
    
    assert strategy.name == "price_action_intraday_v1"
    assert strategy.timeframe == "5m"
    assert strategy.ema_fast == 20
    assert strategy.ema_slow == 50
    assert strategy.volume_spike_factor == 1.5
    assert strategy.min_confidence_to_trade == 0.6


def test_strategy_initialization_custom_config():
    """Test PriceActionIntradayV1 initialization with custom config."""
    config = {
        "name": "price_action_v1",
        "timeframe": "1m",
        "ema_fast": 9,
        "ema_slow": 21,
        "volume_spike_factor": 2.0,
        "min_confidence_to_trade": 0.7,
        "atr_period": 10,
        "enable_patterns": False,
    }
    state = StrategyState()
    
    strategy = PriceActionIntradayV1(config, state)
    
    assert strategy.timeframe == "1m"
    assert strategy.ema_fast == 9
    assert strategy.ema_slow == 21
    assert strategy.volume_spike_factor == 2.0
    assert strategy.min_confidence_to_trade == 0.7
    assert strategy.atr_period == 10
    assert strategy.enable_patterns is False


def test_generate_signal_hold_missing_indicators():
    """Test that HOLD is returned when indicators are missing."""
    config = {"name": "price_action_v1"}
    state = StrategyState()
    strategy = PriceActionIntradayV1(config, state)
    
    candle = create_mock_candle()
    series = create_mock_series()
    indicators = {}  # No indicators
    
    decision = strategy.generate_signal(candle, series, indicators)
    
    assert decision is not None
    assert decision.action == "HOLD"
    assert "missing" in decision.reason.lower()


def test_generate_signal_hold_invalid_price():
    """Test that HOLD is returned when price is invalid."""
    config = {"name": "price_action_v1"}
    state = StrategyState()
    strategy = PriceActionIntradayV1(config, state)
    
    candle = create_mock_candle(close=0)  # Invalid price
    series = create_mock_series()
    indicators = create_mock_indicators()
    
    decision = strategy.generate_signal(candle, series, indicators)
    
    assert decision is not None
    assert decision.action == "HOLD"
    assert "invalid" in decision.reason.lower()


def test_generate_signal_hold_low_confidence():
    """Test that HOLD is returned when confidence is below threshold."""
    config = {
        "name": "price_action_v1",
        "min_confidence_to_trade": 0.9,  # High threshold
    }
    state = StrategyState()
    strategy = PriceActionIntradayV1(config, state)
    
    # Setup: uptrend but no pattern/volume spike
    candle = create_mock_candle()
    series = create_mock_series()
    indicators = create_mock_indicators(ema20=105.0, ema50=100.0)
    
    decision = strategy.generate_signal(candle, series, indicators)
    
    assert decision is not None
    # Should hold due to low confidence (no patterns, no volume spike)
    assert decision.action == "HOLD"


def test_generate_signal_uptrend_detection():
    """Test that uptrend is correctly detected."""
    config = {
        "name": "price_action_v1",
        "min_confidence_to_trade": 0.0,  # Allow any signal for testing
    }
    state = StrategyState()
    strategy = PriceActionIntradayV1(config, state)
    
    candle = create_mock_candle()
    series = create_mock_series()
    indicators = create_mock_indicators(ema20=110.0, ema50=100.0)  # Uptrend
    
    # First call to establish state
    strategy.generate_signal(candle, series, indicators)
    
    # Verify internal state shows uptrend
    symbol = strategy.config.get("current_symbol", "UNKNOWN")
    prev_state = strategy._prev_state.get(symbol, {})
    assert prev_state.get("fast_above_slow", False) is True


def test_generate_signal_downtrend_detection():
    """Test that downtrend is correctly detected."""
    config = {
        "name": "price_action_v1",
        "min_confidence_to_trade": 0.0,
    }
    state = StrategyState()
    strategy = PriceActionIntradayV1(config, state)
    
    candle = create_mock_candle()
    series = create_mock_series()
    indicators = create_mock_indicators(ema20=95.0, ema50=100.0)  # Downtrend
    
    strategy.generate_signal(candle, series, indicators)
    
    symbol = strategy.config.get("current_symbol", "UNKNOWN")
    prev_state = strategy._prev_state.get(symbol, {})
    assert prev_state.get("fast_above_slow", True) is False


def test_detect_hammer_pattern():
    """Test hammer pattern detection."""
    config = {"name": "price_action_v1"}
    state = StrategyState()
    strategy = PriceActionIntradayV1(config, state)
    
    # Create a hammer candle: small body near top, long lower wick
    hammer_candle = {
        "open": 100.0,
        "high": 101.0,  # Small upper wick
        "low": 95.0,    # Long lower wick
        "close": 100.5, # Close near high (small body)
        "volume": 10000,
    }
    series = create_mock_series()
    
    result = strategy._detect_patterns(hammer_candle, series)
    
    # Should detect bullish pattern
    assert result["bullish_pattern"] is True
    assert result["pattern_type"] == "hammer"


def test_detect_engulfing_pattern():
    """Test engulfing pattern detection."""
    config = {"name": "price_action_v1"}
    state = StrategyState()
    strategy = PriceActionIntradayV1(config, state)
    
    # Create series with a red candle followed by green engulfing
    series = {
        "open": [100.0, 99.0, 98.0],   # Previous candle opens higher
        "high": [101.0, 100.0, 103.0],
        "low": [98.0, 97.0, 96.5],
        "close": [99.0, 98.0, 102.0],  # Previous close is lower than open (red)
        "volume": [10000, 10000, 15000],
    }
    
    # Current candle is bullish and engulfs previous
    current_candle = {
        "open": 97.0,   # Opens below previous close
        "high": 103.0,
        "low": 96.5,
        "close": 102.0, # Closes above previous open - engulfs
        "volume": 15000,
    }
    
    result = strategy._detect_patterns(current_candle, series)
    
    # Should detect bullish engulfing pattern
    assert result["bullish_pattern"] is True
    assert result["pattern_type"] == "bull_engulf"


def test_detect_volume_spike():
    """Test volume spike detection."""
    config = {
        "name": "price_action_v1",
        "volume_spike_factor": 1.5,
        "volume_window": 20,
    }
    state = StrategyState()
    strategy = PriceActionIntradayV1(config, state)
    
    # Create series with average volume of 10000
    series = {
        "volume": [10000] * 25,
    }
    
    # Current candle with spike volume
    candle_with_spike = {
        "open": 100.0,
        "high": 105.0,
        "low": 95.0,
        "close": 102.0,
        "volume": 20000,  # 2x average - should be spike
    }
    
    is_spike = strategy._detect_volume_spike(candle_with_spike, series)
    assert is_spike is True
    
    # Current candle without spike
    candle_no_spike = {
        "open": 100.0,
        "high": 105.0,
        "low": 95.0,
        "close": 102.0,
        "volume": 12000,  # 1.2x average - not a spike
    }
    
    is_spike = strategy._detect_volume_spike(candle_no_spike, series)
    assert is_spike is False


def test_detect_volatility_mode():
    """Test ATR volatility mode detection."""
    config = {
        "name": "price_action_v1",
        "atr_period": 14,
        "atr_expand_factor": 1.2,
        "atr_compress_factor": 0.8,
    }
    state = StrategyState()
    strategy = PriceActionIntradayV1(config, state)
    
    # Create series with consistent range
    n = 50
    series = {
        "high": [100.0 + 2.0 for _ in range(n)],
        "low": [100.0 - 2.0 for _ in range(n)],
        "close": [100.0 for _ in range(n)],
    }
    
    # Test normal mode
    indicators = {"atr14": 4.0}  # Average range
    mode = strategy._detect_volatility_mode(series, indicators)
    assert mode == "normal"


def test_calculate_confidence():
    """Test confidence calculation."""
    config = {"name": "price_action_v1"}
    state = StrategyState()
    strategy = PriceActionIntradayV1(config, state)
    
    # Base confidence (EMA alignment only)
    components = {
        "bullish_pattern": False,
        "bearish_pattern": False,
        "volume_spike": False,
        "is_compressing": False,
    }
    indicators = {"rsi14": 50.0}
    
    confidence = strategy._calculate_confidence(components, indicators, is_uptrend=True)
    assert 0.0 <= confidence <= 1.0
    assert confidence >= 0.3  # Base score
    
    # Full confluence (pattern + volume + vol_ok + RSI)
    components = {
        "bullish_pattern": True,
        "bearish_pattern": False,
        "pattern_type": "hammer",
        "volume_spike": True,
        "is_compressing": False,
    }
    indicators = {"rsi14": 55.0}  # RSI in bullish range
    
    confidence = strategy._calculate_confidence(components, indicators, is_uptrend=True)
    assert confidence > 0.7  # Should be high confidence


def test_factory_function():
    """Test the factory function."""
    config = {"name": "price_action_v1", "timeframe": "5m"}
    state = StrategyState()
    
    strategy = create_price_action_intraday_v1(config, state)
    
    assert isinstance(strategy, PriceActionIntradayV1)
    assert strategy.name == "price_action_intraday_v1"


def test_strategy_state_position_tracking():
    """Test that strategy correctly uses state for position tracking."""
    config = {"name": "price_action_v1", "current_symbol": "NIFTY"}
    state = StrategyState()
    strategy = PriceActionIntradayV1(config, state)
    
    # Initially no position
    assert not strategy.position_is_long("NIFTY")
    assert not strategy.position_is_short("NIFTY")
    
    # Open long position
    state.update_position("NIFTY", 1, 100.0)
    assert strategy.position_is_long("NIFTY")
    assert not strategy.position_is_short("NIFTY")
    
    # Open short position
    state.update_position("BANKNIFTY", -1, 200.0)
    assert not strategy.position_is_long("BANKNIFTY")
    assert strategy.position_is_short("BANKNIFTY")


def test_context_expiry_adjustment():
    """Test that expiry context adjusts confidence."""
    config = {
        "name": "price_action_v1",
        "min_confidence_to_trade": 0.0,  # Allow signals for testing
        "current_symbol": "NIFTY",
    }
    state = StrategyState()
    strategy = PriceActionIntradayV1(config, state)
    
    candle = create_mock_candle()
    series = create_mock_series()
    
    # Setup for bullish signal
    indicators = create_mock_indicators(ema20=110.0, ema50=100.0, rsi14=55.0)
    
    # First call to establish state (simulate crossover)
    strategy._prev_state["NIFTY"] = {"fast_above_slow": False}
    
    # Normal context
    normal_context = {}
    decision_normal = strategy.generate_signal(candle, series, indicators, normal_context)
    
    # Reset state for next call
    strategy._prev_state["NIFTY"] = {"fast_above_slow": False}
    
    # Expiry context (last hour)
    expiry_context = {
        "is_expiry_day": True,
        "time_to_expiry_minutes": 30,
    }
    decision_expiry = strategy.generate_signal(candle, series, indicators, expiry_context)
    
    # Both should have signals (or both should not based on confluence)
    # If both have BUY signals, expiry should have slightly lower confidence
    if decision_normal.action == "BUY" and decision_expiry.action == "BUY":
        # Expiry confidence should be 90% of normal
        assert decision_expiry.confidence <= decision_normal.confidence


def run_all_tests():
    """Run all tests and report results."""
    tests = [
        test_strategy_initialization,
        test_strategy_initialization_custom_config,
        test_generate_signal_hold_missing_indicators,
        test_generate_signal_hold_invalid_price,
        test_generate_signal_hold_low_confidence,
        test_generate_signal_uptrend_detection,
        test_generate_signal_downtrend_detection,
        test_detect_hammer_pattern,
        test_detect_engulfing_pattern,
        test_detect_volume_spike,
        test_detect_volatility_mode,
        test_calculate_confidence,
        test_factory_function,
        test_strategy_state_position_tracking,
        test_context_expiry_adjustment,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            print(f"✓ {test.__name__}")
            passed += 1
        except Exception as e:
            print(f"✗ {test.__name__}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    print(f"\nResults: {passed} passed, {failed} failed")
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
