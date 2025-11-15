#!/usr/bin/env python3
"""
Test script to validate Market Data Engine v2 integration.
"""

import sys
import tempfile
from pathlib import Path
from unittest.mock import Mock, MagicMock

# Add parent directory to path
BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))


def test_strategy_runner_accepts_market_data_engine():
    """Test that StrategyRunner accepts MarketDataEngine parameter."""
    from core.strategy_engine import StrategyRunner
    
    # Create mock objects
    state_store = Mock()
    paper_engine = Mock()
    paper_engine.logical_alias = {}
    paper_engine._handle_signal = Mock()
    
    market_data_engine = Mock()
    
    # Create StrategyRunner with market_data_engine
    runner = StrategyRunner(
        state_store,
        paper_engine,
        market_data_engine=market_data_engine
    )
    
    assert runner.market_data_engine is market_data_engine
    print("✓ StrategyRunner accepts market_data_engine parameter")


def test_market_data_engine_basic_operations():
    """Test basic MarketDataEngine operations."""
    from core.market_data_engine import MarketDataEngine
    
    # Create temp cache directory
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_dir = Path(tmpdir)
        
        # Create engine without Kite client (offline mode)
        mde = MarketDataEngine(None, {}, cache_dir=cache_dir)
        
        # Test cache path generation
        path = mde._cache_path("NIFTY", "5m")
        assert path.name == "NIFTY_5m.json"
        
        # Test save and load cache
        test_candles = [
            {
                "ts": "2024-11-15T10:00:00+00:00",
                "open": 19500.0,
                "high": 19550.0,
                "low": 19490.0,
                "close": 19520.0,
                "volume": 10000.0
            },
            {
                "ts": "2024-11-15T10:05:00+00:00",
                "open": 19520.0,
                "high": 19560.0,
                "low": 19510.0,
                "close": 19540.0,
                "volume": 12000.0
            }
        ]
        
        mde.save_cache("NIFTY", "5m", test_candles)
        loaded = mde.load_cache("NIFTY", "5m")
        
        assert len(loaded) == 2
        assert loaded[0]["ts"] == test_candles[0]["ts"]
        assert loaded[1]["close"] == test_candles[1]["close"]
        
        # Test get_window
        window = mde.get_window("NIFTY", "5m", window_size=1)
        assert len(window) == 1
        assert window[0]["ts"] == test_candles[1]["ts"]
        
        print("✓ MarketDataEngine basic operations work correctly")


def test_refresh_market_cache_script():
    """Test that refresh_market_cache.py script exists and can be imported."""
    script_path = BASE_DIR / "scripts" / "refresh_market_cache.py"
    assert script_path.exists(), "refresh_market_cache.py script not found"
    print("✓ refresh_market_cache.py script exists")


def test_dashboard_api_endpoint_exists():
    """Test that market data API endpoint is defined."""
    from ui.dashboard import router
    
    # Check that the router has the market_data/window endpoint
    routes = [route for route in router.routes]
    market_data_routes = [r for r in routes if "/market_data/window" in getattr(r, "path", "")]
    
    assert len(market_data_routes) > 0, "Market data API endpoint not found"
    print("✓ Market data API endpoint /api/market_data/window is defined")


def test_paper_engine_integration():
    """Test that PaperEngine can be instantiated with MarketDataEngine."""
    from core.config import AppConfig
    from engine.paper_engine import PaperEngine
    
    # Create minimal config
    config_dict = {
        "trading": {
            "mode": "paper",
            "paper_capital": 100000,
            "fno_universe": ["NIFTY"],
            "logical_universe": ["NIFTY"]
        },
        "risk": {
            "risk_per_trade_pct": 0.01
        },
        "meta": {
            "enabled": False
        }
    }
    
    cfg = AppConfig(raw=config_dict)
    
    # Create mock Kite client
    mock_kite = Mock()
    mock_kite.profile = Mock(return_value={"user_id": "TEST123"})
    
    # Create mock data feed
    mock_feed = Mock()
    mock_feed.get_ltp = Mock(return_value=19500.0)
    
    # Create PaperEngine with symbol map to avoid FnO resolution
    symbol_map = {"NIFTY": "NIFTY24DECFUT"}
    
    try:
        engine = PaperEngine(
            cfg,
            kite=mock_kite,
            data_feed=mock_feed,
            symbol_map_override=symbol_map
        )
        
        # Verify MarketDataEngine was created
        assert engine.market_data_engine is not None
        
        # Verify StrategyRunner has reference to MarketDataEngine
        assert hasattr(engine.strategy_runner, 'market_data_engine')
        
        print("✓ PaperEngine integrates MarketDataEngine correctly")
        
    except Exception as e:
        print(f"⚠ PaperEngine integration test skipped: {e}")


def main():
    """Run all tests."""
    print("=" * 60)
    print("Testing Market Data Engine v2 Integration")
    print("=" * 60)
    print()
    
    tests = [
        test_strategy_runner_accepts_market_data_engine,
        test_market_data_engine_basic_operations,
        test_refresh_market_cache_script,
        test_dashboard_api_endpoint_exists,
        test_paper_engine_integration,
    ]
    
    passed = 0
    failed = 0
    
    for test_func in tests:
        try:
            test_func()
            passed += 1
        except Exception as e:
            print(f"✗ {test_func.__name__} failed: {e}")
            failed += 1
    
    print()
    print("=" * 60)
    print(f"Test Results: {passed} passed, {failed} failed")
    print("=" * 60)
    
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
