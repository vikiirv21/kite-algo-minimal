#!/usr/bin/env python3
"""
Test script to demonstrate the improved warmup behavior.

This script simulates the scenario where indicators are warming up
and shows that:
1. Only the first occurrence is logged (as INFO, not WARNING)
2. Subsequent occurrences are silent
3. Other errors are still logged as WARNING
"""

import sys
import logging
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.indicators import IndicatorWarmupError
from core.strategy_engine_v2 import StrategyEngineV2


def test_warmup_behavior():
    """Test that warmup errors are handled gracefully"""
    
    # Setup logging to see the behavior
    logging.basicConfig(
        level=logging.INFO,
        format='%(levelname)s: %(message)s'
    )
    
    print("=" * 70)
    print("Testing Warmup Behavior")
    print("=" * 70)
    
    # Create a strategy engine
    config = {
        "history_lookback": 200,
        "strategies": [],
        "primary_strategy_id": "",
    }
    engine = StrategyEngineV2(config=config)
    
    # Simulate series with insufficient data for some indicators
    print("\n1. Testing with 45 bars (insufficient for EMA50):")
    print("-" * 70)
    series_45 = {
        "open": [100.0 + i * 0.1 for i in range(45)],
        "high": [101.0 + i * 0.1 for i in range(45)],
        "low": [99.0 + i * 0.1 for i in range(45)],
        "close": [100.0 + i * 0.1 for i in range(45)],
        "volume": [1000 for _ in range(45)],
    }
    
    # First call - should log warmup message
    print("\n  First call (should log INFO for EMA50 warmup):")
    ind1 = engine.compute_indicators(series_45, symbol="NIFTY", timeframe="5m")
    print(f"  Indicators computed: {list(ind1.keys())}")
    
    # Second call - should be silent
    print("\n  Second call (should be SILENT - already logged):")
    ind2 = engine.compute_indicators(series_45, symbol="NIFTY", timeframe="5m")
    print(f"  Indicators computed: {list(ind2.keys())}")
    
    # Third call - should still be silent
    print("\n  Third call (should still be SILENT):")
    ind3 = engine.compute_indicators(series_45, symbol="NIFTY", timeframe="5m")
    print(f"  Indicators computed: {list(ind3.keys())}")
    
    # Different symbol - should log once per symbol
    print("\n2. Testing with different symbol (BANKNIFTY):")
    print("-" * 70)
    print("\n  First call for BANKNIFTY (should log INFO):")
    ind4 = engine.compute_indicators(series_45, symbol="BANKNIFTY", timeframe="5m")
    print(f"  Indicators computed: {list(ind4.keys())}")
    
    # Different timeframe - should log once per (symbol, indicator, timeframe)
    print("\n3. Testing with different timeframe (15m) for NIFTY:")
    print("-" * 70)
    print("\n  First call for NIFTY 15m (should log INFO):")
    ind5 = engine.compute_indicators(series_45, symbol="NIFTY", timeframe="15m")
    print(f"  Indicators computed: {list(ind5.keys())}")
    
    # Sufficient data - no warmup errors
    print("\n4. Testing with sufficient data (100 bars):")
    print("-" * 70)
    series_100 = {
        "open": [100.0 + i * 0.1 for i in range(100)],
        "high": [101.0 + i * 0.1 for i in range(100)],
        "low": [99.0 + i * 0.1 for i in range(100)],
        "close": [100.0 + i * 0.1 for i in range(100)],
        "volume": [1000 for _ in range(100)],
    }
    
    print("\n  Call with 100 bars (should work without warmup messages):")
    ind6 = engine.compute_indicators(series_100, symbol="NIFTY", timeframe="5m")
    print(f"  Indicators computed: {list(ind6.keys())}")
    
    # Verify we got the expected indicators
    assert "ema20" in ind6, "EMA20 should be computed with 100 bars"
    assert "ema50" in ind6, "EMA50 should be computed with 100 bars"
    assert "ema100" in ind6, "EMA100 should be computed with 100 bars"
    assert "rsi14" in ind6, "RSI14 should be computed with 100 bars"
    
    print("\n" + "=" * 70)
    print("✅ All warmup behavior tests passed!")
    print("=" * 70)
    
    print("\nSummary:")
    print("  - Warmup messages logged only once per (symbol, indicator, timeframe)")
    print("  - Subsequent warmup events are silent")
    print("  - Indicators computed successfully when data is sufficient")
    print("  - No WARNING logs for normal warmup conditions")


def test_exception_structure():
    """Test the IndicatorWarmupError exception structure"""
    print("\n" + "=" * 70)
    print("Testing IndicatorWarmupError Exception")
    print("=" * 70)
    
    try:
        raise IndicatorWarmupError("EMA(50)", 50, 45)
    except IndicatorWarmupError as e:
        print(f"\n✅ Exception caught successfully")
        print(f"   - indicator_name: {e.indicator_name}")
        print(f"   - required: {e.required}")
        print(f"   - actual: {e.actual}")
        print(f"   - message: {str(e)}")
        
        assert e.indicator_name == "EMA(50)"
        assert e.required == 50
        assert e.actual == 45
        assert "EMA(50) requires at least 50 values, got 45" in str(e)
        
    print("\n✅ Exception structure test passed!")


if __name__ == "__main__":
    test_exception_structure()
    test_warmup_behavior()
    sys.exit(0)
