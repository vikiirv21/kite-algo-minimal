"""Tests for strategies/fno_intraday_trend.py robustness to invalid data"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from strategies.fno_intraday_trend import FnoIntradayTrendStrategy
from strategies.base import Decision


def test_strategy_handles_none_close():
    """Test that strategy handles None close value gracefully"""
    strategy = FnoIntradayTrendStrategy()
    
    # Test with None close value
    bar = {"close": None}
    decision = strategy.on_bar("TEST_SYMBOL", bar)
    
    assert isinstance(decision, Decision)
    assert decision.action == "HOLD"
    assert "invalid_price" in decision.reason
    print("✓ test_strategy_handles_none_close")


def test_strategy_handles_missing_close():
    """Test that strategy handles missing close key"""
    strategy = FnoIntradayTrendStrategy()
    
    # Test with missing close key (defaults to 0.0)
    bar = {"open": 100.0, "high": 105.0}
    decision = strategy.on_bar("TEST_SYMBOL", bar)
    
    assert isinstance(decision, Decision)
    assert decision.action == "HOLD"
    assert decision.reason == "invalid_price"  # 0.0 is <= 0
    print("✓ test_strategy_handles_missing_close")


def test_strategy_handles_invalid_type_close():
    """Test that strategy handles non-numeric close value"""
    strategy = FnoIntradayTrendStrategy()
    
    # Test with string that can't be converted
    bar = {"close": "invalid"}
    decision = strategy.on_bar("TEST_SYMBOL", bar)
    
    assert isinstance(decision, Decision)
    assert decision.action == "HOLD"
    assert "invalid_price" in decision.reason
    print("✓ test_strategy_handles_invalid_type_close")


def test_strategy_handles_negative_close():
    """Test that strategy handles negative close value"""
    strategy = FnoIntradayTrendStrategy()
    
    # Test with negative close
    bar = {"close": -100.0}
    decision = strategy.on_bar("TEST_SYMBOL", bar)
    
    assert isinstance(decision, Decision)
    assert decision.action == "HOLD"
    assert decision.reason == "invalid_price"
    print("✓ test_strategy_handles_negative_close")


def test_strategy_handles_zero_close():
    """Test that strategy handles zero close value"""
    strategy = FnoIntradayTrendStrategy()
    
    # Test with zero close
    bar = {"close": 0.0}
    decision = strategy.on_bar("TEST_SYMBOL", bar)
    
    assert isinstance(decision, Decision)
    assert decision.action == "HOLD"
    assert decision.reason == "invalid_price"
    print("✓ test_strategy_handles_zero_close")


def test_strategy_handles_valid_close():
    """Test that strategy works normally with valid close value"""
    strategy = FnoIntradayTrendStrategy()
    
    # Test with valid close - should work without error
    bar = {"close": 100.0}
    decision = strategy.on_bar("TEST_SYMBOL", bar)
    
    assert isinstance(decision, Decision)
    assert decision.action == "HOLD"
    # Warmup phase, not enough data yet
    assert decision.reason == "warmup"
    print("✓ test_strategy_handles_valid_close")


def test_strategy_no_crash_on_bad_bars():
    """Test that strategy doesn't crash on multiple bad bars"""
    strategy = FnoIntradayTrendStrategy()
    
    bad_bars = [
        {"close": None},
        {"close": "bad"},
        {"close": 0.0},
        {"close": -1.0},
        {},
    ]
    
    for i, bar in enumerate(bad_bars):
        decision = strategy.on_bar(f"TEST_{i}", bar)
        assert isinstance(decision, Decision)
        assert decision.action == "HOLD"
    
    print("✓ test_strategy_no_crash_on_bad_bars")


def run_all_tests():
    """Run all tests and report results"""
    tests = [
        test_strategy_handles_none_close,
        test_strategy_handles_missing_close,
        test_strategy_handles_invalid_type_close,
        test_strategy_handles_negative_close,
        test_strategy_handles_zero_close,
        test_strategy_handles_valid_close,
        test_strategy_no_crash_on_bad_bars,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"✗ {test.__name__}: {e}")
            failed += 1
    
    print(f"\nResults: {passed} passed, {failed} failed")
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
