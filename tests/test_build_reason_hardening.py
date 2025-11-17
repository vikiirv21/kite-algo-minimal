"""Tests for build_reason hardening to handle None indicators"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from strategies.fno_intraday_trend import build_reason


def test_build_reason_with_none_price():
    """Test that build_reason handles None price gracefully"""
    indicators = {
        "ema20": 100.0,
        "ema50": 95.0,
        "ema100": 90.0,
        "ema200": 85.0,
        "rsi14": 50.0,
    }
    regime = "UP_TREND"
    signal = "BUY"
    
    result = build_reason(None, indicators, regime, signal)
    
    assert "Indicators warming up or missing" in result
    assert "price=None" in result
    print("✓ test_build_reason_with_none_price")


def test_build_reason_with_none_ema20():
    """Test that build_reason handles None ema20 gracefully"""
    indicators = {
        "ema20": None,
        "ema50": 95.0,
        "ema100": 90.0,
        "ema200": 85.0,
        "rsi14": 50.0,
    }
    regime = "UP_TREND"
    signal = "BUY"
    
    result = build_reason(100.0, indicators, regime, signal)
    
    assert "Indicators warming up or missing" in result
    assert "ema20=None" in result
    print("✓ test_build_reason_with_none_ema20")


def test_build_reason_with_none_ema50():
    """Test that build_reason handles None ema50 gracefully"""
    indicators = {
        "ema20": 100.0,
        "ema50": None,
        "ema100": 90.0,
        "ema200": 85.0,
        "rsi14": 50.0,
    }
    regime = "UP_TREND"
    signal = "BUY"
    
    result = build_reason(100.0, indicators, regime, signal)
    
    assert "Indicators warming up or missing" in result
    assert "ema50=None" in result
    print("✓ test_build_reason_with_none_ema50")


def test_build_reason_with_none_ema100():
    """Test that build_reason handles None ema100 gracefully"""
    indicators = {
        "ema20": 100.0,
        "ema50": 95.0,
        "ema100": None,
        "ema200": 85.0,
        "rsi14": 50.0,
    }
    regime = "UP_TREND"
    signal = "BUY"
    
    result = build_reason(100.0, indicators, regime, signal)
    
    assert "Indicators warming up or missing" in result
    assert "ema100=None" in result
    print("✓ test_build_reason_with_none_ema100")


def test_build_reason_with_none_ema200():
    """Test that build_reason handles None ema200 gracefully"""
    indicators = {
        "ema20": 100.0,
        "ema50": 95.0,
        "ema100": 90.0,
        "ema200": None,
        "rsi14": 50.0,
    }
    regime = "UP_TREND"
    signal = "BUY"
    
    result = build_reason(100.0, indicators, regime, signal)
    
    assert "Indicators warming up or missing" in result
    assert "ema200=None" in result
    print("✓ test_build_reason_with_none_ema200")


def test_build_reason_with_missing_indicators():
    """Test that build_reason handles missing indicator keys"""
    indicators = {}  # Empty dict, all indicators missing
    regime = "UNKNOWN"
    signal = "HOLD"
    
    result = build_reason(100.0, indicators, regime, signal)
    
    assert "Indicators warming up or missing" in result
    assert "ema20=None" in result
    assert "ema50=None" in result
    assert "ema100=None" in result
    assert "ema200=None" in result
    print("✓ test_build_reason_with_missing_indicators")


def test_build_reason_with_all_none():
    """Test that build_reason handles all None values"""
    indicators = {
        "ema20": None,
        "ema50": None,
        "ema100": None,
        "ema200": None,
    }
    regime = "UNKNOWN"
    signal = "HOLD"
    
    result = build_reason(None, indicators, regime, signal)
    
    assert "Indicators warming up or missing" in result
    assert "price=None" in result
    print("✓ test_build_reason_with_all_none")


def test_build_reason_with_valid_indicators():
    """Test that build_reason works normally with valid indicators"""
    indicators = {
        "ema20": 105.0,
        "ema50": 100.0,
        "ema100": 95.0,
        "ema200": 90.0,
        "rsi14": 65.0,
    }
    regime = "UP_TREND"
    signal = "BUY"
    
    result = build_reason(110.0, indicators, regime, signal)
    
    # Should NOT have the warming up message
    assert "Indicators warming up or missing" not in result
    # Should have regime info
    assert "regime:UP_TREND" in result
    # Should detect above_fast_emas (110 > 105 > 100)
    assert "above_fast_emas" in result
    print("✓ test_build_reason_with_valid_indicators")


def test_build_reason_signal_formatting():
    """Test that signal formatting is safe with different signal types"""
    indicators = {
        "ema20": None,
        "ema50": None,
        "ema100": None,
        "ema200": None,
    }
    regime = "UNKNOWN"
    
    # Test with string signal
    result = build_reason(100.0, indicators, regime, "BUY")
    assert "signal=BUY" in result
    
    # Test with None signal
    result = build_reason(100.0, indicators, regime, None)
    assert "signal=None" in result
    
    print("✓ test_build_reason_signal_formatting")


def test_build_reason_chained_comparison_below():
    """Test chained comparison for below_fast_emas"""
    indicators = {
        "ema20": 105.0,
        "ema50": 110.0,
        "ema100": 115.0,
        "ema200": 120.0,
        "rsi14": 35.0,
    }
    regime = "DOWN_TREND"
    signal = "SELL"
    
    result = build_reason(100.0, indicators, regime, signal)
    
    # Should NOT have the warming up message
    assert "Indicators warming up or missing" not in result
    # Should detect below_fast_emas (100 < 105 < 110)
    assert "below_fast_emas" in result
    print("✓ test_build_reason_chained_comparison_below")


def run_all_tests():
    """Run all tests and report results"""
    tests = [
        test_build_reason_with_none_price,
        test_build_reason_with_none_ema20,
        test_build_reason_with_none_ema50,
        test_build_reason_with_none_ema100,
        test_build_reason_with_none_ema200,
        test_build_reason_with_missing_indicators,
        test_build_reason_with_all_none,
        test_build_reason_with_valid_indicators,
        test_build_reason_signal_formatting,
        test_build_reason_chained_comparison_below,
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
