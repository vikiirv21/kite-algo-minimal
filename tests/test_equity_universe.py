#!/usr/bin/env python3
"""
Test script to verify equity universe filtering implementation.

This script tests:
1. Loading NIFTY50 and NIFTY100 lists
2. build_equity_universe() with different configurations
3. Deduplication and sorting
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add project root to path
BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from data.universe.nifty_lists import (
    NIFTY50,
    NIFTY100,
    get_equity_universe_from_indices,
)


def test_nifty_lists():
    """Test that NIFTY lists are properly defined."""
    print("=" * 80)
    print("TEST: NIFTY Lists")
    print("=" * 80)
    
    print(f"\nNIFTY50 contains {len(NIFTY50)} stocks")
    print(f"Sample NIFTY50 stocks: {NIFTY50[:5]}")
    
    print(f"\nNIFTY100 contains {len(NIFTY100)} stocks")
    print(f"Sample NIFTY100 stocks: {NIFTY100[:5]}")
    
    # Verify NIFTY50 is subset of NIFTY100
    nifty50_set = set(NIFTY50)
    nifty100_set = set(NIFTY100)
    
    assert nifty50_set.issubset(nifty100_set), "NIFTY50 should be subset of NIFTY100"
    print("\n✓ NIFTY50 is a subset of NIFTY100")
    
    # Verify no duplicates
    assert len(NIFTY50) == len(nifty50_set), "NIFTY50 contains duplicates"
    assert len(NIFTY100) == len(nifty100_set), "NIFTY100 contains duplicates"
    print("✓ No duplicates in NIFTY lists")
    
    print("\n✓ NIFTY lists test PASSED\n")


def test_get_equity_universe_from_indices():
    """Test the get_equity_universe_from_indices function."""
    print("=" * 80)
    print("TEST: get_equity_universe_from_indices()")
    print("=" * 80)
    
    # Test with NIFTY50 only
    universe_50 = get_equity_universe_from_indices(["NIFTY50"])
    print(f"\nNIFTY50 universe: {len(universe_50)} symbols")
    print(f"Sample: {universe_50[:5]}")
    assert len(universe_50) == len(NIFTY50), "NIFTY50 universe size mismatch"
    assert universe_50 == sorted(universe_50), "Universe should be sorted"
    print("✓ NIFTY50 universe correctly generated and sorted")
    
    # Test with NIFTY100 only
    universe_100 = get_equity_universe_from_indices(["NIFTY100"])
    print(f"\nNIFTY100 universe: {len(universe_100)} symbols")
    print(f"Sample: {universe_100[:5]}")
    assert len(universe_100) == len(NIFTY100), "NIFTY100 universe size mismatch"
    assert universe_100 == sorted(universe_100), "Universe should be sorted"
    print("✓ NIFTY100 universe correctly generated and sorted")
    
    # Test with both (should be same as NIFTY100 due to deduplication)
    universe_both = get_equity_universe_from_indices(["NIFTY50", "NIFTY100"])
    print(f"\nNIFTY50 + NIFTY100 universe: {len(universe_both)} symbols")
    assert len(universe_both) == len(NIFTY100), "Combined universe should equal NIFTY100"
    assert universe_both == universe_100, "Combined should be same as NIFTY100"
    print("✓ Deduplication works correctly")
    
    # Test with empty list
    universe_empty = get_equity_universe_from_indices([])
    assert len(universe_empty) == 0, "Empty indices should return empty universe"
    print("✓ Empty indices handled correctly")
    
    # Test case insensitivity
    universe_lower = get_equity_universe_from_indices(["nifty50"])
    assert universe_lower == universe_50, "Should be case insensitive"
    print("✓ Case insensitivity works")
    
    print("\n✓ get_equity_universe_from_indices() test PASSED\n")


def test_build_equity_universe_mock():
    """Test build_equity_universe with mock configurations."""
    print("=" * 80)
    print("TEST: build_equity_universe() with mock config")
    print("=" * 80)
    
    # Import the function
    from core.scanner import build_equity_universe
    
    # Mock Kite client (we won't actually call it)
    class MockKite:
        def ltp(self, instruments):
            # Return mock LTP data
            return {inst: {"last_price": 150.0} for inst in instruments}
    
    mock_kite = MockKite()
    
    # Test nifty_lists mode
    config_nifty = {
        "trading": {
            "equity_universe_config": {
                "mode": "nifty_lists",
                "include_indices": ["NIFTY50"],
                "max_symbols": 30,
                "min_price": None,  # Skip price filter for this test
            }
        }
    }
    
    universe = build_equity_universe(config_nifty, mock_kite)
    print(f"\nNIFTY50 with max_symbols=30: {len(universe)} symbols")
    assert len(universe) == 30, f"Expected 30 symbols, got {len(universe)}"
    print(f"Sample: {universe[:5]}")
    print("✓ max_symbols cap works correctly")
    
    # Test fallback mode (should use load_equity_universe)
    config_fallback = {
        "trading": {
            "equity_universe_config": {
                "mode": "all",
            }
        }
    }
    
    universe_fallback = build_equity_universe(config_fallback, mock_kite)
    print(f"\nFallback mode: {len(universe_fallback)} symbols")
    print(f"Sample: {universe_fallback[:3]}")
    print("✓ Fallback mode works")
    
    print("\n✓ build_equity_universe() test PASSED\n")


def main():
    """Run all tests."""
    print("\n" + "=" * 80)
    print("EQUITY UNIVERSE FILTERING - TEST SUITE")
    print("=" * 80 + "\n")
    
    try:
        test_nifty_lists()
        test_get_equity_universe_from_indices()
        test_build_equity_universe_mock()
        
        print("=" * 80)
        print("ALL TESTS PASSED ✓")
        print("=" * 80)
        print("\nEquity universe filtering implementation is working correctly!")
        print("\nNext steps:")
        print("1. Run the scanner to generate universe.json")
        print("2. Start equity engine: python -m scripts.run_day --mode paper --engines equity")
        print("3. Check logs for 'Equity universe loaded' message")
        
        return 0
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
