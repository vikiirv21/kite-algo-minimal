"""Tests for core/indicators.py"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.indicators import (
    ema, sma, rsi, atr, supertrend, bollinger, vwap, slope, hl2, hl3
)


def test_ema_basic():
    """Test EMA calculation with simple data"""
    data = [100.0, 102.0, 104.0, 103.0, 105.0, 107.0, 106.0, 108.0, 110.0, 109.0]
    result = ema(data, period=5)
    assert isinstance(result, float)
    assert result > 0
    
    # Test with return_series
    series = ema(data, period=5, return_series=True)
    assert isinstance(series, list)
    assert len(series) == len(data)


def test_sma_basic():
    """Test SMA calculation"""
    data = [100.0, 102.0, 104.0, 103.0, 105.0]
    result = sma(data, period=3)
    # Last 3 values: 104, 103, 105 -> average = 104
    assert abs(result - 104.0) < 0.01
    
    series = sma(data, period=3, return_series=True)
    assert len(series) == len(data)


def test_rsi_basic():
    """Test RSI calculation"""
    # Create data with clear uptrend (should have high RSI)
    data = [100 + i * 0.5 for i in range(20)]
    result = rsi(data, period=14)
    assert isinstance(result, float)
    assert 0 <= result <= 100
    assert result > 50  # Uptrend should have RSI > 50
    
    series = rsi(data, period=14, return_series=True)
    assert len(series) == len(data) - 1  # One less due to diff


def test_atr_basic():
    """Test ATR calculation"""
    high = [105.0, 107.0, 106.0, 108.0, 110.0] * 4  # 20 bars
    low = [95.0, 97.0, 96.0, 98.0, 100.0] * 4
    close = [100.0, 102.0, 101.0, 103.0, 105.0] * 4
    
    result = atr(high, low, close, period=14)
    assert isinstance(result, float)
    assert result > 0
    
    series = atr(high, low, close, period=14, return_series=True)
    assert len(series) == len(close)


def test_supertrend_basic():
    """Test SuperTrend calculation"""
    # Create trending data
    high = [105.0 + i for i in range(20)]
    low = [95.0 + i for i in range(20)]
    close = [100.0 + i for i in range(20)]
    
    result = supertrend(high, low, close, period=10, multiplier=3.0)
    assert isinstance(result, dict)
    assert 'supertrend' in result
    assert 'direction' in result
    assert result['direction'] in [1, -1]
    
    series = supertrend(high, low, close, period=10, multiplier=3.0, return_series=True)
    assert isinstance(series, list)
    assert len(series) == len(close)


def test_bollinger_basic():
    """Test Bollinger Bands calculation"""
    data = [100.0, 102.0, 104.0, 103.0, 105.0] * 5  # 25 bars
    result = bollinger(data, period=20, stddev=2.0)
    
    assert isinstance(result, dict)
    assert 'middle' in result
    assert 'upper' in result
    assert 'lower' in result
    assert result['upper'] > result['middle'] > result['lower']
    
    series = bollinger(data, period=20, stddev=2.0, return_series=True)
    assert len(series) == len(data)


def test_vwap_basic():
    """Test VWAP calculation"""
    close = [100.0, 102.0, 104.0, 103.0, 105.0]
    volume = [1000, 1200, 1100, 1300, 1500]
    
    result = vwap(close, volume)
    assert isinstance(result, float)
    assert result > 0
    
    series = vwap(close, volume, return_series=True)
    assert len(series) == len(close)


def test_slope_basic():
    """Test slope calculation"""
    # Linear uptrend
    data = [100.0 + i * 2.0 for i in range(10)]
    result = slope(data, period=5)
    assert isinstance(result, float)
    assert result > 0  # Should be positive for uptrend
    
    series = slope(data, period=5, return_series=True)
    assert len(series) == len(data)


def test_hl2_basic():
    """Test HL2 calculation"""
    high = [105.0, 107.0, 106.0]
    low = [95.0, 97.0, 96.0]
    
    result = hl2(high, low)
    assert result == (106.0 + 96.0) / 2.0  # Last values
    
    series = hl2(high, low, return_series=True)
    assert len(series) == len(high)
    assert series[0] == (105.0 + 95.0) / 2.0


def test_hl3_basic():
    """Test HL3 calculation"""
    high = [105.0, 107.0, 106.0]
    low = [95.0, 97.0, 96.0]
    close = [100.0, 102.0, 101.0]
    
    result = hl3(high, low, close)
    assert result == (106.0 + 96.0 + 101.0) / 3.0  # Last values
    
    series = hl3(high, low, close, return_series=True)
    assert len(series) == len(high)


def run_all_tests():
    """Run all tests and report results"""
    tests = [
        test_ema_basic,
        test_sma_basic,
        test_rsi_basic,
        test_atr_basic,
        test_supertrend_basic,
        test_bollinger_basic,
        test_vwap_basic,
        test_slope_basic,
        test_hl2_basic,
        test_hl3_basic,
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
            failed += 1
    
    print(f"\nResults: {passed} passed, {failed} failed")
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
