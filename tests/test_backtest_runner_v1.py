#!/usr/bin/env python3
"""
Test script for Backtest Runner v1 validation.
"""

import sys
import tempfile
from pathlib import Path
from datetime import datetime
from unittest.mock import Mock

# Add parent directory to path
BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))


def test_backtest_engine_initialization():
    """Test BacktestEngine can be initialized."""
    from scripts.run_backtest_v1 import BacktestEngine
    from core.config import load_config
    from core.market_data_engine import MarketDataEngine
    from core.universe_builder import load_universe
    
    cfg = load_config('configs/dev.yaml')
    universe = load_universe()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        mde = MarketDataEngine(None, universe, cache_dir=Path(tmpdir))
        
        engine = BacktestEngine(
            cfg=cfg,
            capital=100000,
            symbol='TEST',
            logical_name='TEST',
            strategy_code='ema20_50_intraday',
            default_qty=1,
            market_data_engine=mde,
        )
        
        assert engine.symbol == 'TEST'
        assert engine.capital == 100000
        assert engine.default_qty == 1
        
    print("✓ BacktestEngine initialization test passed")


def test_symbol_resolution():
    """Test symbol resolution logic."""
    from scripts.run_backtest_v1 import resolve_symbol
    
    # Test with logical symbol
    resolved = resolve_symbol('NIFTY')
    assert resolved is not None
    assert isinstance(resolved, str)
    
    print(f"✓ Symbol resolution test passed: NIFTY -> {resolved}")


def test_candle_processing():
    """Test candle processing logic."""
    from scripts.run_backtest_v1 import BacktestEngine
    from core.config import load_config
    from core.market_data_engine import MarketDataEngine
    from core.universe_builder import load_universe
    
    cfg = load_config('configs/dev.yaml')
    universe = load_universe()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        mde = MarketDataEngine(None, universe, cache_dir=Path(tmpdir))
        
        engine = BacktestEngine(
            cfg=cfg,
            capital=100000,
            symbol='TEST',
            logical_name='TEST',
            strategy_code='ema20_50_intraday',
            default_qty=1,
            market_data_engine=mde,
        )
        
        # Mock candle
        candle = {
            'ts': '2024-01-01T10:00:00+00:00',
            'open': 100.0,
            'high': 105.0,
            'low': 95.0,
            'close': 102.0,
            'volume': 1000.0
        }
        
        # Process candle (should not raise)
        engine._process_candle(candle)
        
        # Check timestamp was set
        assert engine.current_timestamp is not None
        
    print("✓ Candle processing test passed")


def test_result_building():
    """Test result building logic."""
    from scripts.run_backtest_v1 import BacktestEngine
    from core.config import load_config
    from core.market_data_engine import MarketDataEngine
    from core.universe_builder import load_universe
    
    cfg = load_config('configs/dev.yaml')
    universe = load_universe()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        mde = MarketDataEngine(None, universe, cache_dir=Path(tmpdir))
        
        engine = BacktestEngine(
            cfg=cfg,
            capital=100000,
            symbol='TEST',
            logical_name='TEST',
            strategy_code='ema20_50_intraday',
            default_qty=1,
            market_data_engine=mde,
        )
        
        # Build result
        result = engine.build_result(
            timeframe='5m',
            from_date='2024-01-01',
            to_date='2024-01-31',
        )
        
        # Validate structure
        assert 'strategy' in result
        assert 'config' in result
        assert 'summary' in result
        assert 'equity_curve' in result
        assert 'trades' in result
        
        # Validate summary fields
        summary = result['summary']
        assert 'total_pnl' in summary
        assert 'win_rate' in summary
        assert 'total_trades' in summary
        assert 'max_drawdown' in summary
        
    print("✓ Result building test passed")


def test_cli_argument_parsing():
    """Test CLI argument parsing."""
    import sys
    from scripts.run_backtest_v1 import parse_args
    
    # Mock sys.argv
    original_argv = sys.argv
    try:
        sys.argv = [
            'run_backtest_v1.py',
            '--strategy', 'ema20_50_intraday',
            '--symbol', 'NIFTY',
            '--from', '2024-01-01',
            '--to', '2024-01-31',
            '--timeframe', '5m',
            '--capital', '500000',
            '--qty', '2',
        ]
        
        args = parse_args()
        
        assert args.strategy == 'ema20_50_intraday'
        assert args.symbol == 'NIFTY'
        assert args.from_date == '2024-01-01'
        assert args.to_date == '2024-01-31'
        assert args.timeframe == '5m'
        assert args.capital == 500000.0
        assert args.qty == 2
        
    finally:
        sys.argv = original_argv
    
    print("✓ CLI argument parsing test passed")


def main():
    """Run all tests."""
    print("=" * 60)
    print("Testing Backtest Runner v1")
    print("=" * 60)
    print()
    
    tests = [
        test_backtest_engine_initialization,
        test_symbol_resolution,
        test_candle_processing,
        test_result_building,
        test_cli_argument_parsing,
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
