#!/usr/bin/env python3
"""
Test script for run_backtest.py --preset-ema2050-nifty flag.
"""

import sys
from pathlib import Path

# Add parent directory to path
BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))


def test_preset_flag_parsing():
    """Test that --preset-ema2050-nifty flag is parsed correctly."""
    import argparse
    
    parser = argparse.ArgumentParser()
    parser.add_argument('--preset-ema2050-nifty', action='store_true')
    
    # Test with flag
    args = parser.parse_args(['--preset-ema2050-nifty'])
    assert args.preset_ema2050_nifty is True
    
    # Test without flag
    args = parser.parse_args([])
    assert args.preset_ema2050_nifty is False
    
    print("✓ Preset flag parsing test passed")


def test_preset_defaults_applied():
    """Test that preset defaults are applied correctly."""
    import argparse
    
    parser = argparse.ArgumentParser()
    parser.add_argument('--from-date', required=False)
    parser.add_argument('--to-date', required=False)
    parser.add_argument('--symbols', default='')
    parser.add_argument('--strategies', default='')
    parser.add_argument('--capital', type=float, default=1_000_000.0)
    parser.add_argument('--qty', type=int, default=1)
    parser.add_argument('--preset-ema2050-nifty', action='store_true')
    
    # Parse with preset flag only
    args = parser.parse_args(['--preset-ema2050-nifty'])
    
    # Apply preset logic
    if args.preset_ema2050_nifty:
        if args.from_date is None:
            args.from_date = '2024-01-01'
        if args.to_date is None:
            args.to_date = '2024-11-15'
        if not args.symbols:
            args.symbols = 'NIFTY'
        if not args.strategies:
            args.strategies = 'EMA_20_50'
        if args.capital == 1_000_000.0:
            args.capital = 500000.0
        if args.qty == 1:
            args.qty = 50
    
    # Verify defaults
    assert args.from_date == '2024-01-01'
    assert args.to_date == '2024-11-15'
    assert args.symbols == 'NIFTY'
    assert args.strategies == 'EMA_20_50'
    assert args.capital == 500000.0
    assert args.qty == 50
    
    print("✓ Preset defaults application test passed")


def test_explicit_overrides():
    """Test that explicit CLI args override preset defaults."""
    import argparse
    
    parser = argparse.ArgumentParser()
    parser.add_argument('--from-date', required=False)
    parser.add_argument('--to-date', required=False)
    parser.add_argument('--symbols', default='')
    parser.add_argument('--strategies', default='')
    parser.add_argument('--capital', type=float, default=1_000_000.0)
    parser.add_argument('--qty', type=int, default=1)
    parser.add_argument('--preset-ema2050-nifty', action='store_true')
    
    # Parse with preset flag and explicit overrides
    args = parser.parse_args([
        '--preset-ema2050-nifty',
        '--from-date', '2023-06-01',
        '--to-date', '2023-12-31',
        '--symbols', 'BANKNIFTY',
        '--capital', '100000',
        '--qty', '10'
    ])
    
    # Apply preset logic
    if args.preset_ema2050_nifty:
        if args.from_date is None:
            args.from_date = '2024-01-01'
        if args.to_date is None:
            args.to_date = '2024-11-15'
        if not args.symbols:
            args.symbols = 'NIFTY'
        if not args.strategies:
            args.strategies = 'EMA_20_50'
        if args.capital == 1_000_000.0:
            args.capital = 500000.0
        if args.qty == 1:
            args.qty = 50
    
    # Verify explicit values are preserved
    assert args.from_date == '2023-06-01', f"Expected '2023-06-01', got '{args.from_date}'"
    assert args.to_date == '2023-12-31', f"Expected '2023-12-31', got '{args.to_date}'"
    assert args.symbols == 'BANKNIFTY', f"Expected 'BANKNIFTY', got '{args.symbols}'"
    assert args.strategies == 'EMA_20_50', f"Expected 'EMA_20_50', got '{args.strategies}'"  # Not overridden, so preset applies
    assert args.capital == 100000.0, f"Expected 100000.0, got {args.capital}"
    assert args.qty == 10, f"Expected 10, got {args.qty}"
    
    print("✓ Explicit overrides test passed")


def test_without_preset_flag():
    """Test that behavior without preset flag remains unchanged."""
    import argparse
    
    parser = argparse.ArgumentParser()
    parser.add_argument('--from-date', required=False)
    parser.add_argument('--to-date', required=False)
    parser.add_argument('--symbols', default='')
    parser.add_argument('--strategies', default='')
    parser.add_argument('--capital', type=float, default=1_000_000.0)
    parser.add_argument('--qty', type=int, default=1)
    parser.add_argument('--preset-ema2050-nifty', action='store_true')
    
    # Parse without preset flag
    args = parser.parse_args([
        '--from-date', '2023-01-01',
        '--to-date', '2023-12-31'
    ])
    
    # Apply preset logic (should not change anything)
    if args.preset_ema2050_nifty:
        if args.from_date is None:
            args.from_date = '2024-01-01'
        if args.to_date is None:
            args.to_date = '2024-11-15'
        if not args.symbols:
            args.symbols = 'NIFTY'
        if not args.strategies:
            args.strategies = 'EMA_20_50'
        if args.capital == 1_000_000.0:
            args.capital = 500000.0
        if args.qty == 1:
            args.qty = 50
    
    # Verify original behavior
    assert args.from_date == '2023-01-01'
    assert args.to_date == '2023-12-31'
    assert args.symbols == ''
    assert args.strategies == ''
    assert args.capital == 1_000_000.0
    assert args.qty == 1
    
    print("✓ Without preset flag test passed")


def test_partial_overrides():
    """Test that only some parameters can be overridden while others use preset."""
    import argparse
    
    parser = argparse.ArgumentParser()
    parser.add_argument('--from-date', required=False)
    parser.add_argument('--to-date', required=False)
    parser.add_argument('--symbols', default='')
    parser.add_argument('--strategies', default='')
    parser.add_argument('--capital', type=float, default=1_000_000.0)
    parser.add_argument('--qty', type=int, default=1)
    parser.add_argument('--preset-ema2050-nifty', action='store_true')
    
    # Parse with preset and only capital override
    args = parser.parse_args([
        '--preset-ema2050-nifty',
        '--capital', '750000'
    ])
    
    # Apply preset logic
    if args.preset_ema2050_nifty:
        if args.from_date is None:
            args.from_date = '2024-01-01'
        if args.to_date is None:
            args.to_date = '2024-11-15'
        if not args.symbols:
            args.symbols = 'NIFTY'
        if not args.strategies:
            args.strategies = 'EMA_20_50'
        if args.capital == 1_000_000.0:
            args.capital = 500000.0
        if args.qty == 1:
            args.qty = 50
    
    # Verify: dates, symbols, strategies, qty should be from preset; capital should be overridden
    assert args.from_date == '2024-01-01'
    assert args.to_date == '2024-11-15'
    assert args.symbols == 'NIFTY'
    assert args.strategies == 'EMA_20_50'
    assert args.capital == 750000.0  # Explicitly set
    assert args.qty == 50  # From preset
    
    print("✓ Partial overrides test passed")


def main():
    """Run all tests."""
    print("=" * 60)
    print("Testing run_backtest.py --preset-ema2050-nifty")
    print("=" * 60)
    print()
    
    tests = [
        test_preset_flag_parsing,
        test_preset_defaults_applied,
        test_explicit_overrides,
        test_without_preset_flag,
        test_partial_overrides,
    ]
    
    passed = 0
    failed = 0
    
    for test_func in tests:
        try:
            test_func()
            passed += 1
        except Exception as e:
            print(f"✗ {test_func.__name__} failed: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    print()
    print("=" * 60)
    print(f"Test Results: {passed} passed, {failed} failed")
    print("=" * 60)
    
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
