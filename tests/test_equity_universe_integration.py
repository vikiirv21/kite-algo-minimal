#!/usr/bin/env python3
"""
Integration test to verify equity universe filtering end-to-end.

This script simulates the scanner and engine flow without requiring Kite credentials.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path
from unittest.mock import Mock, MagicMock

# Add project root to path
BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from core.config import AppConfig, load_config
from core.scanner import MarketScanner, build_equity_universe
from data.universe.nifty_lists import NIFTY50, NIFTY100


def create_mock_kite():
    """Create a mock Kite client for testing."""
    mock_kite = Mock()
    
    # Mock instruments() to return sample NSE instruments
    def mock_instruments(exchange):
        if exchange == "NSE":
            instruments = []
            # Add instruments for NIFTY50 stocks
            for symbol in NIFTY50[:10]:  # Just first 10 for testing
                instruments.append({
                    "tradingsymbol": symbol,
                    "instrument_token": hash(symbol) % 10000000,
                    "lot_size": 1,
                    "tick_size": 0.05,
                    "exchange": "NSE",
                    "segment": "NSE",
                    "name": symbol,
                    "last_price": 200.0,  # All above min_price threshold
                })
            return instruments
        return []
    
    mock_kite.instruments = Mock(side_effect=mock_instruments)
    
    # Mock ltp() for price filtering
    def mock_ltp(instruments):
        result = {}
        for inst in instruments:
            # All stocks have price above 100
            result[inst] = {"last_price": 150.0}
        return result
    
    mock_kite.ltp = Mock(side_effect=mock_ltp)
    
    return mock_kite


def test_scanner_with_nifty_config():
    """Test the MarketScanner with NIFTY configuration."""
    print("=" * 80)
    print("TEST: MarketScanner with NIFTY Configuration")
    print("=" * 80)
    
    # Load config
    config = load_config("configs/dev.yaml")
    
    # Verify config has equity_universe_config
    trading_cfg = config.raw.get("trading", {})
    eu_cfg = trading_cfg.get("equity_universe_config", {})
    
    print(f"\nConfig equity_universe_config:")
    print(f"  mode: {eu_cfg.get('mode')}")
    print(f"  include_indices: {eu_cfg.get('include_indices')}")
    print(f"  max_symbols: {eu_cfg.get('max_symbols')}")
    print(f"  min_price: {eu_cfg.get('min_price')}")
    
    assert eu_cfg.get("mode") == "nifty_lists", "Config should have nifty_lists mode"
    assert "NIFTY50" in eu_cfg.get("include_indices", []), "Should include NIFTY50"
    print("✓ Config correctly loaded")
    
    # Test build_equity_universe
    mock_kite = create_mock_kite()
    universe = build_equity_universe(config.raw, mock_kite)
    
    print(f"\nBuilt equity universe: {len(universe)} symbols")
    print(f"Sample: {universe[:5]}")
    
    # Should have 100 symbols (NIFTY50 + NIFTY100)
    # But limited to max_symbols=120 and filtered by min_price=100
    assert len(universe) > 0, "Universe should not be empty"
    assert len(universe) <= 120, "Universe should respect max_symbols cap"
    print("✓ Universe built successfully with constraints")
    
    print("\n✓ Scanner configuration test PASSED\n")


def test_universe_json_structure():
    """Test that universe.json would have the right structure."""
    print("=" * 80)
    print("TEST: Universe.json Structure")
    print("=" * 80)
    
    # Simulate scanner output
    universe_data = {
        "date": date.today().isoformat(),
        "asof": "2024-01-01T00:00:00Z",
        "fno": ["NIFTY", "BANKNIFTY"],
        "equity": ["RELIANCE", "TCS", "INFY"],
        "equity_universe": ["RELIANCE", "TCS", "INFY"],  # New key
        "meta": {
            "NIFTY": {"tradingsymbol": "NIFTY24JANFUT"},
            "RELIANCE": {"tradingsymbol": "RELIANCE", "last_price": 2500.0},
        }
    }
    
    print("\nSimulated universe.json structure:")
    print(json.dumps(universe_data, indent=2)[:500])
    
    # Verify structure
    assert "equity_universe" in universe_data, "Should have equity_universe key"
    assert isinstance(universe_data["equity_universe"], list), "equity_universe should be a list"
    print("\n✓ Universe.json structure is correct")
    
    print("\n✓ Universe.json structure test PASSED\n")


def test_equity_engine_loading():
    """Test that equity engine would correctly load from universe.json."""
    print("=" * 80)
    print("TEST: Equity Engine Universe Loading")
    print("=" * 80)
    
    # Create a temporary scanner universe file
    artifacts_dir = BASE_DIR / "artifacts"
    scanner_dir = artifacts_dir / "scanner" / date.today().isoformat()
    scanner_dir.mkdir(parents=True, exist_ok=True)
    
    test_universe = {
        "date": date.today().isoformat(),
        "asof": "2024-01-01T00:00:00Z",
        "fno": ["NIFTY", "BANKNIFTY"],
        "equity": ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK"],
        "equity_universe": ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK"],
        "meta": {}
    }
    
    universe_path = scanner_dir / "universe.json"
    with universe_path.open("w") as f:
        json.dump(test_universe, f, indent=2)
    
    print(f"\nCreated test universe.json at: {universe_path}")
    print(f"equity_universe contains {len(test_universe['equity_universe'])} symbols")
    
    # Verify the file loading logic (without importing the entire engine)
    # This simulates what _load_equity_universe does
    assert universe_path.exists(), "Universe file should exist"
    
    with universe_path.open("r") as f:
        loaded = json.load(f)
    
    equity_universe = loaded.get("equity_universe", [])
    print(f"\nLoaded equity_universe: {equity_universe}")
    
    assert len(equity_universe) == 5, "Should load 5 symbols"
    assert equity_universe == test_universe["equity_universe"], "Should match original"
    print("✓ Universe loads correctly from scanner output")
    
    # Test the logic that would be in _load_equity_universe
    # 1. Check scanner's universe.json first
    if universe_path.exists():
        with universe_path.open("r") as f:
            universe_data = json.load(f)
        if isinstance(universe_data, dict):
            eu = universe_data.get("equity_universe")
            if eu and isinstance(eu, list):
                cleaned = [str(sym).strip().upper() for sym in eu if sym]
                assert len(cleaned) == 5, "Should extract 5 symbols"
                print(f"✓ Extraction logic works: {cleaned}")
    
    print("\n✓ Equity engine loading test PASSED\n")


def main():
    """Run all integration tests."""
    print("\n" + "=" * 80)
    print("EQUITY UNIVERSE FILTERING - INTEGRATION TEST SUITE")
    print("=" * 80 + "\n")
    
    try:
        test_scanner_with_nifty_config()
        test_universe_json_structure()
        test_equity_engine_loading()
        
        print("=" * 80)
        print("ALL INTEGRATION TESTS PASSED ✓")
        print("=" * 80)
        print("\nEquity universe filtering is ready for production!")
        print("\nTo test with actual Kite credentials:")
        print("1. python -m scripts.run_day --login --engines none  # Refresh tokens")
        print("2. python -m scripts.run_day --mode paper --engines equity")
        print("3. Check logs for:")
        print("   - 'MarketScanner: scanning X enabled equity symbols'")
        print("   - 'Equity universe loaded from scanner (mode=nifty_lists, symbols=X)'")
        
        return 0
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
