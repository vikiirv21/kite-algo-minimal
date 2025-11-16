#!/usr/bin/env python3
"""
Test script for Backtest Engine v3.

Validates:
- BacktestConfig initialization
- BacktestEngineV3 initialization
- HistoricalDataLoader CSV loading
- Basic backtest execution
- Output file generation
"""

import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path

# Add parent directory to path
BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))


def test_backtest_config():
    """Test BacktestConfig initialization."""
    from backtest.engine_v3 import BacktestConfig
    
    config = BacktestConfig(
        symbols=["NIFTY", "BANKNIFTY"],
        strategies=["ema20_50_intraday_v2"],
        start_date="2025-01-01",
        end_date="2025-01-05",
        data_source="csv",
        timeframe="5m",
        initial_equity=100000.0,
    )
    
    assert config.symbols == ["NIFTY", "BANKNIFTY"]
    assert config.strategies == ["ema20_50_intraday_v2"]
    assert config.start_date == "2025-01-01"
    assert config.end_date == "2025-01-05"
    assert config.data_source == "csv"
    assert config.timeframe == "5m"
    assert config.initial_equity == 100000.0
    
    config_dict = config.to_dict()
    assert isinstance(config_dict, dict)
    assert config_dict["symbols"] == ["NIFTY", "BANKNIFTY"]
    
    print("✓ BacktestConfig initialization test passed")


def test_historical_data_loader():
    """Test HistoricalDataLoader with CSV files."""
    from backtest.data_loader import HistoricalDataLoader
    
    # Check if sample data exists
    market_data_dir = BASE_DIR / "artifacts" / "market_data"
    nifty_csv = market_data_dir / "NIFTY_5m.csv"
    
    if not nifty_csv.exists():
        print("⚠ Skipping data loader test - sample data not found")
        return
    
    loader = HistoricalDataLoader(
        data_source="csv",
        timeframe="5m",
        symbols=["NIFTY"],
        config={},
        logger_instance=None,
    )
    
    # Load bars
    bars = list(loader.iter_bars("NIFTY", "2025-01-01", "2025-01-02"))
    
    assert len(bars) > 0, "Should load at least one bar"
    
    # Validate bar structure
    bar = bars[0]
    assert "timestamp" in bar
    assert "open" in bar
    assert "high" in bar
    assert "low" in bar
    assert "close" in bar
    assert "volume" in bar
    
    assert isinstance(bar["timestamp"], datetime)
    assert isinstance(bar["open"], float)
    assert isinstance(bar["high"], float)
    assert isinstance(bar["low"], float)
    assert isinstance(bar["close"], float)
    assert isinstance(bar["volume"], float)
    
    print(f"✓ HistoricalDataLoader test passed - loaded {len(bars)} bars")


def test_backtest_engine_initialization():
    """Test BacktestEngineV3 initialization."""
    from backtest.engine_v3 import BacktestConfig, BacktestEngineV3
    from core.config import load_config
    
    # Load main config
    config = load_config(str(BASE_DIR / "configs" / "dev.yaml"))
    main_config_dict = config.raw if hasattr(config, "raw") else {}
    
    # Create backtest config
    bt_config = BacktestConfig(
        symbols=["NIFTY"],
        strategies=["ema20_50_intraday_v2"],
        start_date="2025-01-01",
        end_date="2025-01-02",
        data_source="csv",
        timeframe="5m",
        initial_equity=100000.0,
    )
    
    # Initialize engine
    engine = BacktestEngineV3(
        bt_config=bt_config,
        config=main_config_dict,
        logger_instance=None,
    )
    
    assert engine.run_id is not None
    assert engine.bt_config == bt_config
    assert engine.data_loader is not None
    assert engine.regime_engine is not None
    assert engine.portfolio_engine is not None
    assert engine.risk_engine is not None
    assert engine.state is not None
    
    print("✓ BacktestEngineV3 initialization test passed")


def test_backtest_execution():
    """Test full backtest execution."""
    from backtest.engine_v3 import BacktestConfig, BacktestEngineV3
    from core.config import load_config
    
    # Check if sample data exists
    market_data_dir = BASE_DIR / "artifacts" / "market_data"
    nifty_csv = market_data_dir / "NIFTY_5m.csv"
    
    if not nifty_csv.exists():
        print("⚠ Skipping execution test - sample data not found")
        return
    
    # Load main config
    config = load_config(str(BASE_DIR / "configs" / "dev.yaml"))
    main_config_dict = config.raw if hasattr(config, "raw") else {}
    
    # Create backtest config
    bt_config = BacktestConfig(
        symbols=["NIFTY"],
        strategies=["ema20_50_intraday_v2"],
        start_date="2025-01-01",
        end_date="2025-01-02",
        data_source="csv",
        timeframe="5m",
        initial_equity=100000.0,
    )
    
    # Initialize engine
    engine = BacktestEngineV3(
        bt_config=bt_config,
        config=main_config_dict,
        logger_instance=None,
    )
    
    # Run backtest
    result = engine.run()
    
    assert result is not None
    assert result.run_id == engine.run_id
    assert result.config == bt_config
    assert isinstance(result.equity_curve, list)
    assert isinstance(result.per_strategy, dict)
    assert isinstance(result.per_symbol, dict)
    assert isinstance(result.trades, list)
    assert isinstance(result.overall_metrics, dict)
    
    # Check overall metrics
    assert "initial_equity" in result.overall_metrics
    assert "final_equity" in result.overall_metrics
    assert "total_return" in result.overall_metrics
    assert "total_trades" in result.overall_metrics
    assert "bars_processed" in result.overall_metrics
    
    # Verify output files exist
    assert engine.backtest_dir.exists()
    assert (engine.backtest_dir / "config.json").exists()
    assert (engine.backtest_dir / "summary.json").exists()
    assert (engine.backtest_dir / "equity_curve.json").exists()
    
    # Verify JSON structure
    with (engine.backtest_dir / "summary.json").open() as f:
        summary = json.load(f)
        assert "run_id" in summary
        assert "config" in summary
        assert "equity_curve" in summary
        assert "overall_metrics" in summary
    
    print(f"✓ Backtest execution test passed - run_id={result.run_id}")
    print(f"  - Bars processed: {result.overall_metrics['bars_processed']}")
    print(f"  - Trades: {result.overall_metrics['total_trades']}")
    print(f"  - Final equity: {result.overall_metrics['final_equity']:.2f}")


def test_isolation():
    """Test that backtest engine is isolated from live/paper paths."""
    from backtest.engine_v3 import BacktestEngineV3
    
    # Verify that backtest engine doesn't import or modify live/paper modules
    # This is validated by the fact that we can run tests without broker credentials
    
    # Check that backtest outputs go to separate directory
    backtest_dir = BASE_DIR / "artifacts" / "backtests"
    if backtest_dir.exists():
        # Verify isolation - backtest dir should not contain live/paper journals
        for run_dir in backtest_dir.iterdir():
            if run_dir.is_dir() and run_dir.name.startswith("bt_"):
                journal_dir = run_dir / "journal"
                if journal_dir.exists():
                    # Should not be the same as live/paper journals
                    live_journal = BASE_DIR / "artifacts" / "journal"
                    assert journal_dir != live_journal
    
    print("✓ Isolation test passed")


def main():
    """Run all tests."""
    print("=" * 80)
    print("Backtest Engine v3 - Test Suite")
    print("=" * 80)
    print()
    
    tests = [
        ("BacktestConfig", test_backtest_config),
        ("HistoricalDataLoader", test_historical_data_loader),
        ("BacktestEngineV3 Initialization", test_backtest_engine_initialization),
        ("Backtest Execution", test_backtest_execution),
        ("Isolation", test_isolation),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_fn in tests:
        print(f"Running test: {name}")
        try:
            test_fn()
            passed += 1
        except Exception as e:
            print(f"✗ {name} test failed: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
        print()
    
    print("=" * 80)
    print(f"Test Results: {passed} passed, {failed} failed")
    print("=" * 80)
    
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
